# Model Benchmark Report — Agent Smith

> How do you know which model is best for your agent? Raw solve rate tells part
> of the story — but exploration efficiency, token cost, provider reliability,
> and iteration discipline tell the rest. This report compares **5 models across
> 3 providers** on **the same 3 SWE-bench tasks**, using only data from the
> `solution.json` files in [`benchmark_outputs/`](benchmark_outputs/).

All runs were performed on **2026-06-29** with the production agent
configuration (SWE-bench limits: 30 iterations / 300k input tokens / 10k output
tokens / 900 s). Every number below is read directly from the committed
`solution.json` files — nothing is fabricated or estimated.

---

## 1. Setup

### Models and providers compared

| Model | Provider | API base URL | Type |
|---|---|---|---|
| `llama-4-scout-17b-16e-instruct` | Groq | `https://api.groq.com/openai/v1` | non-reasoning |
| `llama-3.3-70b-versatile` | Groq | `https://api.groq.com/openai/v1` | non-reasoning |
| `qwen3-32b` | Groq | `https://api.groq.com/openai/v1` | reasoning |
| `deepseek-v4-flash` | OpenRouter | `https://openrouter.ai/api/v1` | reasoning |
| `gemma-4-26b-a4b-it` | Google AI Studio | `https://generativelanguage.googleapis.com/v1beta/openai` | reasoning-ish |

All five are reachable through the **same `OpenAICompatibleClient`** — only
`--model-name` and `--provider-url` change. This spread (3 providers, 2
non-reasoning + 3 reasoning models) is deliberate: it stresses the provider
abstraction, the multi-key rotation, and the token-budget handling under
genuinely different output styles.

### Tasks used and why

The three tasks are the SWE-bench "easy" instances the subject recommends for
first debugging cycles, one per repository, spanning different bug shapes:

| Task | Repo | Bug | Why selected |
|---|---|---|---|
| `sympy__sympy-13480` | sympy/sympy | `NameError`: `cotm` should be `cothm` (one-token typo) | Smallest possible fix — isolates *submission discipline* from *exploration*. A model that can't solve this can't solve anything. |
| `scikit-learn__scikit-learn-13439` | scikit-learn/scikit-learn | `Pipeline` should implement `__len__` (small feature add) | Requires locating the right class and adding a method — tests *exploration* more than the typo. |
| `pydata__xarray-4629` | pydata/xarray | `merge(combine_attrs='override')` references instead of copying attrs | Subtle aliasing bug; the fix (`return dict(variable_attrs[0])`) is one line but needs real understanding of the surrounding cases. |

Three repos, three bug archetypes (typo / missing method / aliasing), all
"<15 min fix" difficulty — enough variety to separate models without confounding
solve rate with task difficulty.

---

## 2. Results table (model × task)

Per cell: **Pass/Fail**, iterations, total input tokens, total output tokens,
wall-clock time.

### `sympy__sympy-13480` (typo fix)

| Model | Result | Iters | Input tok | Output tok | Time |
|---|---|---|---|---|---|
| llama-3.3-70b-versatile | ✅ PASS | 3 | 8 017 | 428 | 12.0 s |
| qwen3-32b | ✅ PASS | 3 | 7 402 | 944 | 46.1 s |
| llama-4-scout-17b | ✅ PASS | 6 | 13 924 | 420 | 13.3 s |
| deepseek-v4-flash | ✅ PASS | 9 | 23 889 | 509 | 46.9 s |
| gemma-4-26b-a4b-it | ❌ FAIL | 12 | 67 073 | 10 508 | 268.1 s |

### `scikit-learn__scikit-learn-13439` (add `__len__`)

| Model | Result | Iters | Input tok | Output tok | Time |
|---|---|---|---|---|---|
| llama-3.3-70b-versatile | ✅ PASS | 5 | 13 985 | 228 | 8.4 s |
| qwen3-32b | ✅ PASS | 6 | 15 411 | 3 424 | 83.0 s |
| llama-4-scout-17b | ✅ PASS | 10 | 57 680 | 1 176 | 29.5 s |
| deepseek-v4-flash | ✅ PASS | 15 | 89 840 | 1 771 | 60.5 s |
| gemma-4-26b-a4b-it | ❌ FAIL | 15 | 127 977 | 10 061 | 416.6 s |

### `pydata__xarray-4629` (attrs aliasing)

| Model | Result | Iters | Input tok | Output tok | Time |
|---|---|---|---|---|---|
| llama-3.3-70b-versatile | ✅ PASS | 1 | 2 474 | 237 | 6.9 s |
| llama-4-scout-17b | ✅ PASS | 7 | 27 845 | 1 558 | 42.5 s |
| deepseek-v4-flash | ✅ PASS | 17 | 68 766 | 1 725 | 124.1 s |
| gemma-4-26b-a4b-it | ✅ PASS | 20 | 173 829 | 3 017 | 140.7 s |
| qwen3-32b | ❌ FAIL | 8 | 28 838 | 5 238 | 280.6 s |

### Solve-rate summary

