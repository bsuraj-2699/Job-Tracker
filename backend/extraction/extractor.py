"""Extract structured job application data from job pages."""

from __future__ import annotations

import json
import os

import trafilatura
from dotenv import load_dotenv
from langchain_groq import ChatGroq

from backend.models import CaptureRequest, ExtractionResult

load_dotenv()

# Quality gate: if the primary model isn't confident enough or missed too many
# fields, we re-run the extraction with the stronger fallback model.
MIN_CONFIDENCE = 0.6
MAX_MISSING_FIELDS = 2

# Hard cap on raw HTML passed through when trafilatura can't clean the page.
RAW_HTML_FALLBACK_CHARS = 8000

# Output token budget for the models. The schema includes ``jd_full`` (the full
# job description), so a content-heavy posting needs enough room to avoid
# truncating the tool call mid-output and dropping required fields.
# Configurable via the MAX_TOKENS env var.
DEFAULT_MAX_TOKENS = 2048


class JobExtractor:
    """Turn a captured job page into a structured :class:`ExtractionResult`.

    Uses a fast primary model (Llama 3.3 70B) first and escalates to a stronger
    fallback model (GPT-OSS 120B) when the primary result looks low quality.
    """

    def __init__(self) -> None:
        primary_model = os.getenv("PRIMARY_MODEL", "llama-3.3-70b-versatile")
        fallback_model = os.getenv("FALLBACK_MODEL", "openai/gpt-oss-120b")
        max_tokens = int(os.getenv("MAX_TOKENS", DEFAULT_MAX_TOKENS))

        self.primary = ChatGroq(
            model=primary_model,
            temperature=0,
            max_tokens=max_tokens,
        ).with_structured_output(ExtractionResult)

        self.fallback = ChatGroq(
            model=fallback_model,
            temperature=0,
            max_tokens=max_tokens,
        ).with_structured_output(ExtractionResult)

    def clean_html(self, raw_html: str) -> str:
        """Strip boilerplate from raw HTML, returning clean readable text.

        Falls back to the first ``RAW_HTML_FALLBACK_CHARS`` characters of the
        raw HTML if trafilatura can't extract anything.
        """
        extracted = trafilatura.extract(raw_html)
        if extracted:
            return extracted
        return raw_html[:RAW_HTML_FALLBACK_CHARS]

    def build_prompt(self, clean_text: str, url: str) -> str:
        """Build the extraction instruction sent to the model."""
        return f"""You are a job-application data extractor. Given the cleaned text of a job posting and its URL, extract structured information.

Source URL: {url}

Job posting text:
\"\"\"
{clean_text}
\"\"\"

Extract the following fields:
- company: the hiring company's name.
- role: the job title / role.
- location: the job location (city / "Remote" / etc.), or null if not stated.
- salary_raw: the exact salary text as written on the page (e.g. "12-18 LPA", "₹50,000/month"), or null if no salary is mentioned.
- salary_min: the MONTHLY minimum salary in INR as an integer. Convert annual figures (e.g. LPA = lakhs per annum) to monthly INR (divide annual by 12). Null if unknown.
- salary_max: the MONTHLY maximum salary in INR as an integer, converted the same way. Null if unknown.
- skills: a list of up to 10 key skills / technologies required (e.g. ["Python", "FastAPI", "PostgreSQL"]).
- jd_full: the complete job description text.
- jd_summary: a concise 2-3 sentence summary of the role.
- source_platform: detect the job platform from the URL domain (e.g. "LinkedIn", "Naukri", "Wellfound", "Internshala", "Indeed", "Glassdoor"), or null if it is not one of these.
- extraction_confidence: a float between 0.0 and 1.0 reflecting how many of the above fields you were able to confidently extract (1.0 = everything found, lower as more fields are missing or uncertain).
- missing_fields: a list of the field names you could NOT find in the posting.
- used_fallback: set this to false.

Respond ONLY with the structured output. Do not include any preamble, explanation, or commentary.

IMPORTANT: If you cannot find the company name on this page, look for it in the page title, URL domain, or any 'Posted by' or 'Employer' text. Never return <UNKNOWN> — if truly not found, return an empty string '' instead.
Same rule applies to role/position — check the page <title> tag as a last resort. An empty string is always better than <UNKNOWN>."""

    def _clean_result(
        self, result: ExtractionResult, url: str
    ) -> ExtractionResult:
        """Normalize a raw extraction before returning it.

        Stamps the canonical ``url`` (we never trust the model to echo it) and
        scrubs any literal ``<UNKNOWN>`` placeholders down to empty strings.
        """
        data = result.model_dump()
        data["url"] = url
        for key, value in data.items():
            if isinstance(value, str) and value.strip().upper() == "<UNKNOWN>":
                data[key] = ""
        return ExtractionResult(**data)

    def _parse_failed_generation(
        self, error: Exception
    ) -> ExtractionResult | None:
        """Salvage a partial result from a Groq structured-output error.

        When structured-output validation fails, Groq echoes the model's raw
        (partial) JSON back inside the error message under ``failed_generation``.
        Pull it out and build an ExtractionResult rather than losing everything.
        """
        try:
            error_str = str(error)
            marker = "'failed_generation': '"
            start = error_str.find(marker)
            if start < 0:
                return None
            start += len(marker)
            end = error_str.rfind("}'") + 1
            if end <= start:
                return None
            raw = error_str[start:end]
            json_start = raw.find("{")
            json_end = raw.rfind("}") + 1
            if json_start < 0 or json_end <= json_start:
                return None
            partial_data = json.loads(raw[json_start:json_end])
            # A salvaged generation is low-trust by definition; every other field
            # falls back to its ExtractionResult default.
            partial_data.setdefault("extraction_confidence", 0.3)
            partial_data.setdefault("used_fallback", False)
            return ExtractionResult(**partial_data)
        except Exception as parse_err:  # noqa: BLE001 - best-effort salvage
            print(f"Could not parse failed_generation: {parse_err}")
            return None

    def extract(self, request: CaptureRequest) -> ExtractionResult:
        """Extract structured data from a capture request.

        Runs the primary model first and escalates to the fallback when the
        result is low confidence, too sparse, or missing both company and role.
        Never raises: on any model error it salvages partial JSON from the error
        when possible, otherwise returns an empty ExtractionResult so the
        ``/capture`` endpoint can decide what to do with a low-confidence result.
        """
        # Prefer the browser's rendered text when the extension sends it: it's
        # far smaller than the full page HTML (faster + cheaper to extract) and
        # already has the job description expanded. Fall back to cleaning the
        # raw HTML for older extension versions that don't send body_text.
        clean_text = request.body_text or self.clean_html(request.raw_html)
        prompt = self.build_prompt(clean_text, request.url)

        # A usable-but-low-quality primary result, kept as a last resort in case
        # the fallback model later errors out entirely.
        primary_result: ExtractionResult | None = None

        try:
            result: ExtractionResult = self.primary.invoke(prompt)
            result.used_fallback = False
            needs_fallback = (
                result.extraction_confidence < MIN_CONFIDENCE
                or len(result.missing_fields) > MAX_MISSING_FIELDS
                or (result.company == "" and result.role == "")
            )
            if not needs_fallback:
                return self._clean_result(result, request.url)
            primary_result = result
        except Exception as exc:  # noqa: BLE001 - never crash the capture
            print(f"Primary model failed: {exc}")
            partial = self._parse_failed_generation(exc)
            if partial and (partial.company or partial.role):
                print("Salvaged partial result from primary failed_generation.")
                return self._clean_result(partial, request.url)

        try:
            result = self.fallback.invoke(prompt)
            result.used_fallback = True
            return self._clean_result(result, request.url)
        except Exception as exc:  # noqa: BLE001 - never crash the capture
            partial = self._parse_failed_generation(exc)
            if partial:
                partial.used_fallback = True
                return self._clean_result(partial, request.url)
            if primary_result is not None:
                print("Fallback failed; using low-confidence primary result.")
                return self._clean_result(primary_result, request.url)
            print(f"Both models failed: {exc}")
            return ExtractionResult(
                url=request.url,
                company="",
                role="",
                jd_full="Extraction failed",
                jd_summary="Could not extract job details",
                extraction_confidence=0.0,
                missing_fields=["company", "role", "skills", "jd_full"],
                used_fallback=True,
            )


# Module-level singleton; created lazily so importing this module never
# instantiates the model clients (keeps imports cheap and side-effect free).
_extractor: JobExtractor | None = None


def get_extractor() -> JobExtractor:
    """Return the shared :class:`JobExtractor`, instantiating it on first use."""
    global _extractor
    if _extractor is None:
        _extractor = JobExtractor()
    return _extractor
