# AI Personal Finance expert

## Project Architecture

```
[ User Input ] ---> [ LLM Main Conversation Loop ] ---> [ Output to User ]
                             |
                             v
               [ Extract Insights using cheap LLM model with background job]
                             |
                             v
                 [ Save to Memory JSON file ]
```

## Constraints

- **No agent frameworks.** No LangChain, LlamaIndex, CrewAI, etc.
- **LLM calls only where judgment is needed.** Do not use LLM to do arithmetic, parse a date, or sum a column. Handle such tasks over to the backend code via function calling.
- **Memory must persist on disk or file** between Session 1 and Session 2. In-process state doesn't count.
