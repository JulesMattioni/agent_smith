import json
import dotenv
from models.mbpp import MBPPTaskInput
from core.llm.clients import OpenRouterClient
from core.sandbox.sandbox import Sandbox
from core.sandbox.config import SandboxConfig
from core.agent.agent import Agent
from core.mcp.client import MCPClient
from core.cli.base_agent import BaseAgentCLI


class MBPPAgentCLI(BaseAgentCLI):
    def _load_task(self) -> MBPPTaskInput:
        with open(self.args.task_file) as f:
            return MBPPTaskInput(**json.load(f))

    def run(self):
        task_input = self._load_task()
        client = OpenRouterClient(
            model_name=self.args.model_name,
            provider_name="groq",
            base_url=self.args.provider_url,
        )
        config = SandboxConfig(max_execution_time_seconds=10)
        sandbox = Sandbox(config, MCPClient("mbpp"))
        agent = Agent(client, sandbox)

        task = f"""Solve the following Python programming task:

Task: {task_input.task_definition}

You must implement this function:
{task_input.function_definition}

These are SOME tests (not all) your solution must pass:
{chr(10).join(task_input.test_list)}

Instructions:
1. Write a correct and general implementation
2. Run the visible tests to verify they pass
3. Think about edge cases not covered by the visible tests
4. Call final_answer() with the COMPLETE function source code as a string

IMPORTANT: final_answer() must receive the complete function code, like this:
final_answer(\"\"\"def {task_input.function_definition.split('(')[0].replace('def ', '')}(...):
    # your implementation here
\"\"\")
"""

        system_prompt = f"""You are an autonomous coding agent.
To solve the user's task, you must write Python code inside a ```python code block.
This code will be executed in a sandbox, and you will receive the standard output (Observation).
You can use `print()` to observe variables and results.
Once you have the final answer, call the function `final_answer("your result")`.

{sandbox.mcp_client.get_man()}

IMPORTANT: Be concise. Write minimal code without docstrings, comments, or unnecessary validations."""

        res = agent.run(
            task=task,
            system_prompt=system_prompt,
            task_id=str(task_input.task_id),
            benchmark="mbpp",
        )

        self._save_output(res)


if __name__ == "__main__":
    dotenv.load_dotenv()
    cli = MBPPAgentCLI()
    cli.run()
