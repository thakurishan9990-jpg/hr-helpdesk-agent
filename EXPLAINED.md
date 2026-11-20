# How This Project Works — Explained Simply

This guide explains every part of the Nimbus HR/IT Helpdesk agent in plain language. Read it top to bottom once, then use it as a reference.

---

## The big picture in one paragraph

An employee types a question. First, a **guardrail** checks that the question is safe and about HR/IT. Then **Gemini** (the LLM) reads it and decides what information it needs. For a policy question it calls the **RAG** search tool, which finds the right paragraphs in our policy documents. For a question about a specific employee it calls a **database tool**, which lives in a separate **MCP server** that reads Postgres. Gemini writes an answer from what the tools returned. A final **guardrail** checks that policy answers cite their source, that the agent didn't guess, and that no personal data (emails, phone numbers) is shown. **LangGraph** is the "flowchart" that connects these steps.

---

## Part 1 — RAG (Retrieval-Augmented Generation)

**The problem:** Gemini knows nothing about *our* company's leave rules. If we just ask it, it will make up a plausible answer (called *hallucination*).

**The fix:** before answering, *retrieve* the relevant policy text and give it to the model: "answer using ONLY this". That's RAG.

### How it works here

**Ingestion (one time): `python ingest.py`**

1. **Load**: read the 5 markdown files in `data/policies/`.
2. **Chunk**: split each file at every `## ` heading, so one section becomes one chunk. That gives **39 chunks**.
   - Why sections and not "every 500 characters"? A section is one complete idea, and we get its name for free. We need that name for citations ("Leave Policy — 5. Carry Forward and Encashment").
3. **Embed**: send each chunk to Gemini's embedding model. You get back a list of 768 numbers (a *vector*) that represents its *meaning*. Texts with similar meaning get vectors that point in similar directions.
4. **Store**: save each vector, its text, and `{document, section}` metadata in **ChromaDB**, a vector database saved on disk in `chroma_db/`.

**Retrieval (every question): `search_policies(query)`**

1. Embed the question with the same model.
2. Ask ChromaDB for the 4 closest chunk vectors. Closeness is measured by **cosine distance**: 0 means the same meaning, bigger means less related.
3. **Drop chunks whose distance is above `MAX_DISTANCE` (0.45).** If nothing is left, we return an empty list and the agent says "I couldn't find this" instead of guessing.
4. Return each chunk with its document and section, so the answer can cite it.

### Files
| File | What it does |
|------|--------------|
| `data/policies/*.md` | The knowledge: leave, WFH, IT/password, expenses, code of conduct |
| `helpdesk/rag.py` | `chunk_markdown` (splitting), `build_index` (embed + store), `search_policies` (retrieve + filter) |
| `helpdesk/llm.py` | `embed()` calls Gemini. It uses `RETRIEVAL_DOCUMENT` for chunks and `RETRIEVAL_QUERY` for questions, because Gemini tunes the vectors for each role |
| `ingest.py` | Runs the ingestion and prints the chunks it made |

**Debug tip:** `python -m helpdesk.rag "can I carry forward leave?"` shows every candidate chunk with its distance and whether it was kept or dropped.

---

## Part 2 — MCP (Model Context Protocol) + Postgres

**What MCP is:** a standard "plug" that lets AI applications use tools provided by *another program*. Think of it like USB: any MCP client can connect to any MCP server and ask "what tools do you have?" and then "please run this one."

**Two sides:**
- **MCP server** (`helpdesk/mcp_server.py`): owns the database connection and offers tools.
- **MCP client** (`helpdesk/mcp_client.py`): used by our agent to discover and call those tools.

They talk over **stdio**. The client starts the server as a subprocess (`python -m helpdesk.mcp_server`) and they exchange JSON messages through the subprocess's standard input and output.

### The database
`docker-compose.yml` starts PostgreSQL 16 in a container. The first time it starts, Postgres runs `db/init.sql`, which creates:
- `employees(id, name, department, manager, email, phone)`: 10 fake employees, E101–E110
- `leave_balances(employee_id, leave_type, total, used, remaining)`: annual, sick and casual leave for each employee

### The two tools
| Tool | Arguments | Returns |
|------|-----------|---------|
| `get_employee` | `employee_id` | name, department, manager, email, phone |
| `get_leave_balance` | `employee_id`, optional `leave_type` | list of {leave_type, total, used, remaining} |

### Why this is safe (important for interviews)
1. **The LLM never writes SQL.** It can only pick one of two tools and fill in an ID. The SQL is fixed in our code.
2. **Parameterized queries**: `WHERE id = %s` with the value passed separately. The database driver treats the value as data, never as SQL code, so SQL injection is impossible.
3. **Input validation**: the ID must match `^E\d{3}$` and the leave type must be annual, sick or casual. `E101'; DROP TABLE employees;--` is rejected before touching the database (we tested this).
4. **Read-only session**: the connection uses `default_transaction_read_only=on`, so Postgres itself refuses any write, even if a bug slipped through.