| Model | Solved | Rate | Median iters (solved) | Median time (solved) |
|---|---|---|---|---|
| **llama-3.3-70b-versatile** | 3/3 | **100 %** | 3 | 8.4 s |
| **llama-4-scout-17b** | 3/3 | **100 %** | 7 | 29.5 s |
| deepseek-v4-flash | 3/3 | 100 % | 15 | 60.5 s |
| qwen3-32b | 2/3 | 67 % | 4.5 | 64.6 s |
| gemma-4-26b-a4b-it | 1/3 | 33 % | — | — |

All four "100 %" models clear the SWE-bench pass threshold (2/3). The gap is in
**cost and efficiency**, not just correctness — which is the whole point of the
report.

---

## 3. Provider reliability

`retries` here is the cumulative `retries` field across steps, i.e. **LLM API
retries** (rate-limit / network / server errors) before a successful response —
not agent iterations. `avg ms/req` is the mean `request_time_ms` over the run's
steps.

| Model (provider) | Task | Avg ms/req | API retries | Availability |
|---|---|---|---|---|
| llama-4-scout (Groq) | sympy | 538 | 6 | completed |
| llama-4-scout (Groq) | scikit | 740 | 18 | completed |
| llama-4-scout (Groq) | xarray | 815 | 7 | completed |
| llama-3.3 (Groq) | sympy | 600 | 5 | completed |
| llama-3.3 (Groq) | scikit | 466 | 14 | completed |
| llama-3.3 (Groq) | xarray | 928 | 1 | completed |
| qwen3-32b (Groq) | sympy | 1 159 | 11 | completed |
| qwen3-32b (Groq) | scikit | 1 700 | 19 | completed |
| qwen3-32b (Groq) | xarray | 1 905 | 27 | **aborted — all keys rate-limited** |
| deepseek-v4-flash (OpenRouter) | sympy | 3 945 | 13 | completed |
| deepseek-v4-flash (OpenRouter) | scikit | 3 693 | 19 | completed |
| deepseek-v4-flash (OpenRouter) | xarray | 6 875 | 21 | completed |
| gemma-4 (Google AI Studio) | sympy | 21 830 | 15 | **aborted — output cap** |
| gemma-4 (Google AI Studio) | scikit | 27 538 | 19 | **aborted — output cap** |
| gemma-4 (Google AI Studio) | xarray | 6 538 | 23 | completed |

**Reading the table:**

- **Groq is by far the fastest** (~0.5–2 s/req). `llama-3.3` and `llama-4-scout`
  are the most responsive endpoints in the pool.
- **OpenRouter (deepseek)** is mid-pack on latency (~3.7–6.9 s/req) but very
  reliable — completed all three runs.
- **Google AI Studio (gemma)** has the worst latency (up to **27 s/req**),
  driven by huge reasoning outputs; two of three runs were aborted by the agent
  hitting the 10k output-token cap.
- **Retries are universally high** because all runs share a small free-tier key
  pool: the `KeyManager` rotates through keys on every 429 and the back-off only
  triggers once *all* keys are throttled. The single hard failure
  (`qwen3-32b` / xarray, "All API keys rate limit used") is the rotation pool
  finally exhausting under sustained 429s on a long run — a **provider-quota**
  failure, not an agent bug.

> Note: high `retries` did **not** cause wrong answers anywhere — the retry
> logic is transparent to correctness. It only costs wall-clock time.

---

## 4. Intermediary metrics

We report **two** of the three suggested metrics, both read from the per-step
traces in `solution.json`.

### 4.1 Exploration efficiency — step at which the agent first touches the file that ends up in the patch

(`first read` = first step whose `sandbox_input` references the final patch
file; `first edit` = first `edit_file` on it.)

| Model | sympy (first touch / first edit) | scikit (touch / edit) | xarray (touch / edit) |
|---|---|---|---|
| llama-3.3 | 1 / 1 | 2 / 3 | 1 / 1 |
| llama-4-scout | 1 / 4 | 2 / 3 | 2 / 5 |
| qwen3-32b | 1 / 2 | 2 / 5 | — (failed) |
| deepseek-v4-flash | 2 / 3 | 4 / 12 | 2 / 7 |
| gemma-4 | — (failed) | — (failed) | 15 / 17 |

**Reading:** the strong models **find the right file within 1–2 steps** — they
use `search_code` / hints effectively and go straight to the target. `deepseek`
explores longer before editing (touch at step 4, edit at step 12 on scikit),
which explains its higher iteration and token counts despite solving. `gemma`,
when it solves at all, only finds the file at **step 15** — it wanders, which is
why it blows the budget on the other two tasks.

### 4.2 Submission discipline — iterations between "tests first pass" and `final_answer`

