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
        return parser.parse_args()

    def _build_client(self) -> MCPClient | None:
        """Build and connect an MCP client from CLI args.

        Returns:
            A connected MCPClient, or None if no MCP flag was given.
        """
        if self.args.mcp_stdio:
            client = MCPClient(command=self.args.mcp_stdio)
            client.connect()
            return client
        elif self.args.mcp_server:
            client = MCPClient(url=self.args.mcp_server)
            client.connect()
            return client
        return None

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
        """Start the interactive sandbox REPL."""
        config = self._load_config()
        client = self._build_client()
        sandbox = Sandbox(config, mcp_client=client)

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
                        if client:
                            client.disconnect()
                        return
                    if line == "EXEC":
                        break
                    if line == "MAN":
                        print(
                            client.get_man()
                            if client
                            else "No MCP client connected."
                        )
                        continue
                    lines.append(line)

                code = "\n".join(lines)
                print(sandbox.execute(code))

            except KeyboardInterrupt:
                break

        if client:
            client.disconnect()


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
