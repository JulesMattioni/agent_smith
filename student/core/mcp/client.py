import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client


class MCPClient:
    def __init__(self, command: str = None, url: str = None):
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
        self._loop.run_until_complete(self._connect_async())

    async def _call_tool_async(self, name: str, args: dict) -> str:
        res = await self.session.call_tool(name, args)
        return res.content[0].text

    def call_tool(self, name: str, args: dict) -> str:
        return self._loop.run_until_complete(self._call_tool_async(name, args))

    def get_tools(self) -> dict:
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
        if self._session_ctx:
            await self._session_ctx.__aexit__(None, None, None)
        if self._stdio_ctx:
            await self._stdio_ctx.__aexit__(None, None, None)

    def disconnect(self):
        try:
            self._loop.run_until_complete(self._disconnect_async())
        except Exception:
            pass
        finally:
            self._loop.close()

    def get_man(self) -> str:
        man = "=== MCP TOOLS AVAILABLE ===\n"
        for name, tool in self._tools.items():
            man += f"- Tool: {name}\n"
            man += f"  Description: {tool.description}\n"
            man += f"  Schema: {tool.inputSchema}\n"
        return man
