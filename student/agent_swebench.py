import dotenv
import json
from core.cli.base_agent import BaseAgentCLI
from models.swebench import SWEBenchTaskInput
from core.llm.clients import OpenRouterClient
from core.sandbox.sandbox import Sandbox
from core.sandbox.config import SandboxConfig
from core.agent.agent import Agent
# from core.mcp.client import MCPClient


class SWEBenchAgentCLI(BaseAgentCLI):

    def _load_task(self) -> SWEBenchTaskInput:
        with open(self.args.task_file) as f:
            return SWEBenchTaskInput(**json.load(f))

    def run(self):
        task_input = self._load_task()

        # Configuration spécifique SWE-bench
        client = OpenRouterClient(
            model_name=self.args.model_name,
            provider_name="groq",
            base_url=self.args.provider_url,
        )
        config = SandboxConfig(max_execution_time_seconds=30)
        sandbox = Sandbox(config, None)
        agent = Agent(
            client, sandbox, max_iterations=30
        )

        task = f"""Solve the following GitHub issue in the repository {task_input.repo}:

Issue Statement:
{task_input.problem_statement}

Hints:
{task_input.hints_text}

Instructions:
1. Use the provided tools (like search_code, read_file) to explore the codebase and find where the bug is located.
2. Use the edit_file or run_command tools to modify the code and fix the bug.
3. Use the run_tests() tool to execute the evaluation script and verify your fix.
4. Once the bug is fixed and tests pass, submit your solution.

IMPORTANT: To submit your solution, you MUST use the get_patch() tool to generate the diff, and pass it directly to final_answer like this:
final_answer(get_patch())
"""

        system_prompt = f"""You are an autonomous coding agent specializing in bug fixing.
To solve the user's task, you must write Python code inside a
```python code block.
This code will be executed in a sandbox, and you will receive the standard output (Observation).
You can use persistent variables, loops, and conditional logic.
You can use `print()` to observe variables and results.

IMPORTANT RULES:
- Be concise. Write only the necessary code for the current step.
- Explore the code, read files, and test your hypotheses step by step.
- Do NOT guess the patch without reading the code first.
- Once you have completely fixed the issue, call `final_answer(get_patch())`.
"""

        res = agent.run(
            task=task,
            system_prompt=system_prompt,
            task_id=str(task_input.instance_id),
            benchmark="swebench",
        )

        self._save_output(res)


if __name__ == "__main__":
    dotenv.load_dotenv()
    cli = SWEBenchAgentCLI()
    cli.run()
