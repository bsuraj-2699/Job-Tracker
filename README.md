<div align="center">

<img src="https://capsule-render.vercel.app/api?type=venom&color=0:0f172a,50:1e3a5f,100:6366f1&height=200&section=header&text=jobtrack-agent&fontSize=52&fontColor=ffffff&fontAlignY=40&desc=AI-powered%20job%20application%20tracker%20%E2%80%94%20capture%2C%20extract%2C%20search%2C%20follow%20up&descAlignY=62&descSize=14&descColor=a5b4fc&animation=fadeIn" width="100%" />

<img src="https://readme-typing-svg.demolab.com?font=JetBrains+Mono&weight=700&size=18&duration=2800&pause=900&color=6366F1&center=true&vCenter=true&multiline=false&repeat=true&width=680&height=45&lines=Capture+any+job+posting+in+one+click+%F0%9F%96%B1%EF%B8%8F;Groq+LLM+extracts+structured+details+in+seconds+%F0%9F%A4%96;Semantic+search+with+Qdrant+%E2%80%94+find+any+application+naturally;Never+miss+a+follow-up+again+%F0%9F%94%94" alt="Typing" />

<br/><br/>

![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Qdrant](https://img.shields.io/badge/Qdrant-DC244C?style=for-the-badge&logoColor=white)
![Groq](https://img.shields.io/badge/Groq-F55036?style=for-the-badge&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![Chrome](https://img.shields.io/badge/Chrome%20Extension-MV3-4285F4?style=for-the-badge&logo=googlechrome&logoColor=white)

<br/>

![Status](https://img.shields.io/badge/Status-Active%20Development-6366f1?style=flat-square)
![Vectors](https://img.shields.io/badge/Vectors-384--dim-06b6d4?style=flat-square)
![Model](https://img.shields.io/badge/Primary%20Model-gpt_oss_120b-FF6B35?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-a5b4fc?style=flat-square)

</div>

---

## ⚡ What it does

> Apply to 20–30 jobs/day and forget them in 48 hours. This fixes that.

| | Feature | Detail |
|:---:|:---|:---|
| 🖱️ | **One-click capture** | Chrome extension grabs URL, title & full HTML from any job board |
| 🤖 | **LLM extraction** | Groq pulls company, role, salary, skills, summary — structured every time |
| 🧠 | **Semantic search** | *"that fintech role in Bangalore with React"* — finds it instantly |
| 📋 | **Status tracking** | CLI to update, list, export to CSV / Excel |
| 🔔 | **Follow-up reminders** | APScheduler flags cold applications after N days |

**Supported boards:** `LinkedIn` `Naukri` `Wellfound` `Internshala` `Indeed` `Glassdoor`

---

## 🏗️ Architecture

```
┌──────────────┐   raw HTML     ┌─────────────┐   LangChain    ┌──────────────┐
│   Browser    │ ─────────────▶ │   FastAPI   │ ─────────────▶│  Groq LLMs   │  
│  Extension   │  POST /capture │   backend   │    extract     │ gpt-oss-120b │
└──────────────┘                └─────────────┘                └──────────────┘
                                      │                               │
                                      │  embed 384-d                  ▼
                                      │  all-MiniLM-L6-v2      ExtractionResult
                                      ▼                         JobApplication
                                ┌───────────┐ ◀──── store ──────────────┘
                                │  Qdrant   │
                                │  (Docker) │
                                └───────────┘
                                      ▲
                       search / list / export / reminders
                                      │
                                ┌───────────┐
                                │    CLI    │  jobtrack <command>
                                └───────────┘  (typer + rich)
```


## 🛠️ Tech Stack

<div align="center">

[![Skills](https://skillicons.dev/icons?i=python,fastapi,docker&theme=dark)](https://skillicons.dev)

![LangChain](https://img.shields.io/badge/LangChain-1C3C3C?style=for-the-badge&logo=langchain&logoColor=white)
![Groq](https://img.shields.io/badge/Groq-F55036?style=for-the-badge&logoColor=white)
![Qdrant](https://img.shields.io/badge/Qdrant-DC244C?style=for-the-badge&logoColor=white)
![Pydantic](https://img.shields.io/badge/Pydantic-E92063?style=for-the-badge&logo=pydantic&logoColor=white)
![APScheduler](https://img.shields.io/badge/APScheduler-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Sentence Transformers](https://img.shields.io/badge/SentenceTransformers-FF9500?style=for-the-badge&logo=pytorch&logoColor=white)
![Trafilatura](https://img.shields.io/badge/trafilatura-2d6a4f?style=for-the-badge&logo=python&logoColor=white)
![Typer](https://img.shields.io/badge/Typer%20+%20Rich-000000?style=for-the-badge&logo=python&logoColor=white)
![Chrome MV3](https://img.shields.io/badge/Chrome%20MV3-4285F4?style=for-the-badge&logo=googlechrome&logoColor=white)

</div>

---

## 🚀 Quick Start

**Prerequisites:** Python 3.12 · Docker · Groq API key

```bash
# 1. clone & create a venv
git clone https://github.com/bsuraj-2699/jobtrack-agent.git
cd jobtrack-agent
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 2. install dependencies (downloads MiniLM weights on first run — expect a large install)
pip install -r requirements.txt

# 3. configure your Groq API key
cp .env.example .env
# edit .env → set GROQ_API_KEY=...

# 4. start Qdrant in Docker
docker compose up -d

# 5. run the backend (also starts the follow-up reminder scheduler)
uvicorn backend.main:app --reload

# 6. install the CLI globally
pip install -e .
jobtrack --help
```

**Load the extension:** `chrome://extensions` → Enable **Developer mode** → **Load unpacked** → select `extension/`

---

## 🖥️ CLI Reference

| Command | Description |
|:---|:---|
| `jobtrack search "<query>"` | Semantic search over applications (`--limit N`) |
| `jobtrack list` | List all applications (`--status <status>` to filter) |
| `jobtrack update <id>` | Update `--status` and/or `--notes` on an application |
| `jobtrack export` | Export to CSV — use `--format excel` for `.xlsx` |
| `jobtrack stats` | Totals, status breakdown, top skills, most active platform |
| `jobtrack reminders` | Applications overdue for a follow-up |

> `search`, `update`, `export` → talk to the running API · `list`, `stats`, `reminders` → read storage directly

---

## 📡 API Endpoints

| Method | Path | Purpose |
|:---|:---|:---|
| `POST` | `/capture` | Extract, embed, and store a captured page |
| `POST` | `/search` | Semantic search — `query`, `limit`, `status_filter` |
| `PATCH` | `/application/{id}` | Update status / notes (404 if not found) |
| `GET` | `/export` | Download all applications as CSV |
| `GET` | `/health` | Liveness + Qdrant connectivity + active model |

---

## ⚙️ Configuration

All settings load from `.env` (copy from `.env.example`):

| Variable | Default | Description |
|:---|:---|:---|
| `GROQ_API_KEY` | — | **Required.** Groq API key for extraction |
| `QDRANT_HOST` | `localhost` | Qdrant host |
| `QDRANT_PORT` | `6333` | Qdrant REST port |
| `QDRANT_COLLECTION` | `job_applications` | Collection name |
| `PRIMARY_MODEL` | `openai/gpt-oss-120b` | Fast extraction model |
| `FALLBACK_MODEL` | `qwen/qwen3.6-27b` | Higher-quality fallback |
| `REMINDER_CHECK_INTERVAL_HOURS` | `24` | How often the scheduler runs |
| `FOLLOW_UP_AFTER_DAYS` | `7` | Days before an application is flagged cold |

---

## 📁 Project Structure

```
jobtrack-agent/
├── backend/
│   ├── main.py                    # FastAPI app, endpoints, scheduler lifespan
│   ├── config.py                  # pydantic-settings configuration
│   ├── models.py                  # Pydantic models + detect_platform()
│   ├── extraction/
│   │   └── extractor.py           # trafilatura + Groq extraction pipeline
│   ├── storage/
│   │   └── qdrant_client.py       # Qdrant persistence (384-d vectors)
│   ├── scheduler/
│   │   └── reminders.py           # APScheduler follow-up checks
│   └── cli/
│       └── commands.py            # typer + rich CLI
├── extension/                     # Manifest V3 Chrome extension
├── .env.example
├── requirements.txt
├── pyproject.toml                 # `jobtrack` console script entry point
└── docker-compose.yml             # Qdrant service
```

---

<div align="center">

<br/>

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:6366f1,100:06b6d4&height=120&section=footer&text=track%20smarter%2C%20follow%20up%20faster&fontSize=15&fontColor=e2e8f0&fontAlignY=68" width="100%" />

</div>
