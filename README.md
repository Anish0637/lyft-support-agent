# Lyft Support Agent

A production-grade multi-agent customer support system built with **LangGraph**, **FastAPI**, and a no-code **Agent Builder UI** — inspired by the [Lyft Engineering Blog](https://eng.lyft.com/scaling-self-serve-ai-agents-in-lyft-support-b8bf8edd4b37).

---

## What it does

Users (riders and drivers) chat with a smart support assistant. Under the hood a **meta-agent router** classifies each message and dispatches it to the correct specialist sub-agent. Domain experts can create and edit those sub-agents at runtime — no code required — using the internal Agent Builder UI.

```
Customer message
      │
      ▼
 Safety Gate ── blocked? ──► "I can't help with that."
      │
      ▼
  Classifier
      │
   ┌──┴───┬──────────┬───────────┬──────────┐
   ▼      ▼          ▼           ▼          ▼
Rider  Driver    Earnings   Damage    Charge
Intent Intent    Agent      Claim     Review …
```

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/Anish0637/lyft-support-agent.git
cd lyft-support-agent

# 2. Create virtualenv (Python 3.11)
python3.11 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set env vars
cp .env.example .env          # fill in your keys
source .env

# 5. Run the server
uvicorn api.server:app --reload --port 8000
```

Open:
- **Customer chat UI** → http://localhost:8000
- **Agent Builder UI** → http://localhost:8000/builder

---

## Project Structure

```
lyft-support-agent/
├── api/                        # FastAPI backend
│   ├── server.py               # App factory, CORS, static mounts
│   ├── models.py               # Pydantic request/response models
│   └── routes/
│       ├── chat.py             # POST /api/chat, conversation CRUD
│       ├── agents.py           # Agent CRUD, /lint, /test
│       └── health.py           # GET /health
│
├── agent/                      # LangGraph core
│   ├── meta_agent.py           # 10-node StateGraph router
│   ├── safety.py               # Safety gate (gpt-4o-mini)
│   └── configurable_agent.py  # Runtime JSON → LangGraph agent
│
├── config/
│   ├── loader.py               # Scans config/agents/*.json
│   └── agents/                 # One JSON file per sub-agent
│       ├── driver_tax.json
│       ├── charge_review.json
│       └── rider_general.json
│
├── tools/
│   └── support_tools.py        # 10 mock LangChain @tool functions
│
├── ci/
│   └── prompt_linter.py        # Static + LLM-powered prompt linter
│
├── evaluation/
│   ├── tasks.py                # 7 eval tasks
│   ├── metrics.py              # 5 LLM-as-judge evaluators
│   └── pipeline.py             # Local + LangSmith eval runner
│
├── tests/                      # 35 pytest tests (all passing)
│
├── ui/
│   ├── chat/index.html         # Customer-facing chat widget
│   └── builder/index.html      # Internal agent builder
│
└── docs/
    ├── ARCHITECTURE.md         # System design + flow diagrams
    ├── AGENT_BUILDER.md        # How to create/edit agents
    └── API.md                  # REST API reference
```

---

## Mock Data

The tools use in-memory mock data. Use these IDs when testing in the chat:

| Type   | ID           | Name            | Notes               |
|--------|-------------|-----------------|---------------------|
| Rider  | `rider_001` | Alice Johnson   | Active              |
| Rider  | `rider_002` | Bob Williams    | Active              |
| Rider  | `rider_003` | Carol Davis     | Suspended           |
| Driver | `driver_001`| Carlos Rivera   | Active, 4.85★       |
| Driver | `driver_002`| Diana Chen      | Active, 4.92★       |
| Driver | `driver_003`| Evan Thompson   | Deactivated         |
| Trip   | `trip_001`  | Alice → Carlos  | $24.50, no surge    |
| Trip   | `trip_002`  | Bob → Carlos    | $15.75, $3.25 surge |
| Trip   | `trip_003`  | Alice → Diana   | $35.00, $13 surge   |
| Trip   | `trip_004`  | Carol → Diana   | $18.00, no surge    |

---

## Running Tests

```bash
source .env
pytest tests/ -v
# 35/35 tests should pass
```

---

## Docs

| Doc | Contents |
|-----|----------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design, data flow diagrams, component breakdown |
| [docs/AGENT_BUILDER.md](docs/AGENT_BUILDER.md) | Step-by-step guide to creating and editing agents |
| [docs/API.md](docs/API.md) | Full REST API reference with request/response examples |

---

## Environment Variables

```bash
OPENAI_API_KEY=sk-...          # Required — used by all agents
LANGCHAIN_API_KEY=lsv2_...     # Optional — enables LangSmith tracing
LANGCHAIN_TRACING_V2=true      # Optional — enable tracing
LANGCHAIN_PROJECT=lyft-support-agent
```
