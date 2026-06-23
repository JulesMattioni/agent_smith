import dotenv
import json
import os
from student.core.cli.base_agent import BaseAgentCLI
from models.swebench import SWEBenchTaskInput
from student.core.llm.clients import GroqClient
from student.core.sandbox.sandbox import Sandbox
from student.core.sandbox.config import SandboxConfig
from student.core.agent.agent import Agent
from student.core.mcp.client import MCPClient


class SWEBenchAgentCLI(BaseAgentCLI):
    """CLI entrypoint for running an agent on SWE-bench tasks."""

    def _load_task(self) -> SWEBenchTaskInput:
        """Load a SWE-bench task from the JSON file specified in args.

        Returns:
            A populated SWEBenchTaskInput instance.
        """
        with open(self.args.task_file) as f:
            return SWEBenchTaskInput(**json.load(f))

    def run(self):
        """Set up the agent components and solve the SWE-bench task."""
        task_input = self._load_task()

        os.environ["SWE_DOCKER_IMAGE"] = task_input.docker_image
        os.environ["SWE_EVAL_SCRIPT"] = task_input.eval_script

        mcp_client = MCPClient(command="python mcp_tools_swebench.py")
        mcp_client.connect()

        client = GroqClient(
            model_name=self.args.model_name,
            provider_name="groq",
            base_url=self.args.provider_url,
        )
        config = SandboxConfig(max_execution_time_seconds=30)
        sandbox = Sandbox(config, mcp_client)
        agent = Agent(client, sandbox, max_iterations=30)

        task = (
            f"Solve the following GitHub issue in the repository"
            f" {task_input.repo}:\n"
            f"\nIssue Statement:\n{task_input.problem_statement}"
            f"\n\nHints:\n{task_input.hints_text}"
            "\n\nInstructions:\n"
            "1. Use the provided tools (like search_code, read_file)"
            " to explore the codebase and find where the bug is located.\n"
            "2. Use the edit_file or run_command tools to modify the"
            " code and fix the bug.\n"
            "3. Use the run_tests() tool to execute the evaluation"
            " script and verify your fix.\n"
            "4. Once the bug is fixed and tests pass, submit your"
            " solution.\n"
            "\nIMPORTANT: To submit your solution, you MUST use the"
            " get_patch() tool to generate the diff, and pass it"
            " directly to final_answer like this:\n"
            "final_answer(get_patch())\n"
        )

        system_prompt = (
            "You are an autonomous coding agent specializing in bug"
            " fixing.\n"
            "To solve the user's task, you must write Python code"
            " inside a\n"
            "```python code block.\n"
            "This code will be executed in a sandbox, and you will"
            " receive the standard output (Observation).\n"
            "You can use persistent variables, loops, and conditional"
            " logic.\n"
            "You can use `print()` to observe variables and results.\n"
            f"\n{mcp_client.get_man()}\n"
            "\nIMPORTANT RULES:\n"
            "- Be concise. Write only the necessary code for the"
            " current step.\n"
            "- Explore the code, read files, and test your hypotheses"
            " step by step.\n"
            "- Do NOT guess the patch without reading the code first.\n"
            "- Once you have completely fixed the issue, call"
            " `final_answer(get_patch())`."
        )

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
