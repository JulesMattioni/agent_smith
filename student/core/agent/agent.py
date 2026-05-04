from ..llm.clients import BaseClient
from ..extractor.code_extractor import CodeExtractor


class Agent:
    def __init__(self, llm_client: BaseClient, max_iterations: int = 10):
        self.llm = llm_client
        self.max_iterations = max_iterations

    def run(self, task: str, system_prompt: str):
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task},
        ]
        for i in range(self.max_iterations):

            response = self.llm.generate(messages)
            extracted_code = CodeExtractor.extract(response.content)

            if extracted_code is None:
                observation = ("Error: No code block found in your response. "
                               "Please respond with a ```python code block.")
            else:
                observation = "OK"

            messages.append({"role": "assistant", "content": response.content})
            messages.append(
                {"role": "user", "content": f"Observation: {observation}"}
            )
            if extracted_code and "final_answer" in extracted_code:
                print("Task completed!")
                return extracted_code
        return extracted_code
