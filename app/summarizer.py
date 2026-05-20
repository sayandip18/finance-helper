import json
import sys

from dotenv import load_dotenv
from openai import OpenAI

from app.db import load_session_messages, save_insights, setup_vector_db

load_dotenv()

_EXTRACTION_SYSTEM_PROMPT = """\
You are a data extraction worker. Analyze the conversation transcript and extract long-term goals, habits, and user commitments.

CRITICAL CONSTRAINT:
Do NOT include live numeric account balances, transaction amounts, or volatile financial data in the "long_term_insights" array. Only extract structural rules, commitments, or explicit user requests.

Your output must strictly be a JSON object matching this schema:
{
  "long_term_insights": string[],
  "stale_financial_metrics_to_ignore": string[]
}"""

client = OpenAI()


def _build_transcript(messages: list[dict]) -> str:
    lines = []
    for msg in messages:
        role = msg.get("role", "")
        if role == "system":
            continue
        if role == "user":
            lines.append(f"User: {msg.get('content', '')}")
        elif role == "assistant":
            content = msg.get("content") or ""
            tool_calls = msg.get("tool_calls") or []
            if content:
                lines.append(f"Assistant: {content}")
            for tc in tool_calls:
                fn = tc.get("function", {})
                lines.append(f"  [called {fn.get('name')}({fn.get('arguments')})]")
        elif role == "tool":
            lines.append(f"  [tool result: {msg.get('content', '')}]")
    return "\n".join(lines)


def summarize_session(session_number: int) -> None:
    setup_vector_db()

    messages = load_session_messages(session_number)
    if not messages:
        print(f"No messages found for session {session_number}.")
        return

    transcript = _build_transcript(messages)

    extraction = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": _EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": f"Transcript:\n\n{transcript}"},
        ],
        response_format={"type": "json_object"},
    )

    result = json.loads(extraction.choices[0].message.content)
    insights: list[str] = result.get("long_term_insights", [])

    if not insights:
        print(f"No long-term insights extracted from session {session_number}.")
        return

    embeddings_response = client.embeddings.create(
        model="text-embedding-3-small",
        input=insights,
    )
    embeddings = [e.embedding for e in embeddings_response.data]

    save_insights(session_number, insights, embeddings)
    print(f"Stored {len(insights)} insights for session {session_number}.")


def main() -> None:
    session_number = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    summarize_session(session_number)


if __name__ == "__main__":
    main()
