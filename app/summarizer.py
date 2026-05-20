import json
import sys

from dotenv import load_dotenv
from openai import OpenAI

from app.db import load_session_messages, merge_memory, setup_db

load_dotenv()

_EXTRACTION_SYSTEM_PROMPT = """\
You are a data extraction worker. Analyze the finance conversation transcript and extract structured long-term insights.

CRITICAL CONSTRAINTS:
- Do NOT include live numeric balances, transaction amounts, or any volatile financial data.
- Only extract structural rules, user-stated goals, explicit recurring commitments, and observed spending patterns.
- "goal" should be the user's long-term financial goal as stated in the conversation. Leave empty string if not mentioned.
- "active_commitments" are explicit recurring transfers, allocations, or financial habits the user confirmed (e.g. "transfer ₹30k to house fund on the 25th").
- "spending_flags" are patterns worth flagging across future sessions (e.g. "food delivery consistently high").

Output ONLY a JSON object matching this schema — no explanation, no markdown:
{
  "goal": string,
  "active_commitments": string[],
  "spending_flags": string[]
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
    setup_db()

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

    raw = extraction.choices[0].message.content or "{}"
    result = json.loads(raw)

    if not any([result.get("goal"), result.get("active_commitments"), result.get("spending_flags")]):
        print(f"No insights extracted from session {session_number}.")
        return

    merge_memory(result)
    n = len(result.get("active_commitments", [])) + len(result.get("spending_flags", []))
    print(f"Merged session {session_number} insights into memory.json ({n} items + goal).")


def main() -> None:
    session_number = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    summarize_session(session_number)


if __name__ == "__main__":
    main()
