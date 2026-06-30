import argparse
import dotenv
import sys
from student.core.sandbox.sandbox import Sandbox
from student.core.sandbox.config import SandboxConfig
from student.core.mcp.client import MCPClient


class SandboxCLI:
    """Interactive CLI for executing code in the sandbox."""

    def __init__(self) -> None:
        """Parse CLI arguments and store them."""
        self.args = self._parse_args()

    def _parse_args(self) -> argparse.Namespace:
        """Define and parse CLI arguments.

        Returns:
            Parsed argument namespace.
        """
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "config", nargs="?", help="Path to sandbox config JSON"
        )
        parser.add_argument(
            "--mcp-stdio", help="Command to launch MCP server via stdio"
        )
        parser.add_argument("--mcp-server", help="URL of HTTP MCP server")
        parser.add_argument(
            "--interactive",
            action="store_true",
            help="Run an interactive REPL instead of reading code from stdin",
        )
        return parser.parse_args()

    def _build_client(self) -> MCPClient | None:
        """Build and connect an MCP client from CLI args.

        If an MCP flag is given but the server fails to start or connect
        (e.g. the SWE-bench server aborts because no Docker image is set),
        the failure is reported on stderr and ``None`` is returned so the
        sandbox still runs — without the MCP tools, but with
        ``final_answer()`` and the security restrictions intact. The
        sandbox is meant to work independently of any MCP server.

        Returns:
            A connected MCPClient, or None if no MCP flag was given or the
            connection failed.
        """
        if self.args.mcp_stdio:
            client = MCPClient(command=self.args.mcp_stdio)
        elif self.args.mcp_server:
            client = MCPClient(url=self.args.mcp_server)
        else:
            return None

        try:
            client.connect()
        except Exception as e:
            print(
                f"Warning: could not connect to the MCP server ({e}). "
                "Running the sandbox without MCP tools.",
                file=sys.stderr,
            )
            client.disconnect()
            return None
        return client

    def _load_config(self) -> SandboxConfig:
        """Load sandbox config from a JSON file or use defaults.

        Returns:
            A SandboxConfig instance.
        """
        if self.args.config:
            import json

            with open(self.args.config) as f:
                return SandboxConfig(**json.load(f))
        return SandboxConfig()

    def run(self) -> None:
        """Run the sandbox, in batch (default) or interactive mode.

        By default, the whole of stdin is read as a single code block,
        executed once, and the observation is printed — suitable for
        piping: ``<code> | uv run sandbox --mcp-stdio <cmd>``. The
        ``--interactive`` flag restores the REPL behaviour instead.
        """
        config = self._load_config()
        client = self._build_client()
        sandbox = Sandbox(config, mcp_client=client)

        try:
            if self.args.interactive:
                self._run_interactive(sandbox)
            else:
                self._run_batch(sandbox)
        finally:
            if client:
                client.disconnect()

    def _run_batch(self, sandbox: Sandbox) -> None:
        """Read all of stdin as one code block and execute it once.

        The MCP client, when present, is already wired into ``sandbox``
        at construction, so the connected server's tools are available to
        the executed code without being referenced here.

        Args:
            sandbox: The configured sandbox to run the code in.
        """
        code = sys.stdin.read()
        if not code.strip():
            return
        print(sandbox.execute(code))

    def _run_interactive(self, sandbox: Sandbox) -> None:
        """Start the interactive sandbox REPL.

        Args:
            sandbox: The configured sandbox to run code in.
        """
        print("=== SANDBOX INTERACTIVE MODE ===")

        print(
            "Enter code (type 'EXEC' on a new line to execute, "
            "'MAN' to get the available tools, "
            "'QUIT' to quit):\n"
        )

        while True:
            try:
                lines = []
                while True:
                    line = input()
                    if line == "QUIT":
                        return
                    if line == "EXEC":
                        break
                    if line == "MAN":
                        print(sandbox.get_man())
                        continue
                    lines.append(line)

                code = "\n".join(lines)
                print(sandbox.execute(code))

            except KeyboardInterrupt:
                break


def main() -> None:
    """Load environment variables and start the sandbox CLI."""
    try:
        dotenv.load_dotenv()
        cli = SandboxCLI()
        cli.run()
    except Exception as e:
        print(e, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
