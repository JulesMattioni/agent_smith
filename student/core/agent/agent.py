from ..llm.clients import BaseClient
from ..extractor.code_extractor import CodeExtractor
from ..sandbox.sandbox import Sandbox
from models.mbpp import StepMetrics, SolutionOutput
import re
import time


class Agent:
    def __init__(
        self,
        llm_client: BaseClient,
        sandbox: Sandbox,
        max_iterations: int = 10,
    ):
        self.llm = llm_client
        self.sandbox = sandbox
        self.max_iterations = max_iterations

    def run(
        self, task: str, system_prompt: str, task_id: str, benchmark: str
    ) -> SolutionOutput:
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

        for i in range(self.max_iterations):
            response = self.llm.generate(messages)
            total_requests += 1
            total_input_tokens += response.input_tokens
            total_output_tokens += response.output_tokens

            extracted_code = CodeExtractor.extract(response.content)

            if extracted_code is None:
                observation = "Error: No code block found."
                sandbox_input = ""
            else:
                last_code = extracted_code
                observation = self.sandbox.execute(extracted_code)
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
            iterations=self.max_iterations,
            total_requests=total_requests,
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
            total_time_seconds=time.time() - start_time,
            steps=steps,
            error="Max iterations reached.",
        )
