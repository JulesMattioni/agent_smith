import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client


class MCPClient:
    """Synchronous wrapper around an async MCP session."""

    def __init__(self, command: str = None, url: str = None):
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
            )
            self.transport = "stdio"
        elif url:
            self.url = url
            self.transport = "http"
        else:
            raise ValueError("Either command or url must be provided")

        self.session = None
        self._loop = asyncio.new_event_loop()
        self._tools = {}

    async def _connect_async(self):
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

    def connect(self):
        """Synchronously connect to the MCP server."""
        self._loop.run_until_complete(self._connect_async())

    async def _call_tool_async(self, name: str, args: dict) -> str:
        """Call a tool on the MCP server asynchronously.

        Args:
            name: Tool name to invoke.
            args: Keyword arguments to pass to the tool.

        Returns:
            The text content of the tool response.
        """
        res = await self.session.call_tool(name, args)
        return res.content[0].text

    def call_tool(self, name: str, args: dict) -> str:
        """Call a tool on the MCP server synchronously.

        Args:
            name: Tool name to invoke.
            args: Keyword arguments to pass to the tool.

        Returns:
            The text content of the tool response.
        """
        return self._loop.run_until_complete(self._call_tool_async(name, args))

    def get_tools(self) -> dict:
        """Return callable wrappers for each registered tool.

        Returns:
            Mapping of tool name to a callable that forwards keyword
            arguments to the MCP server.
        """
        tools = {}
        for name in self._tools:

            def make_tool(tool_name):
                def tool(**kwargs):
                    return self.call_tool(tool_name, kwargs)

                tool.__name__ = tool_name
                return tool

            tools[name] = make_tool(name)
        return tools

    async def _disconnect_async(self):
        """Close the session and transport context managers."""
        if self._session_ctx:
            await self._session_ctx.__aexit__(None, None, None)
        if self._stdio_ctx:
            await self._stdio_ctx.__aexit__(None, None, None)

    def disconnect(self):
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
