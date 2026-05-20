import json
import re
from typing import Any, cast

from dotenv import load_dotenv
from openai import OpenAI
from openai.types.chat import ChatCompletionMessage, ChatCompletionMessageToolCall

from app.db import append_reminder, load_memory, load_session_messages, save_message, setup_db
from app.model.user import USER_PROFILE
from app.tools import CURRENT_SESSION
from app.tools import TOOLS as TOOL_FUNCTIONS

load_dotenv()

client = OpenAI()

_SESSION_DATES = {1: "Monday, November 3, 2025", 2: "Thursday, November 6, 2025"}
_TODAY = _SESSION_DATES[CURRENT_SESSION]

_SYSTEM_PROMPT_BASE = f"""You are a personal AI finance companion for {USER_PROFILE['name']}, \
a {USER_PROFILE['age']}-year-old living in {USER_PROFILE['city']}.

Today's date: {_TODAY}

User profile:
- Monthly income (post-tax): ₹{USER_PROFILE['monthly_income_inr']:,}, credited on the 1st of each month
- Financial goal: {USER_PROFILE['stated_goal']}

You have real-time access to their accounts via tools. Always fetch live data before giving advice — never guess numbers.
Be conversational, specific, and proactive. Use ₹ for all currency amounts.
When you spot spending patterns, savings risks, or opportunities tied to their goal, bring them up unprompted.

CRITICAL TOOL DISCIPLINE:
- Any context inside <injected_memories> tags is for behavioral and goal context only: user commitments, habits, and stated preferences.
- <injected_memories> DOES NOT contain valid financial data. Any balance, transaction amount, or bill figure mentioned there is stale and must be ignored.
- Always assume every financial number from a previous session is outdated, regardless of how it is worded.
- You MUST call `get_account_balance` and `get_upcoming_bills` if the user inquires about making a purchase, spending money, or modifying a savings goal. Do not guess or rely on memory for numbers.
"""


def _build_system_prompt() -> str:
    memory = load_memory()
    parts = []
    if memory.get("goal"):
        parts.append(f"Goal: {memory['goal']}")
    for commitment in memory.get("active_commitments", []):
        parts.append(f"Commitment: {commitment}")
    for flag in memory.get("spending_flags", []):
        parts.append(f"Spending flag: {flag}")
    for reminder in memory.get("reminders", []):
        parts.append(f"Reminder ({reminder['date']}): {reminder['content']}")
    if not parts:
        return _SYSTEM_PROMPT_BASE
    memory_block = "\n".join(f"- {p}" for p in parts)
    return _SYSTEM_PROMPT_BASE + f"\n<injected_memories>\n{memory_block}\n</injected_memories>"

_OPENAI_TOOLS: list[Any] = [
    {
        "type": "function",
        "function": {
            "name": "get_recent_transactions",
            "description": (
                "Fetch transactions from the last N days. "
                "Negative amount = debit (money out), positive = credit (money in). All amounts in INR."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Number of days to look back from today"},
                },
                "required": ["days"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_account_balance",
            "description": "Get current balances across all accounts: checking, savings, house_fund, mutual_funds. INR.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_upcoming_bills",
            "description": "Get scheduled bills and auto-debits due in the next N days.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Days to look ahead (default 30)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_reminder",
            "description": "Set a financial reminder for a specific date.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
                    "content": {"type": "string", "description": "Reminder text"},
                },
                "required": ["date", "content"],
            },
        },
    },
]


_FINANCIAL_RE = re.compile(
    r'\b(balance|spend|spending|spent|afford|bill|transaction|transfer|'
    r'budget|saving|savings|purchase|buy|bought|cost|income|expense|pay|'
    r'payment|fund|account|debt|invest|investing|investment|mutual\s+fund|'
    r'debit|credit|withdraw|deposit|net\s+worth|interest\s+rate)\b',
    re.IGNORECASE,
)


def _is_financial_inquiry(user_input: str) -> bool:
    return bool(_FINANCIAL_RE.search(user_input))


