import json
import os
import re
import sys
from student.core.cli.base_agent import BaseAgentCLI
from student.models.swebench import SWEBenchTaskInput
from student.core.llm.clients import OpenAICompatibleClient
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

    def run(self) -> None:
        """Set up the agent components and solve the SWE-bench task."""
        task_input = self._load_task()

        os.environ["SWE_DOCKER_IMAGE"] = task_input.docker_image
        os.environ["SWE_EVAL_SCRIPT"] = task_input.eval_script

        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        server = os.path.join(repo_root, "mcp_tools_swebench.py")
        mcp_client = MCPClient(command=f"python {server}")
        mcp_client.connect()

        client = OpenAICompatibleClient(
            model_name=self.args.model_name,
            base_url=self.args.provider_url,
        )
        config = SandboxConfig(max_execution_time_seconds=30)
        sandbox = Sandbox(config, mcp_client)
        agent = Agent(
            client, sandbox, max_iterations=30, max_tokens_per_call=2048
        )

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
            "```python code block, and end that block with the marker"
            " <end_code> on its own line.\n"
            "Write EXACTLY ONE code block per turn, then STOP and wait."
            " Do NOT write more code, and do NOT invent or predict the"
            " Observation yourself: the sandbox will run your code and"
            " give you the real output.\n"
            "This code will be executed in a sandbox, and you will"
            " receive the standard output (Observation).\n"
            "You can use persistent variables, loops, and conditional"
            " logic.\n"
            "You can use `print()` to observe variables and results.\n"
            f"\n{sandbox.get_man()}\n"
            "\nEach tool is a plain Python function. Call it directly by"
            " its name with keyword arguments. Do NOT prefix it with a"
            " module or object (write `search_code(...)`, never"
            " `search_code.search_code(...)`).\n"
            "Example turn:\n"
            "```python\n"
            'result = search_code(pattern="CheckConstraint")\n'
            "print(result)\n"
            "```\n"
            "<end_code>\n"
            f"\n{config.describe_constraints()}\n"
            "\nIMPORTANT RULES:\n"
            "- Be concise. Write only the necessary code for the"
            " current step.\n"
            "- Explore the code, read files, and test your hypotheses"
            " step by step.\n"
            "- Do NOT guess the patch without reading the code first.\n"
            "- Once you have completely fixed the issue, call"
            " `final_answer(get_patch())`."
        )

        def validate_answer(patch: str) -> str | None:
            """Run the real evaluation script against the submitted patch.

            The task input does not expose the FAIL_TO_PASS/PASS_TO_PASS
            test list, so correctness is judged by requiring BOTH a clean
            exit code AND the absence of failure markers in the report
            (some eval scripts, e.g. sympy's bin/test, return exit code 0
            even when tests fail). This rejects a final_answer whose patch
            does not actually make the tests pass.
            """
            result = mcp_client.call_tool("run_tests", {})
            exit_match = re.search(r"EXIT_CODE:\s*(-?\d+)", result)
            exit_ok = exit_match.group(1) == "0" if exit_match else True
            failure_markers = re.search(
                r"\[FAIL\]"
                r"|FAILED \("
                r"|\d+ failed"
                r"|=+ FAILURES =+"
                r"|Traceback \(most recent",
                result,
            )
            if exit_ok and not failure_markers:
                return None
            tail = result if len(result) <= 4000 else result[-4000:]
            return (
                "final_answer rejected: the evaluation tests did not pass.\n"
                f"{tail}\n"
                "Inspect the failures, fix the code with edit_file, verify "
                "with run_tests(), then call final_answer(get_patch()) again."
            )

        res = agent.run(
            task=task,
            system_prompt=system_prompt,
            task_id=str(task_input.instance_id),
            benchmark="swebench",
            answer_validator=validate_answer,
        )

        self._save_output(res)


def main() -> None:
    """Entrypoint: build the SWE-bench agent CLI and run it."""
    try:
        cli = SWEBenchAgentCLI()
        cli.run()
    except Exception as e:
        print(e, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
