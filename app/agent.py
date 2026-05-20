import json

from dotenv import load_dotenv
from openai import OpenAI

from app.db import load_messages, save_message, setup_db
from app.model.user import USER_PROFILE
from app.tools import CURRENT_SESSION
from app.tools import TOOLS as TOOL_FUNCTIONS

load_dotenv()

client = OpenAI()

_SYSTEM_PROMPT = f"""You are a personal AI finance companion for {USER_PROFILE['name']}, \
a {USER_PROFILE['age']}-year-old living in {USER_PROFILE['city']}.

User profile:
- Monthly income (post-tax): ₹{USER_PROFILE['monthly_income_inr']:,}, credited on the 1st of each month
- Financial goal: {USER_PROFILE['stated_goal']}

You have real-time access to their accounts via tools. Always fetch live data before giving advice — never guess numbers.
Be conversational, specific, and proactive. Use ₹ for all currency amounts.
When you spot spending patterns, savings risks, or opportunities tied to their goal, bring them up unprompted.
"""

_OPENAI_TOOLS = [
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


def _execute_tool(name: str, args: dict) -> str:
    fn = TOOL_FUNCTIONS.get(name)
    if fn is None:
        return f"Unknown tool: {name}"
    return json.dumps(fn(**args))


def _assistant_msg_to_dict(msg) -> dict:
    d: dict = {"role": "assistant", "content": msg.content}
    if msg.tool_calls:
        d["tool_calls"] = [
            {
                "id": tc.id,
                "type": tc.type,
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
            for tc in msg.tool_calls
        ]
    return d


def run():
    setup_db()
    messages = load_messages()

    if not messages:
        system_msg = {"role": "system", "content": _SYSTEM_PROMPT}
        messages.append(system_msg)
        save_message(CURRENT_SESSION, system_msg)
        print(f"Hi {USER_PROFILE['name']}! I'm your finance companion. How can I help you today?")
    else:
        print(f"Welcome back, {USER_PROFILE['name']}! I remember our previous conversations. How can I help?")

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input or user_input.lower() in ("quit", "exit"):
            print("Goodbye!")
            break

        user_msg = {"role": "user", "content": user_input}
        messages.append(user_msg)
        save_message(CURRENT_SESSION, user_msg)

        # Agentic loop: keep going until there are no more tool calls
        while True:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                tools=_OPENAI_TOOLS,
            )
            assistant_msg = response.choices[0].message
            msg_dict = _assistant_msg_to_dict(assistant_msg)
            messages.append(msg_dict)
            save_message(CURRENT_SESSION, msg_dict)

            if response.choices[0].finish_reason != "tool_calls":
                print(f"\nAssistant: {assistant_msg.content}")
                break

            for tc in assistant_msg.tool_calls:
                args = json.loads(tc.function.arguments)
                result = _execute_tool(tc.function.name, args)
                tool_msg = {"role": "tool", "tool_call_id": tc.id, "content": result}
                messages.append(tool_msg)
                save_message(CURRENT_SESSION, tool_msg)
