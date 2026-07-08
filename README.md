*This project has been created as part of the 42 curriculum by jmattion.*

# Agent Smith

Autonomous reasoning, code generation, and execution.

## Description

Agent Smith is an **agentic framework** that autonomously solves coding
challenges. Given a programming task, the agent **reasons, writes Python code,
executes it in a secure sandbox, observes the result, and iterates** until the
task is solved — the classic **Thought → Code → Observation** loop.

Unlike classical setups where an LLM emits a single final answer, our agent uses
**code-based tool calling**: the model writes real Python that calls tools
directly (`result = read_file("models.py", 1, 50); print(result)`). This is more
expressive than JSON tool calling — it allows persistent variables, loops, and
conditional logic across steps.

The framework is evaluated on two benchmarks:

- **MBPP** (*Mostly Basic Python Problems*) — short algorithmic problems: write
  one correct function.
- **SWE-bench** (Verified) — real bugs in real repositories (sympy, django,
  scikit-learn, xarray…) fixed inside Docker containers and submitted as a git
  patch.

The hard part is not only making the agent *intelligent*, but making it **safe,
controlled, reproducible, and measurable**: every LLM-generated line runs behind
a security boundary, every run is fully traced, and multiple models are
benchmarked to pick the best one.

## Instructions

### Requirements

