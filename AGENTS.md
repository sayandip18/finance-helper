# AI Personal Finance expert

## Project Architecture

```
[ User Input ]
      |
      v
[ Keyword Matcher ]  (zero-latency, no LLM call)
      |
      +-- match --> tool_choice = "required"  ─┐
      |                                         |
      +-- no match --> tool_choice = "auto"  ──┤
                                               |
                                               v
                              [ LLM Main Conversation Loop ]
                                   (gpt-4o + tool calls)
                                first turn: tool_choice above
                               subsequent turns: tool_choice="auto"
                                               |
                                               v
                                   [ Output to User ]
                                               |
                                               v
                        [ Extract Insights (gpt-4o-mini, background) ]
                                               |
                                               v
                                     [ Save to Memory DB ]
```

## Constraints

- **No agent frameworks.** No LangChain, LlamaIndex, CrewAI, etc.
- **LLM calls only where judgment is needed.** Do not use LLM to do arithmetic, parse a date, or sum a column. Handle such tasks over to the backend code via function calling.
- **Memory must persist on disk or file** between Session 1 and Session 2. In-process state doesn't count.
