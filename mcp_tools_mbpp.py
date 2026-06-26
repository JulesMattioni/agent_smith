from mcp.server.fastmcp import FastMCP
from typing import List
import subprocess
import tempfile
import sys


class MBPPTools:
    """MCP server exposing tools for MBPP task evaluation."""

    def __init__(self) -> None:
        """Initialize the FastMCP server and register tools."""
        self.__mcp = FastMCP("mbpp-tools")
        self._register_tools()

    def _register_tools(self) -> None:
        """Register all MCP tools on the FastMCP instance."""
        self.__mcp.tool()(self.run_tests)

    def run_tests(
        self, code: str, test_list: List[str], test_imports: List[str]
    ) -> str:
        """Execute tests against the provided code in a subprocess.

        Args:
            code: The solution code to test.
            test_list: List of assertion statements to run.
            test_imports: List of import statements required by tests.

        Returns:
            Test execution output, or an error message on failure.
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

    def run(self) -> None:
        """Start the MCP server."""
        self.__mcp.run()


if __name__ == "__main__":
    try:
        server = MBPPTools()
        server.run()
    except Exception as e:
        print(e, file=sys.stderr)
        sys.exit(1)
