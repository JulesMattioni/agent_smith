import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
import os
from typing import Any, Callable


class MCPClient:
    """Synchronous wrapper around an async MCP session."""

    def __init__(
        self, command: str | None = None, url: str | None = None
    ) -> None:
        """Initialize the MCP transport configuration.

        Args:
            command: Shell command to start a stdio MCP server.
            url: URL of an HTTP MCP server.

        Raises:
            ValueError: If neither command nor url is provided.
        """
        if command:
            args = command.split()
            self.params = StdioServerParameters(
                command=args[0],
                args=args[1:],
                env={
                    "SWE_DOCKER_IMAGE": str(os.getenv("SWE_DOCKER_IMAGE")),
                    "SWE_EVAL_SCRIPT": str(os.getenv("SWE_EVAL_SCRIPT")),
                },
            )
            self.transport = "stdio"
        elif url:
            self.url = url
            self.transport = "http"
        else:
            raise ValueError("Either command or url must be provided")

        self.session: Any = None
        self._loop = asyncio.new_event_loop()
        self._tools: dict[str, Any] = {}

    async def _connect_async(self) -> None:
        """Open the transport, start the session, and list tools."""
        if self.transport == "stdio":
            self._stdio_ctx = stdio_client(self.params)
            self._read, self._write = await self._stdio_ctx.__aenter__()
            self._session_ctx = ClientSession(self._read, self._write)
        elif self.transport == "http":
            self._stdio_ctx = streamable_http_client(self.url)
            self._read, self._write, _ = await self._stdio_ctx.__aenter__()
            self._session_ctx = ClientSession(self._read, self._write)

        self.session = await self._session_ctx.__aenter__()
        await self.session.initialize()

        tools_res = await self.session.list_tools()
        for tool in tools_res.tools:
            self._tools[tool.name] = tool

    def connect(self) -> None:
        """Synchronously connect to the MCP server."""
        self._loop.run_until_complete(self._connect_async())

    async def _call_tool_async(self, name: str, args: dict[str, Any]) -> str:
        """Call a tool on the MCP server asynchronously.

        Args:
            name: Tool name to invoke.
            args: Keyword arguments to pass to the tool.

        Returns:
            The text content of the tool response.

        Raises:
            RuntimeError: If the MCP server reports the tool call as an
                error (``isError``). Propagating it lets a failed tool
                (e.g. an edit_file that matched nothing) surface in the
                sandbox observation and halt the current code block,
                instead of being silently discarded when the model does
                not print the return value.
        """
        res = await self.session.call_tool(name, args)
        text = res.content[0].text if res.content else ""
        if getattr(res, "isError", False):
            raise RuntimeError(text)
        return text

    def call_tool(self, name: str, args: dict[str, Any]) -> str:
        """Call a tool on the MCP server synchronously.

        Args:
            name: Tool name to invoke.
            args: Keyword arguments to pass to the tool.

        Returns:
            The text content of the tool response.
        """
        return self._loop.run_until_complete(self._call_tool_async(name, args))

    def get_tools(self) -> dict[str, Callable[..., str]]:
        """Return callable wrappers for each registered tool.

        Returns:
            Mapping of tool name to a callable that forwards keyword
            arguments to the MCP server.
        """
        tools: dict[str, Callable[..., str]] = {}
        for name in self._tools:

            def make_tool(tool_name: str) -> Callable[..., str]:
                schema = self._tools[tool_name].inputSchema or {}
                param_names = list(schema.get("properties", {}).keys())

                def tool(*args: Any, **kwargs: Any) -> str:
                    if len(args) > len(param_names):
                        raise TypeError(
                            f"{tool_name}() takes at most "
                            f"{len(param_names)} positional arguments "
                            f"but {len(args)} were given"
                        )
                    for param_name, value in zip(param_names, args):
                        if param_name in kwargs:
                            raise TypeError(
                                f"{tool_name}() got multiple values for "
                                f"argument '{param_name}'"
                            )
                        kwargs[param_name] = value
                    return self.call_tool(tool_name, kwargs)

                tool.__name__ = tool_name
                return tool

            tools[name] = make_tool(name)
        return tools

    async def _disconnect_async(self) -> None:
        """Close the session and transport context managers."""
        if self._session_ctx:
            await self._session_ctx.__aexit__(None, None, None)
        if self._stdio_ctx:
            await self._stdio_ctx.__aexit__(None, None, None)

    def disconnect(self) -> None:
        """Synchronously disconnect and close the event loop."""
        try:
            self._loop.run_until_complete(self._disconnect_async())
        except Exception:
            pass
        finally:
            self._loop.close()

    def get_man(self) -> str:
        """Return a human-readable summary of available tools.

        Returns:
            Formatted string listing each tool's name, description,
            and input schema.
        """
        man = "=== MCP TOOLS AVAILABLE ===\n"
        for name, tool in self._tools.items():
            man += f"- Tool: {name}\n"
            man += f"  Description: {tool.description}\n"
            man += f"  Schema: {tool.inputSchema}\n"
        return man