- **Python 3.10**
- **[uv](https://docs.astral.sh/uv/)** as the package manager
- **Docker** (SWE-bench only — the agent explores and tests inside containers)
- One or more **free-tier LLM API keys** (Groq, OpenRouter, Google AI Studio…)

### Install

```bash
# Install the project (package: agent-smith)
uv sync

# Provide your API keys (never commit this file — it is git-ignored)
cp student/.env.example student/.env
# then edit student/.env:
#   API_KEYS=key1,key2,key3
```

Multiple keys are comma-separated; the agent rotates through them automatically
on rate limits / quota exhaustion.

### Run the sandbox on its own

The sandbox and its tools work **independently of the agent loop**. Pipe code
into it; tools from the connected MCP server are available as Python functions:

```bash
echo 'print(run_tests(code="def f(): return 1", test_list=["assert f()==1"], test_imports=[]))' \
  | uv run sandbox --mcp-stdio "python mcp_tools_mbpp.py"

# Interactive REPL (type EXEC to run, MAN for the tool manual, QUIT to exit)
uv run sandbox --interactive --mcp-stdio "python mcp_tools_swebench.py"

# With a custom Pydantic config file and an HTTP MCP server
uv run sandbox config.json --mcp-server <URL>
```

### Run the MBPP agent

```bash
# 1. Dump a task (via the external moulinette evaluator)
uv run moulinette_eval dump mbpp --output ../cache/mbpp_task.json

# 2. Run the agent
uv run python -m agent_mbpp \
  --task-file ../cache/mbpp_task.json \
  --output  ../cache/mbpp_solution.json \
  --model-name "meta-llama/llama-4-scout-17b-16e-instruct" \
  --provider-url "https://api.groq.com/openai/v1"

# 3. Validate the solution
uv run moulinette_eval validate mbpp ../cache/mbpp_task.json ../cache/mbpp_solution.json
```

### Run the SWE-bench agent

Same flow, with `swebench` and `agent_swebench` (requires Docker):

```bash
uv run moulinette_eval dump swebench --output ../cache/swebench_task.json

uv run python -m agent_swebench \
  --task-file ../cache/swebench_task.json \
  --output  ../cache/swebench_solution.json \
  --model-name "meta-llama/llama-4-scout-17b-16e-instruct" \
  --provider-url "https://api.groq.com/openai/v1"

uv run moulinette_eval validate swebench ../cache/swebench_task.json ../cache/swebench_solution.json
```

> The **moulinette** is the external evaluator provided by the staff (it dumps
> tasks and validates solutions). It is **not** part of this submission; we only
> invoke its CLI.

## System architecture

Five components, five clear responsibilities:

```
                          ┌──────────────────────────────────────┐
                          │            Agent (loop)              │
   ┌────────────┐         │   core/agent/agent.py                │
   │ LLM client │◀────────┤   1. messages → LLM.generate()       │
   │ core/llm   │  text   │   2. extract code                    │
   └────────────┘────────▶│   3. sandbox.execute(code)           │
                          │   4. observation → messages          │
                          │   5. detect FINAL_ANSWER / limits    │
                          └───────────────┬──────────────────────┘
                                          │ code
                                          ▼
                          ┌──────────────────────────────────────┐
                          │      Sandbox  core/sandbox           │
                          │  separate process, builtins stripped,│
                          │  imports/fs/network blocked,         │
                          │  timeout + RLIMIT memory,           │
                          │  final_answer() injected            │
                          └───────────────┬──────────────────────┘
                                          │ tool call (via Pipe)
                                          ▼
                          ┌──────────────────────────────────────┐
                          │      MCP client  core/mcp            │
                          └───────────────┬──────────────────────┘
                                          │ stdio / streamable HTTP
                                          ▼
                  ┌───────────────────────┴────────────────────────┐
                  │  MCP server (separate process)                 │
                  │  mcp_tools_mbpp.py    → run_tests              │
                  │  mcp_tools_swebench.py → Docker-backed tools   │
                  └────────────────────────────────────────────────┘
```

1. **Agent / Orchestrator** — the central loop. Calls the LLM, extracts code,
   feeds it to the sandbox, reads observations, repeats. This is our own
   implementation (no `smolagents` / `langgraph` / `crewai` / `autogen`).
2. **Code Extraction** — transforms the LLM response into executable Python,
   handling several formats (Python blocks, XML, JSON/Hermes, ReAct).
3. **Sandbox** — the execution boundary. Enforces all security restrictions and
   wraps an MCP client.
4. **`final_answer()`** — a sandbox-injected built-in (not an MCP tool), always
   present regardless of the connected server.
5. **MCP server(s)** — separate processes (stdio or HTTP) exposing the tools.

Key boundary: **the sandbox wraps the MCP client, not the other way around.**
The sandbox restricts what the generated Python can do (imports, paths, timeout,
memory); MCP tool *actions* (reading files in Docker, running tests) happen
**outside** the sandbox and are not subject to its timeout.

Directory layout:

```
agent_smith/
├── mcp_tools_mbpp.py        # MBPP MCP server (root, as required)
├── mcp_tools_swebench.py    # SWE-bench MCP server (root)
├── student/                 # the submitted code
│   ├── agent_mbpp.py        # MBPP CLI entrypoint
│   ├── agent_swebench.py    # SWE-bench CLI entrypoint
│   ├── sandbox_cli.py       # standalone sandbox CLI
│   ├── models/              # Pydantic contract (task input / metrics / output)
│   └── core/
│       ├── agent/           # the loop
│       ├── extractor/       # multi-format code extraction
│       ├── sandbox/         # isolated execution + config
│       ├── llm/             # OpenAI-compatible client, key rotation
│       ├── mcp/             # sync wrapper over the async MCP session
│       └── cli/             # shared CLI base
├── benchmark_outputs/       # solution.json files backing the report
└── BENCHMARK_REPORT.md
```

## Agent loop explanation

The loop lives in [`student/core/agent/agent.py`](student/core/agent/agent.py).
For each iteration (up to `max_iterations`):

1. **Check limits** — wall-clock time and cumulative input/output tokens. If a
   budget is about to be exceeded, stop cleanly and return a failed
   `SolutionOutput` (we never overshoot the hard limits).
2. **Generate** — call the LLM with `stop_sequences=["<end_code>",
   "Observation:"]` and a per-call `max_tokens` cap. The stop sequences are
   essential: without them the model **hallucinates** the observation instead of
   waiting for real execution.
3. **Extract code** — `CodeExtractor.extract()` pulls the Python out of the
   response. If no code is found, the observation is an explicit
   `"Error: No code block found."` — the model is never left guessing.
4. **Execute** — `sandbox.execute(code)` returns stdout, an error, or a
   `<<<FINAL_ANSWER:...>>>` marker.
5. **Record + feed back** — a full `StepMetrics` entry is logged (tokens, time,
   model, raw LLM output, code sent, sandbox output, retries) and the
   observation is appended to the conversation.
6. **Final answer** — when `<<<FINAL_ANSWER:...>>>` appears, an optional
   **validator re-runs the real tests**. If the patch/code doesn't actually
   pass, the submission is **rejected** and the failure is fed back; the loop
   continues. Only a genuinely passing answer ends the run with `success=True`.

Two principles drive the design:

- **The LLM never guesses.** Every failure mode — no code, malformed code,
  timeout, truncated tool output, tool error — produces an explicit observation.
- **We don't trust the model's word.** A self-reported "success" is **re-verified**
  by actually re-running the tests (`answer_validator`), so `solution.json`
  reflects a real solve, not a hallucination.

## Sandbox design

Implemented in [`student/core/sandbox/`](student/core/sandbox/) using **only the
standard library** (no `RestrictedPython`).

The sandbox runs untrusted code in a **separate process**
(`multiprocessing.Process`), which lets us truly kill runaway code and isolate
memory. Inside the child (`IsolatedWorker.run`), before executing anything:

| Restriction | Mechanism |
|---|---|
| **Import allowlist** | `builtins.__import__` overridden → only allowlisted modules import, else `ImportError` |
| **Filesystem restriction** | `builtins.open` overridden → only paths under `allowed_directories`, else `PermissionError` |
| **No network** | `socket.socket` replaced → `PermissionError` |
| **Restricted builtins** | `eval`, `exec`, `compile` removed from builtins (user code runs via a reference captured beforehand) |
| **Memory limit** | `resource.setrlimit(RLIMIT_AS, max_memory_mb)` |
| **Execution timeout** | parent polls the pipe with the configured timeout, then `terminate()`s the child |

The parent process (`Sandbox.execute`) communicates with the child over a
`multiprocessing.Pipe`. The child sends `CALL_TOOL` messages (the real MCP call
happens parent-side, outside the sandbox), `FINAL_ANSWER`, `SUCCESS`, or
`ERROR`. Oversized observations are truncated head+tail with an explicit notice.

Limits are configured with a Pydantic `SandboxConfig` (loadable from JSON). The
same config object also **renders the prompt's constraint text**
(`describe_constraints()`), so the enforcement and the prompt can never drift
apart. `final_answer()` is injected by the sandbox itself and is present
regardless of which MCP server is connected.

## Tool implementation details

Tools are exposed by **MCP servers** (`FastMCP`) at the repository root, and the
sandbox manual is **generated dynamically** from each server's tool schemas
(`MCPClient.get_man()`), so an **unknown MCP server** is supported automatically.
Both **stdio** and **streamable HTTP** transports are implemented
([`core/mcp/client.py`](student/core/mcp/client.py)).

**MBPP** ([`mcp_tools_mbpp.py`](mcp_tools_mbpp.py)) — `run_tests(code,
test_list, test_imports)`: assembles imports + code + tests in a temp file and
runs it in a subprocess with a timeout, returning a clear pass/fail report.

**SWE-bench** ([`mcp_tools_swebench.py`](mcp_tools_swebench.py)) — Docker-backed,
all mandatory tools:

| Tool | Implementation |
|---|---|
| `read_file(filepath, start, end)` | `cat` + `cat -n`-style line numbers |
| `edit_file(filepath, old_str, new_str)` | exact-string replace; on miss, returns nearby lines as a hint so the model can copy verbatim |
| `list_files(directory, pattern)` | `find -type f -name` |
| `search_code(pattern, file_pattern)` | `grep -rEn`, `/path:line content`, capped at 100 results |
| `search_function_or_class_definition_in_code(name)` | `search_code("(def|class) name")` |
| `find_references(name)` | `search_code(name)` |
| `run_command(command, workdir)` | bash in the container → stdout/stderr/exit code |
| `get_patch()` | `git -c core.fileMode=false diff` |
| `run_tests()` | runs the evaluation script inside the container |

The container is started lazily and **cleaned up** (`docker rm -f`) on server
shutdown.

## LLM providers and key management

Any OpenAI-compatible `/chat/completions` endpoint works — the provider is
selected purely by `--provider-url` (Groq, OpenRouter, Google AI Studio's
OpenAI-compatible URL…). A single `OpenAICompatibleClient`
([`core/llm/clients.py`](student/core/llm/clients.py)) handles all of them, with:

- **Multiple API keys + rotation** (`KeyManager`): keys are tried in turn; on
  429 the client rotates through all live keys before backing off; on 401/403 a
  key is marked dead for the rest of the run.
- **Provider-aware back-off**: `Retry-After` (Groq), `retry-after-ms`, and
  Gemini-style `retryDelay` in the body are all honored, with a hard wait cap.
- **Usage tracking**: tokens, latency, retries, and request count per step.

## Benchmark results and analysis

We compared **5 models across 3 providers** on the **same 3 SWE-bench tasks**.
Full methodology, tables, and per-step analysis are in
[`BENCHMARK_REPORT.md`](BENCHMARK_REPORT.md); the backing `solution.json` files
are in [`benchmark_outputs/`](benchmark_outputs/).

| Model (provider) | Solve rate | Verdict |
|---|---|---|
| **llama-4-scout-17b** (Groq) | 3/3 | **Selected — primary** (fast, tight exploration, low tokens) |
| **llama-3.3-70b-versatile** (Groq) | 3/3 | **Selected — co-primary** (most token-efficient) |
| deepseek-v4-flash (OpenRouter) | 3/3 | Usable fallback (reliable but explores longer) |
| qwen3-32b (Groq) | 2/3 | Disregarded (reasoning tokens fight the budget) |
| gemma-4-26b-a4b-it (Google AI Studio) | 1/3 | Disregarded (hits output cap, slow) |

**Takeaway:** non-reasoning models on the fastest provider win. Reasoning models
spend their token budget thinking instead of solving, which is a losing trade
under a hard token cap. The forced answer validator is cheap insurance that
makes the pipeline safe to grade.

## Resources

Topic references:

- [SWE-bench](https://www.swebench.com/) and **SWE-bench Verified** — leaderboards
  and per-task traces.
- [MBPP dataset](https://github.com/google-research/google-research/tree/master/mbpp).
- [Model Context Protocol](https://modelcontextprotocol.io/) — the MCP spec and
  Python SDK.
- Provider docs: [Groq](https://groq.com), [OpenRouter](https://openrouter.ai),
  [Google AI Studio](https://ai.google.dev).

### Use of AI

AI assistance (Claude) was used as a coding partner, with every decision
reviewed and owned by us:

- **Prompt engineering** iterations for the agent system prompts (MBPP and
  SWE-bench), validated empirically by inspecting `solution.json` traces.
- **Documentation** (this README, the benchmark report) drafted from the actual
  code and the real run data.

The agent loop, the sandbox security mechanisms, the MCP integration, and all
architectural choices are our own work — AI accelerated the writing, not the
engineering decisions.
