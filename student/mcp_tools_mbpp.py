from mcp.server.fastmcp import FastMCP
from typing import List
import subprocess
import tempfile
import sys


class MBPPTools:
    """Utilities for registering MCP tools to run MBPP-style tests."""

    def __init__(self):
        self.__mcp = FastMCP("mbpp-tools")
        self._register_tools()

    def _register_tools(self):
        self.__mcp.tool()(self.run_tests)

    def run_tests(
        self, code: str, test_list: List[str], test_imports: List[str]
    ) -> str:
        """
        Execute tests against provided code.

        Parameters
        ----------
        code : str
            The code to test.
        test_list : List[str]
            List of test statements to execute.
        test_imports : List[str]
            List of import statements required for tests.

        Returns
        -------
        str
            Test execution output or error message.

        Raises
        ------
        subprocess.TimeoutExpired
            If execution exceeds 30 seconds timeout.
        Exception
            Catches and returns critical errors as string.
        """
        import_code = "\n".join(test_imports)
        tests_code = "\n".join(test_list)
        full_code = "\n\n".join([import_code, code, tests_code])
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py") as temp_file:
            temp_file.write(full_code)
            temp_file.flush()

            try:
                res = subprocess.run(
                    [sys.executable, temp_file.name],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                output = res.stdout
                if res.stderr:
                    output += f"\nError: {res.stderr}"

                return output if output else "Code executed with success!"
            except subprocess.TimeoutExpired:
                return "Error: execution has timed out."
            except Exception as e:
                return f"Critical error: {e}"

    def run(self):
        self.__mcp.run()


if __name__ == "__main__":
    server = MBPPTools()
    server.run()
