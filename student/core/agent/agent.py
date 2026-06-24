from ..llm.clients import BaseClient
from ..extractor.code_extractor import CodeExtractor
from ..sandbox.sandbox import Sandbox
from ...models.mbpp import StepMetrics, SolutionOutput
from typing import Callable, Optional
import re
import time


class Agent:
    """Autonomous agent that iterates between an LLM and a sandbox."""

    def __init__(
        self,
        llm_client: BaseClient,
        sandbox: Sandbox,
        max_iterations: int = 30,
        max_input_tokens: int = 300000,
        max_output_tokens: int = 10000,
        max_total_time_seconds: float = 900,
        max_tokens_per_call: Optional[int] = None,
    ):
        """Initialize the agent.

        Args:
            llm_client: LLM client used to generate responses.
            sandbox: Sandbox used to execute extracted code.
            max_iterations: Maximum number of LLM/sandbox cycles.
            max_input_tokens: Total input-token budget for the whole run.
            max_output_tokens: Total output-token budget for the whole run.
            max_total_time_seconds: Wall-clock budget for the whole run.
            max_tokens_per_call: Hard cap on output tokens for a SINGLE
                request. Providers count this reservation against their
                per-minute token quota (prompt + max_tokens), so a large
                value can trip free-tier TPM limits. Defaults to
                max_output_tokens to preserve previous behavior.
        """
        self.llm = llm_client
        self.sandbox = sandbox
        self._max_iterations = max_iterations
        self._max_input_tokens = max_input_tokens
        self._max_output_tokens = max_output_tokens
        self._max_total_time_seconds = max_total_time_seconds
        self._max_tokens_per_call = max_tokens_per_call or max_output_tokens

    def _check_limits(
        self,
        total_input_tokens: int,
        total_output_tokens: int,
        time_elapsed: float,
        steps: list[StepMetrics],
    ) -> str | None:
        if time_elapsed >= self._max_total_time_seconds:
            return "Time limit reached."
        if total_output_tokens >= self._max_output_tokens:
            return "Output token limit reached."
        next_cost = steps[-1].input_tokens if steps else 0
        if next_cost + total_input_tokens >= self._max_input_tokens:
            return "Input token limit reached."
        return None

    def run(
        self,
        task: str,
        system_prompt: str,
        task_id: str,
        benchmark: str,
        answer_validator: Optional[Callable[[str], Optional[str]]] = None,
    ) -> SolutionOutput:
        """Run the agent loop until a final answer or max iterations.

        Args:
            task: The task description shown to the LLM.
            system_prompt: The system prompt prepended to conversation.
            task_id: Unique identifier for the task.
            benchmark: Benchmark name ('mbpp' or 'swebench').
            answer_validator: Optional callback invoked with the submitted
                answer when final_answer() fires. It returns None to accept
                the answer, or a rejection message (fed back to the LLM as
                an observation) to reject it and keep iterating. This lets
                the harness enforce correctness instead of trusting the
                model's self-reported success.

        Returns:
            A SolutionOutput with the final answer and step metrics.
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task},
        ]

        steps: list[StepMetrics] = []
        total_input_tokens = 0
        total_output_tokens = 0
        total_requests = 0
        start_time = time.time()
        last_code = ""

        for i in range(self._max_iterations):
            stop = self._check_limits(
                total_input_tokens,
                total_output_tokens,
                time.time() - start_time,
                steps,
            )
            if stop:
                return SolutionOutput(
                    task_id=task_id,
                    benchmark=benchmark,
                    success=False,
                    solution=last_code,
                    system_prompt=system_prompt,
                    iterations=len(steps),
                    total_requests=total_requests,
                    total_input_tokens=total_input_tokens,
                    total_output_tokens=total_output_tokens,
                    total_time_seconds=time.time() - start_time,
                    steps=steps,
                    error=stop,
                )
            try:
                response = self.llm.generate(
                    messages,
                    stop_sequences=["<end_code>", "Observation:"],
                    max_tokens=self._max_tokens_per_call,
                )
            except Exception as e:
                return SolutionOutput(
                    task_id=task_id,
                    benchmark=benchmark,
                    success=False,
                    solution=last_code,
                    system_prompt=system_prompt,
                    iterations=len(steps),
                    total_requests=total_requests,
                    total_input_tokens=total_input_tokens,
                    total_output_tokens=total_output_tokens,
                    total_time_seconds=time.time() - start_time,
                    steps=steps,
                    error=f"LLM generation error: {e}",
                )
            total_requests += 1
            total_input_tokens += response.input_tokens
            total_output_tokens += response.output_tokens

            extracted_code = CodeExtractor.extract(response.content)

            if extracted_code is None:
                observation = "Error: No code block found."
                sandbox_input = ""
            else:
                last_code = extracted_code
                try:
                    observation = self.sandbox.execute(extracted_code)
                except Exception as e:
                    observation = f"Error while executing code in sandbox: {e}"
                sandbox_input = extracted_code

            steps.append(
                StepMetrics(
                    step=i + 1,
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                    request_time_ms=response.request_time_ms,
                    api_url=self.llm.base_url,
                    model_name=self.llm.model_name,
                    llm_output=response.content,
                    sandbox_input=sandbox_input,
                    sandbox_output=observation,
                    retries=response.attempts,
                )
            )

            messages.append({"role": "assistant", "content": response.content})
            messages.append(
                {"role": "user", "content": f"Observation: {observation}"}
            )

            final_match = re.search(
                r"<<<FINAL_ANSWER:(.*?)>>>", observation, re.DOTALL
            )
            if final_match:
                answer = final_match.group(1).strip()
                if not answer:
                    hint = (
                        " get_patch() likely returned an empty diff: inspect"
                        " the code with read_file/search_code, apply a real"
                        " change with edit_file, then retry."
                        if benchmark == "swebench"
                        else " Provide the complete solution before calling"
                        " final_answer() again."
                    )
                    messages[-1] = {
                        "role": "user",
                        "content": (
                            "Observation: final_answer() received an empty "
                            "result, which is not accepted." + hint
                        ),
                    }
                    continue
                if answer_validator is not None:
                    try:
                        rejection = answer_validator(answer)
                    except Exception as e:
                        rejection = (
                            "final_answer could not be validated: "
                            f"{e}. Fix the issue and try again."
                        )
                    if rejection:
                        messages[-1] = {
                            "role": "user",
                            "content": "Observation: " + rejection,
                        }
                        continue
                return SolutionOutput(
                    task_id=task_id,
                    benchmark=benchmark,
                    success=True,
                    solution=answer,
                    system_prompt=system_prompt,
                    iterations=i + 1,
                    total_requests=total_requests,
                    total_input_tokens=total_input_tokens,
                    total_output_tokens=total_output_tokens,
                    total_time_seconds=time.time() - start_time,
                    steps=steps,
                )

        return SolutionOutput(
            task_id=task_id,
            benchmark=benchmark,
            success=False,
            solution=last_code,
            system_prompt=system_prompt,
            iterations=self._max_iterations,
            total_requests=total_requests,
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
            total_time_seconds=time.time() - start_time,
            steps=steps,
            error="Max iterations reached.",
        )
