# AI Personal Finance expert

## Setup

Activate the virtual environment:

```
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Linux / Mac
```

Install dependencies:

```bash
uv sync
```

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

## Running the API server

```bash
fastapi dev main.py
```

The `/chat` endpoint will be available at `http://localhost:8000/chat`.

## Running the app

**Session 1** — ensure `CURRENT_SESSION = 1` in `app/tools.py`, then:

```bash
python main.py
```

**Between sessions** — after Session 1 ends, summarize it into memory.json before starting Session 2:

```bash
uv run python -m app.summarizer # summarizes session 1
```

This extracts long-term goals and commitments from the transcript (excluding volatile data like balances) and stores them as embeddings in the `session_insights` table.

**Session 2** — flip `CURRENT_SESSION = 2` in `app/tools.py`, then run again:

```bash
python main.py
```

The agent loads full conversation history from DB, so Session 2 remembers everything from Session 1.

## Hallucination guard — forced tool calls

Before every user turn, a zero-latency keyword match checks the message against a set of financial terms (balance, spend, bill, savings, etc.). If any keyword matches, the first LLM call in the agentic loop is issued with `tool_choice="required"`, forcing the model to invoke at least one tool (e.g. `get_account_balance`, `get_recent_transactions`) before it can reply. Subsequent turns in the same loop revert to `tool_choice="auto"` so the model can chain further tool calls or produce a final answer.