### How the agent uses MCP tools
In `agent.py`, `get_tools()` calls `list_mcp_tools()`. The server replies with each tool's name, description and **JSON schema** of its arguments. We turn those into Gemini `FunctionDeclaration`s. So if you add a third tool to the server, the agent sees it automatically, without editing the agent.

> **Version note:** this project uses `mcp` SDK v2, where the server class is `MCPServer` (in v1 it was called `FastMCP`), and tool fields use snake_case (`input_schema`, `structured_content`).

---

## Part 3 — Guardrails (`helpdesk/guardrails.py`)

Guardrails are checks that run **around** the LLM. The LLM is clever but unpredictable, so we don't trust it alone.

### Input guardrails: `check_input(text)`
They run in this order, and the first failure blocks the message:

1. **Sanity**: empty or longer than 1,000 characters → rejected.
2. **Regex pattern rules** (`INJECTION_PATTERNS`): 7 groups of phrases attackers commonly use. For example: "ignore previous instructions", "reveal your system prompt", "you are now…", "developer mode", "bypass the guardrails", fake `<system>` tags, and SQL keywords like `DROP TABLE`. *Fast, free, works offline, but can be dodged by rewording.*
3. **LLM classifier** (`classify_with_llm`): a separate Gemini call with a strict JSON schema answers `{is_prompt_injection, is_in_scope, reason}`.
   - It catches re-worded attacks (test #6 is written to slip past the regex).
   - `is_in_scope` is the **scope control**: coding help, weather, general knowledge and similar → polite refusal.
   - The user text is wrapped in `<user_message>` tags so the classifier judges it as data rather than obeying it.

When something is blocked, the graph ends immediately with a polite fixed message. The main agent never even sees the attack.

### Output guardrails
4. **`validate_output(answer, tool_log)`** checks the draft answer against what the tools actually returned:
   - **Rule A**: empty answer → replaced with the "couldn't find" message.
   - **Rule B (no guessing)**: policies were searched, nothing relevant was found, and no database data either → the answer is replaced with "I couldn't find this in the company policy documents…". The model had no facts, so whatever it wrote is a guess.
   - **Rule C (citations)**: policy text was used but the answer has no `Source:` → we append the sources that were retrieved. This is skipped for "I couldn't find this" answers, because citing documents that didn't answer the question would be misleading.
   - **Rule D (honest citations)**: if the answer says `[Source: HR database]` but no database tool actually ran, that citation is removed. A citation must match a tool that really ran. (We found this in testing: for the PII question, the model refused without looking anything up but still cited the database.)
5. **`redact_pii(text)`** masks personal data with regexes: emails, phone numbers, Aadhaar, PAN and card numbers → `[REDACTED EMAIL]` and so on.
   - It runs **twice**: on database tool results *before Gemini sees them* (so the model can't leak what it never saw), and on the final answer (in case something slips through anyway). This is **defence in depth**.
   - Official mailboxes like `hr-helpdesk@nimbustech.example` are on an allow-list, because they are not personal data.

### Why regex AND an LLM?
| | Regex | LLM classifier |
|---|---|---|
| Speed / cost | instant, free | one API call |
| Predictable | yes | mostly |
| Understands meaning | no | yes |
| Easy to evade | yes | harder |

Together they cover each other's weaknesses.

---

## Part 4 — The LangGraph flow (`helpdesk/agent.py`)

**LangGraph** lets you build an agent as a **graph**: *nodes* are Python functions, *edges* say what runs next, and a shared **state** dict carries data between nodes.

```
START → input_guard ──blocked──→ END
              │
              ▼
           agent ◄────────┐
              │           │
     wants a tool? ──yes──► tools
              │
              no
              ▼
        output_guard → END
```

### The state (`AgentState`)
| Field | Meaning |
|-------|---------|
| `question` | what the user asked |
| `contents` | the conversation with Gemini so far (user message, model replies, tool results) |
| `tool_log` | which tools ran and whether they found anything (output validation uses this) |
| `rounds` | how many tool rounds so far (stops infinite loops at 4) |
| `blocked`, `block_reason` | set by `input_guard` |
| `answer`, `notes` | final answer and which guardrails acted |

### The nodes
1. **`input_guard_node`**: runs `check_input`. If the message is blocked, it sets the answer to the polite message; otherwise it starts the conversation.
2. **`agent_node`**: calls Gemini with the system prompt and the 3 tool declarations. Gemini either replies with text (the final answer) or with a **function call** such as `get_leave_balance(employee_id="E102")`.
3. **`tools_node`**: executes each function call (`run_tool`): RAG for `search_policies`, MCP for the others. It sends the results back to Gemini as **function responses**.
4. **`output_guard_node`**: runs `validate_output` (citations, no guessing, PII).

### The routing functions (conditional edges)
- `after_input_guard`: blocked → END, otherwise → agent.
- `after_agent`: the last message contains a function call (and we're under 4 rounds) → tools, otherwise → output_guard.

### Walk-through: "How many leave days does E102 have left?"
1. `input_guard`: no regex match; the classifier says in scope and not an injection → allowed.
2. `agent`: Gemini replies with the function call `get_leave_balance({"employee_id": "E102"})`.
3. `tools`: the MCP client starts the server, which runs the parameterized SQL and returns `{annual: 7 left, sick: 7, casual: 2}`.
4. `agent`: Gemini now has the data and writes "E102 has 7 annual, 7 sick and 2 casual leave days remaining. [Source: HR database]".
5. `output_guard`: no PII, nothing to fix → shown to the user.

**Why do we run the tools ourselves instead of letting the SDK do it automatically?** Because then the tool step is a visible node in the graph. We can log it, apply PII redaction to the result, and cap the number of rounds.

---

## Part 5 — Other files

| File | Purpose |
|------|---------|
| `helpdesk/config.py` | Reads `.env`. All settings (model names, `TOP_K`, `MAX_DISTANCE`, DB URL) live here |
| `helpdesk/llm.py` | The only place that calls Gemini. `generate()` (chat, optional JSON schema) and `embed()`, both with automatic retry on rate limits (429). `python -m helpdesk.llm` lists available models |
| `main.py` | CLI chat loop. `--debug` shows tools used and guardrail notes |
| `streamlit_app.py` | Minimal web chat using the same `ask()` function |
| `tests/cases.py` | The 10 questions, each with an automatic `check` function |
| `tests/test_agent.py` | pytest runs the 10 questions; it **skips** with a clear reason if the key, DB or index is missing |
| `tests/test_guardrails.py` | 26 offline tests of regexes, redaction and validation |
| `run_tests.py` | Runs the 10 questions, saves `results/test_results.json`, rewrites the README table |
| `.env.example` | Template for secrets. The real `.env` is in `.gitignore` and never committed |

---

## 10 likely interview questions (with short answers)

**1. What is RAG and why did you use it?**
Retrieval-Augmented Generation: search our own documents first, then let the LLM answer only from what was found. The LLM doesn't know our company's policies, so without RAG it would hallucinate. RAG also lets us cite sources and update knowledge by editing documents instead of retraining a model.

**2. How did you chunk the documents, and why?**
By markdown section (`##` heading), so each chunk is one complete topic and carries its section name for citations. Very long sections would be split further by paragraph (max 1,500 characters). I also add "Document — Section" to the start of each chunk's text, which helps the embedding capture what the chunk is about.

**3. How does the agent avoid making things up?**
Three layers. (a) The system prompt says to answer only from tool results. (b) Retrieval drops chunks above a cosine-distance threshold, so irrelevant text isn't passed on as "evidence". (c) The output guardrail replaces the answer with "I couldn't find this" whenever policies were searched but nothing relevant came back. That last one is code, not a request to the model.

**4. What is MCP, and why not just query the database directly from the agent?**
MCP is a standard protocol for exposing tools to AI apps through a separate server. It separates concerns: the server owns the database credentials and offers only two safe, read-only tools, and any MCP-compatible client can reuse them. The LLM never sees SQL or credentials.

**5. How do you prevent SQL injection?**
The LLM can't write SQL at all; it only fills in tool arguments. The server validates the ID format with a regex and uses parameterized queries (`%s`), and the DB session is read-only. So `E101'; DROP TABLE…` fails validation, and even if it didn't, it would be treated as a plain string.

**6. How does your prompt-injection detection work, and what are its limits?**
Regex rules for well-known attack phrases (fast, free), then a Gemini classifier with a JSON schema for reworded attacks. Limits: regex is easy to evade, and the classifier is itself an LLM that could be fooled. We also don't scan retrieved documents for *indirect* injection, though the system prompt tells the model to treat tool results as data. Defence in depth reduces risk; it can't remove it.

**7. How does PII redaction work?**
Regexes find emails, phones, Aadhaar, PAN and card numbers and replace them with `[REDACTED …]`. It's applied to database results before the LLM sees them, and again to the final answer. Official company mailboxes are allow-listed.

**8. Explain your LangGraph graph.**
Four nodes: `input_guard` → `agent` ⇄ `tools` → `output_guard`. A shared state dict carries the question, the Gemini conversation, a tool log and the answer. Conditional edges end early if the input is blocked, and loop between agent and tools until Gemini stops requesting tools (maximum 4 rounds).

**9. How did you test the agent?**
Two levels. 26 offline unit tests for the guardrails (no API needed). 10 end-to-end questions covering policy, database, injection, out-of-scope, cannot-answer, PII and a mixed DB + policy question. Each has an automatic pass/fail check (for example: "the answer contains 7 and the get_leave_balance tool was used"). `run_tests.py` records the actual answers in the README.

**10. What would you improve for production?**
Authentication, so employees can only see their own data. Keeping one MCP connection open instead of starting a subprocess per call. Conversation memory. Hybrid search (keyword + vector) and a re-ranker. Logging and monitoring of blocked requests. A larger evaluation set with an LLM-as-judge for answer quality. Tuning the distance threshold on real questions.
