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

## Database

Start Postgres:

```bash
docker run --name finance-pg \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=finance_helper \
  -p 5432:5432 \
  -d postgres:16
```

Set this in your `.env`:

```
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/finance_helper
```

Stop and restart (data is preserved):

```bash
docker stop finance-pg
docker start finance-pg
```

Wipe the database and start fresh:

```bash
docker rm -f finance-pg
```

Then re-run the `docker run` command above.

## Running the API server

```bash
fastapi dev app/main.py
```

The `/chat` endpoint will be available at `http://localhost:8000/chat`.

## Running the app

**Session 1** — ensure `CURRENT_SESSION = 1` in `app/tools.py`, then:

```bash
python main.py
```

**Between sessions** — after Session 1 ends, summarize it into pgvector before starting Session 2:

```bash
uv run summarize        # summarizes session 1
```

This extracts long-term goals and commitments from the transcript (excluding volatile data like balances) and stores them as embeddings in the `session_insights` table.

**Session 2** — flip `CURRENT_SESSION = 2` in `app/tools.py`, then run again:

```bash
python main.py
```

The agent loads full conversation history from Postgres, so Session 2 remembers everything from Session 1.
