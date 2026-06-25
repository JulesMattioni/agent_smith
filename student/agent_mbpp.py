import json
import dotenv
import sys
from student.models.mbpp import MBPPTaskInput
from student.core.llm.clients import OpenAICompatibleClient
from student.core.sandbox.sandbox import Sandbox
from student.core.sandbox.config import SandboxConfig
from student.core.agent.agent import Agent
from student.core.mcp.client import MCPClient
from student.core.cli.base_agent import BaseAgentCLI


class MBPPAgentCLI(BaseAgentCLI):
    """CLI entrypoint for running an agent on MBPP tasks."""

    def _load_task(self) -> MBPPTaskInput:
        """Load an MBPP task from the JSON file specified in args.

        Returns:
            A populated MBPPTaskInput instance.
        """
        with open(self.args.task_file) as f:
            return MBPPTaskInput(**json.load(f))

    def run(self) -> None:
        """Set up the agent components and solve the MBPP task."""
        task_input = self._load_task()

        mcp_client = MCPClient(command="python mcp_tools_mbpp.py")
        mcp_client.connect()

        client = OpenAICompatibleClient(
            model_name=self.args.model_name,
            base_url=self.args.provider_url,
        )
        config = SandboxConfig(max_execution_time_seconds=10)
        sandbox = Sandbox(config, mcp_client)
        agent = Agent(client, sandbox, 10, 6000, 1500, 120)

        func_name = task_input.function_definition.split("(")[0].replace(
            "def ", ""
        )
        task = f"""Solve the following Python programming task:

Task: {task_input.task_definition}

You must implement this function:
{task_input.function_definition}

These are SOME tests (not all) your solution must pass:
{chr(10).join(task_input.test_list)}

To verify your solution, call run_tests with EXACTLY these arguments
(copy test_list and test_imports verbatim, only fill in `code`):

run_tests(
    code="<your complete function source>",
    test_list={task_input.test_list!r},
    test_imports={task_input.test_imports!r},
)

Instructions:
1. Write a correct and general implementation
2. Verify it with the run_tests call above (do not change the tests)
3. Think about edge cases not covered by the visible tests
4. Call final_answer() with the COMPLETE function source code as a string

IMPORTANT: final_answer() must receive the complete function code, like this:
final_answer(\"\"\"def {func_name}(...):
    # your implementation here
\"\"\")
"""

        system_prompt = (
            "You are an autonomous coding agent.\n"
            "To solve the user's task, you must write Python code inside"
            " a\n"
            "```python code block, and end that block with the marker"
            " <end_code> on its own line.\n"
            "Write EXACTLY ONE code block per turn, then STOP and wait."
            " Do NOT write more code, and do NOT invent or predict the"
            " Observation yourself: the sandbox will run your code and"
            " give you the real output.\n"
            "This code will be executed in a sandbox, and you will"
            " receive the standard output (Observation).\n"
            "You can use `print()` to observe variables and results.\n"
            "Once you have the final answer, call the function"
            ' `final_answer("your result")`.\n'
            f"\n{mcp_client.get_man()}\n"
            "\nEach tool is a plain Python function. Call it directly by"
            " its name with keyword arguments. Do NOT prefix it with a"
            " module or object (write `run_tests(...)`, never"
            " `run_tests.run_tests(...)`).\n"
            "Example turn:\n"
            "```python\n"
            'result = run_tests(code="def f(): return 1",'
            ' test_list=["assert f() == 1"], test_imports=[])\n'
            "print(result)\n"
            "```\n"
            "<end_code>\n"
            f"\n{config.describe_constraints()}\n"
            "\nVERIFICATION:\n"
            "- Verify your solution ONLY with run_tests(code=...,"
            " test_list=[...], test_imports=[...]). It returns a clear"
            " pass/fail report.\n"
            "- Use the tests provided in the task VERBATIM in test_list —"
            " copy them exactly, never simplify or change the argument"
            " values (e.g. keep 1j as 1j, do not turn it into 1).\n"
            "- Do NOT write your own assert statements in the code block:"
            " a bare failed assert aborts execution with an empty error"
            " and gives you no signal to fix it.\n"
            "- Do NOT invent expected outputs for edge cases you cannot"
            " verify; rely on the provided tests.\n"
            "- Once run_tests reports success, call final_answer() in the"
            " SAME or a later turn, but never place asserts or other logic"
            " before it.\n"
            "\nIMPORTANT: Be concise. Write minimal code without"
            " docstrings, comments, or unnecessary validations."
        )

        def validate_answer(code: str) -> str | None:
            """Run the task's official visible tests against a submission.

            Enforces correctness in the harness instead of trusting the
            model's self-report: if the provided tests fail, the answer is
            rejected and the failure is fed back to the model.
            """
            result = mcp_client.call_tool(
                "run_tests",
                {
                    "code": code,
                    "test_list": task_input.test_list,
                    "test_imports": task_input.test_imports,
                },
            )
            if "Error:" in result or "Traceback" in result:
                return (
                    "final_answer rejected: your solution failed the "
                    "official task tests:\n"
                    f"{result}\n"
                    "Fix the code (verify with run_tests using these exact "
                    "tests), then call final_answer(code) again."
                )
            return None

        res = agent.run(
            task=task,
            system_prompt=system_prompt,
            task_id=str(task_input.task_id),
            benchmark="mbpp",
            answer_validator=validate_answer,
        )

        self._save_output(res)


if __name__ == "__main__":
    try:
        dotenv.load_dotenv()
        cli = MBPPAgentCLI()
        cli.run()
    except Exception as e:
        print(e, file=sys.stderr)
