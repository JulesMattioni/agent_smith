from ..llm.clients import BaseClient
from ..extractor.code_extractor import CodeExtractor
from ..sandbox.sandbox import Sandbox
from models.mbpp import StepMetrics, SolutionOutput
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
    ):
        """Initialize the agent.

        Args:
            llm_client: LLM client used to generate responses.
            sandbox: Sandbox used to execute extracted code.
            max_iterations: Maximum number of LLM/sandbox cycles.
        """
        self.llm = llm_client
        self.sandbox = sandbox
        self._max_iterations = max_iterations
        self._max_input_tokens = max_input_tokens
        self._max_output_tokens = max_output_tokens
        self._max_total_time_seconds = max_total_time_seconds

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
        self, task: str, system_prompt: str, task_id: str, benchmark: str
    ) -> SolutionOutput:
        """Run the agent loop until a final answer or max iterations.

        Args:
            task: The task description shown to the LLM.
            system_prompt: The system prompt prepended to conversation.
            task_id: Unique identifier for the task.
            benchmark: Benchmark name ('mbpp' or 'swebench').

        Returns:
            A SolutionOutput with the final answer and step metrics.
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task},
        ]

        steps = []
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
                response = self.llm.generate(messages)
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
                print(extracted_code)
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
