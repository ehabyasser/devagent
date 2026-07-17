# DevAgent — AI Platform for Software Teams

A V1 AI engineering agent that automates two high-value workflows:

1. **Test Case Generator** — Given a Jira ticket ID or feature description, produces structured test cases across happy-path, negative, boundary, and regression categories.
2. **PR Reviewer** — Given a git diff, returns a structured code review grouped by architecture, Swift best practices, performance, security, and naming — with severity classification and a merge recommendation.

---

## Architecture

```
frontend/
  index.html       Single-page chat UI
  styles.css       Premium dark design system
  app.js           API calls, SSE, rich result rendering

backend/
  main.py          FastAPI app + CORS + lifespan hooks
  config.py        Pydantic-settings (env vars only)
  agents/
    base_agent.py      Agent loop ABC (Understand→Plan→Tool→Validate→Respond)
    test_gen_agent.py  Jira→TestSuite agent
    pr_review_agent.py Diff→PRReview agent
  llm/
    base_llm.py        LLM interface ABC
    openai_llm.py      OpenAI GPT-4o adapter
    anthropic_llm.py   Claude adapter
    ollama_llm.py      Local Ollama adapter
  tools/
    jira_tool.py       Jira REST API v3 fetcher (ADF parser)
    diff_parser.py     Unified diff parser (no shell exec)
    secret_scanner.py  Regex-based credential detector
  schemas/
    test_case.py       TestSuite / TestCase Pydantic schemas
    pr_review.py       PRReview / ReviewIssue Pydantic schemas
  routers/
    agent_router.py    POST /api/agent/test-gen, /api/agent/pr-review
    health_router.py   GET /health
```

---

## Quick Start

### 1. Clone & install

```bash
git clone <this-repo>
cd devagent

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

### 2. Configure secrets

```bash
cp .env.example .env
# Edit .env and set your LLM API key
```

Minimum `.env` for OpenAI:

```
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

For Jira integration (optional — you can use manual descriptions instead):

```
JIRA_BASE_URL=https://your-org.atlassian.net
JIRA_EMAIL=you@yourorg.com
JIRA_API_TOKEN=your-api-token
```

### 3. Start the backend

```bash
cd backend
uvicorn main:app --reload --port 8000
```

Verify: `curl http://localhost:8000/health`

### 4. Open the frontend

Open `frontend/index.html` in your browser directly (no build step needed).

> **Tip**: Use the "Try an example" chips to test the UI without typing anything.

---

## API Reference

### `POST /api/agent/test-gen`

```json
{
  "ticket_id": "PROJ-123",      // optional — provide this OR description
  "description": "As a user…"   // optional — manual feature description
}
```

Returns a `TestSuite` JSON object.

### `POST /api/agent/pr-review`

```json
{
  "pr_title": "feat: Add Face ID login",
  "diff": "diff --git a/…"
}
```

Returns a `PRReview` JSON object with severity-classified issues and a merge recommendation.

### `GET /health`

Returns `{"status": "ok", "provider": "openai/gpt-4o"}`.

---

## Switching LLM Providers

| Provider   | `.env` settings                                                 |
|------------|----------------------------------------------------------------|
| OpenAI     | `LLM_PROVIDER=openai` + `OPENAI_API_KEY`                      |
| Anthropic  | `LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY`                |
| Ollama     | `LLM_PROVIDER=ollama` + `OLLAMA_BASE_URL` + `OLLAMA_MODEL`    |

---

## Running Tests

```bash
cd devagent
pytest backend/tests/ -v
```

Tests cover: diff parser, secret scanner, Pydantic schema validation.

---

## Security Notes

- All secrets via environment variables only — nothing hard-coded.
- No shell command execution anywhere in the codebase.
- Jira credentials use API tokens (never passwords).
- Diff input validated and truncated at 500 KB before LLM call.
- CORS restricted to configured origins (default: localhost:5500).
- Secret scanner runs on every diff before the LLM sees it.

---

## Project Status

| Feature                        | Status  |
|--------------------------------|---------|
| Test Case Generator (manual)   | ✅ Done |
| Test Case Generator (Jira)     | ✅ Done |
| PR Reviewer (diff)             | ✅ Done |
| Secret scanner                 | ✅ Done |
| OpenAI adapter                 | ✅ Done |
| Anthropic adapter              | ✅ Done |
| Ollama adapter                 | ✅ Done |
| Frontend chat UI               | ✅ Done |
| Agent loop visualiser          | ✅ Done |
| Unit tests                     | ✅ Done |
| SSE streaming endpoint         | ✅ Done |

### V2 Roadmap

- ReAct / multi-turn agent loop
- GitHub PR integration (fetch diffs automatically)
- Conversation history / session memory
- Webhook to post review comments directly to GitHub PRs
- Docker Compose setup