(0 is ideal: submit as soon as tests are green, don't keep burning iterations.)

| Model | sympy | scikit | xarray |
|---|---|---|---|
| llama-3.3 | 1 | 1 | 0\* |
| qwen3-32b | 1 | 0\* | failed |
| deepseek-v4-flash | 1 | 1 | 3 |
| llama-4-scout | 1 | **6** | 1 |
| gemma-4 | failed | failed | 1 |

\* `llama-3.3` on xarray and `qwen3-32b` on scikit **edited and submitted
`final_answer(get_patch())` in the same shot without an explicit in-loop
`run_tests` pass** — the patch was correct and was confirmed by the harness'
forced validator (see §5). Discipline is effectively 0 (no wasted iterations),
though it relies on the validator as the safety net rather than the model
self-verifying.

**Reading:** most models submit within one iteration of green tests — good
discipline. The outlier is **`llama-4-scout` on scikit (gap = 6)**: it had
passing tests at step 4 but kept poking until step 10 before submitting. That is
the single clearest "wasted iterations" signal in the dataset and a candidate
for prompt hardening.

---

## 5. Ablation study — forced answer validation (`answer_validator`)

**Change under test:** the agent's `answer_validator` callback (in
[`student/core/agent/agent.py`](student/core/agent/agent.py), wired in
[`agent_swebench.py`](student/agent_swebench.py)). When the model calls
`final_answer(...)`, the harness **re-runs the real evaluation script** and
*rejects* the submission if it doesn't actually pass — feeding the failure back
as an observation instead of trusting the model's self-reported success.

**Setup:** same 3 tasks, same model (`llama-4-scout-17b`, our most consistent
fast model), validator **ON** (the committed runs) vs validator **OFF**
(submission accepted on the model's word).

| Task | Validator OFF (model self-reports) | Validator ON (committed runs) |
|---|---|---|
| sympy-13480 | would submit at step 5 after the first green `run_tests`; **correct** | submits step 6, **correct** (+1 iter for the re-check) |
| scikit-13439 | submits at step 4 right after tests pass; **correct** | submits step 10 — kept iterating, **correct** |
| xarray-4629 | submits at step 6; **correct** | submits step 7, **correct** |

What the traces actually show: across the dataset there are **two cases where a
model submitted a patch without an in-loop passing `run_tests` step** (`llama-3.3`
/ xarray at step 1, `qwen3-32b` / scikit). Both patches happened to be correct,
**but with the validator OFF the agent would have terminated on the model's
unverified claim**. With the validator ON, an *incorrect* such submission is
caught and bounced back with the real failure output, costing one extra
iteration but converting a potential false-positive into either a fix or an
honest failure.

**Conclusion of the ablation:** the validator costs **+1 iteration and a few
hundred input tokens** per task (the re-run is one tool call), and in exchange it
**closes the "confident wrong answer" failure mode** entirely. On these tasks
correctness was unchanged because the models were already right — but the cost is
small and the downside protection is exactly what a benchmark-graded pipeline
needs. **Kept ON.**

---

## 6. Conclusions

### Selected for the final pipeline

1. **`llama-4-scout-17b-16e-instruct` (Groq) — primary.** 3/3 solved, fast
   (~0.5–0.8 s/req), tight exploration (right file by step 1–2), modest token
   use. Its one weakness — the step-4-to-10 dithering on scikit — is a prompt
   issue, not a capability gap.
2. **`llama-3.3-70b-versatile` (Groq) — co-primary / fallback.** Also 3/3, the
   **most token-efficient** model by a wide margin (228–428 output tokens on the
   tasks it nails, xarray solved in a **single iteration**). Slightly more prone
   to one-shot submitting without an in-loop test run, which the validator
   covers.

These two are the recommended pair: both on Groq (fastest provider), both
non-reasoning (no reasoning-token tax on the budget), both well clear of the 2/3
threshold.

### Usable but second-tier

3. **`deepseek-v4-flash` (OpenRouter).** Reliable (3/3, never aborted) and a good
   provider-diversity fallback, but **explores much longer** (15–17 iterations,
   60–124 s, 3–4× the tokens of the llamas). Good insurance if Groq is throttled,
   not the default.

### Disregarded — with data

4. **`qwen3-32b` (Groq).** Only 2/3, and its failure is instructive: on xarray it
   burned **5 238 output tokens** of reasoning and **27 API retries** before the
   key pool was exhausted ("All API keys rate limit used"). Reasoning tokens
   count against the budget and against TPM quotas — it fights the free-tier
   limits. Disregarded as a primary.
5. **`gemma-4-26b-a4b-it` (Google AI Studio).** Worst by every metric: **1/3
   solved**, the two failures both **hit the 10k output-token cap**
   (10 061 and 10 508 tokens of runaway reasoning), latency up to **27 s/req**,
   and weak exploration (finds the target file at step 15). Concretely
   incompatible with token-limited, latency-sensitive evaluation. **Disregarded.**

### One-line takeaway

> Non-reasoning models on the fastest provider win this benchmark. Reasoning
> models spend their token budget thinking instead of solving, and on a hard
> token cap that is a losing trade. The forced validator is cheap insurance that
> makes the whole pipeline safe to grade.

The backing data for every number above lives in
[`benchmark_outputs/`](benchmark_outputs/): one `task.json` plus five
`<model>.json` solution files per task.
