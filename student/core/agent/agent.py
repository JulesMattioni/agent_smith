from ..llm.clients import BaseClient
from ..extractor.code_extractor import CodeExtractor
from ..sandbox.sandbox import Sandbox
import re


class Agent:
    def __init__(
        self,
        llm_client: BaseClient,
        sandbox: Sandbox,
        max_iterations: int = 10,
    ):
        self.llm = llm_client
        self.max_iterations = max_iterations
        self.sandbox = sandbox

    def run(self, task: str, system_prompt: str):
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task},
        ]
        for i in range(self.max_iterations):
            print(f"\n{'-'*20} ITERATION {i+1} {'-'*20}")

            response = self.llm.generate(messages)
            extracted_code = CodeExtractor.extract(response.content)

            if extracted_code is None:
                observation = (
                    "Error: No code block found in your response. "
                    "Please respond with a ```python code block."
                )
                print("No code generated.")
            else:
                print(f"Exectuting following code:\n{extracted_code}\n")
                observation = self.sandbox.execute(extracted_code)
                print(f"Sandbox observation:\n{observation}\n")

            final_match = re.search(
                r"<<<FINAL_ANSWER:(.*?)>>>", observation, re.DOTALL
            )
            if final_match:
                answer = final_match.group(1).strip()
                print(f"\nTask completed! Final Answer is: {answer}")
                return answer

            messages.append({"role": "assistant", "content": response.content})
            messages.append(
                {"role": "user", "content": f"Observation: {observation}"}
            )

        print("Max iterations reached.")
        return None