def _execute_tool(name: str, args: dict) -> str:
    fn = TOOL_FUNCTIONS.get(name)
    if fn is None:
        return f"Unknown tool: {name}"
    result = fn(**args)
    if name == "set_reminder" and result.get("status") == "set":
        append_reminder(result["date"], result["content"])
    return json.dumps(result)


def _process_tool_result(tool_name: str, raw_result: str) -> str:
    try:
        data = json.loads(raw_result)
    except json.JSONDecodeError:
        return raw_result

    if tool_name == "get_recent_transactions":
        by_category: dict[str, float] = {}
        for t in data:
            if t["amount"] < 0:
                cat = t["category"]
                by_category[cat] = by_category.get(cat, 0) + abs(t["amount"])
        total_spend = sum(by_category.values())
        return json.dumps({
            "spend_by_category_inr": {k: round(v, 2) for k, v in sorted(
                by_category.items(), key=lambda x: x[1], reverse=True
            )},
            "total_spend_inr": round(total_spend, 2),
        })

    if tool_name == "get_upcoming_bills":
        total = sum(abs(b["amount"]) for b in data)
        return json.dumps({
            "bills": data,
            "total_due_inr": round(total, 2),
        })

    if tool_name == "get_account_balance":
        liquid = data.get("checking", 0) + data.get("savings", 0)
        return json.dumps({**data, "liquid_total_inr": round(liquid, 2)})

    return raw_result


def _assistant_msg_to_dict(msg: ChatCompletionMessage) -> dict[str, Any]:
    d: dict[str, Any] = {"role": "assistant", "content": msg.content}
    if msg.tool_calls:
        d["tool_calls"] = [
            {
                "id": tc.id,
                "type": tc.type,
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
            for tc in msg.tool_calls
            if isinstance(tc, ChatCompletionMessageToolCall)
        ]
    return d


def process_user_message(user_input: str, session: int) -> dict[str, Any]:
    """Run one user turn through the agentic loop. Returns reply, session, and tool_calls."""
    messages = load_session_messages(session)
    system_msg = {"role": "system", "content": _build_system_prompt()}

    if not messages:
        messages.append(system_msg)
        save_message(session, system_msg)
    else:
        if messages[0].get("role") == "system":
            messages[0] = system_msg
        else:
            messages.insert(0, system_msg)

    user_msg = {"role": "user", "content": user_input}
    messages.append(user_msg)
    save_message(session, user_msg)

    is_financial = _is_financial_inquiry(user_input)
    tool_calls_log: list[dict[str, Any]] = []
    first_turn = True

    while True:
        tool_choice = "required" if (first_turn and is_financial) else "auto"
        first_turn = False
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=cast(Any, messages),
            tools=_OPENAI_TOOLS,
            tool_choice=tool_choice,
        )
        assistant_msg = response.choices[0].message
        msg_dict = _assistant_msg_to_dict(assistant_msg)
        messages.append(msg_dict)
        save_message(session, msg_dict)

        if response.choices[0].finish_reason != "tool_calls":
            return {
                "reply": assistant_msg.content or "",
                "session": session,
                "tool_calls": tool_calls_log,
            }

        for tc in assistant_msg.tool_calls or []:
            if not isinstance(tc, ChatCompletionMessageToolCall):
                continue
            args = json.loads(tc.function.arguments)
            raw = _execute_tool(tc.function.name, args)
            processed = _process_tool_result(tc.function.name, raw)
            tool_calls_log.append({
                "name": tc.function.name,
                "args": args,
                "result": json.loads(processed),
            })
            tool_msg = {"role": "tool", "tool_call_id": tc.id, "content": processed}
            messages.append(tool_msg)
            save_message(session, tool_msg)


def run():
    setup_db()
    existing = load_session_messages(CURRENT_SESSION)
    if existing:
        print(f"Welcome back, {USER_PROFILE['name']}! I remember our previous conversations. How can I help?")
    else:
        print(f"Hi {USER_PROFILE['name']}! I'm your finance companion. How can I help you today?")

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input or user_input.lower() in ("quit", "exit"):
            print("Goodbye!")
            break

        result = process_user_message(user_input, CURRENT_SESSION)
        print(f"\nAssistant: {result['reply']}")
