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
        self._resources: dict[str, Any] = {}
        self._prompts: dict[str, Any] = {}

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

        await self._list_resources_async()
        await self._list_prompts_async()

    async def _list_resources_async(self) -> None:
        """List the server's resources, tolerating unsupported servers.

        Resources are optional in MCP: a server that does not declare the
        capability raises instead of returning an empty list, so the error
        is swallowed to keep connection working with any server.
        """
        try:
            resources_res = await self.session.list_resources()
            for resource in resources_res.resources:
                self._resources[str(resource.uri)] = resource
        except Exception:
            pass

    async def _list_prompts_async(self) -> None:
        """List the server's prompts, tolerating unsupported servers.

        Prompts are optional in MCP; as with resources, a server without
        the capability raises, so the error is swallowed.
        """
        try:
            prompts_res = await self.session.list_prompts()
            for prompt in prompts_res.prompts:
                self._prompts[prompt.name] = prompt
        except Exception:
            pass

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

    def get_resources(self) -> dict[str, Any]:
        """Return the discovered MCP resources keyed by URI."""
        return self._resources

    def get_prompts(self) -> dict[str, Any]:
        """Return the discovered MCP prompts keyed by name."""
        return self._prompts

    async def _read_resource_async(self, uri: str) -> str:
        """Read a resource's text content asynchronously.

        Args:
            uri: URI of the resource to read.

        Returns:
            The concatenated text content of the resource.
        """
        res = await self.session.read_resource(uri)
        return "".join(
            getattr(c, "text", "") for c in res.contents if res.contents
        )

    async def _get_prompt_async(
        self, name: str, args: dict[str, Any] | None = None
    ) -> str:
        """Render a prompt template asynchronously.

        Args:
            name: Name of the prompt to render.
            args: Arguments to fill the prompt template with.

        Returns:
            The concatenated text of the rendered prompt messages.
        """
        res = await self.session.get_prompt(name, args or {})
        parts = []
        for message in res.messages:
            parts.append(getattr(message.content, "text", ""))
        return "\n".join(parts)

    def get_prompt(
        self, name: str, args: dict[str, Any] | None = None
    ) -> str:
        """Render a prompt template synchronously.

        Args:
            name: Name of the prompt to render.
            args: Arguments to fill the prompt template with.

        Returns:
            The concatenated text of the rendered prompt messages.
        """
        return self._loop.run_until_complete(
            self._get_prompt_async(name, args)
        )

    def read_resource(self, uri: str) -> str:
        """Read a resource's text content synchronously.

        Args:
            uri: URI of the resource to read.

        Returns:
            The concatenated text content of the resource.
        """
        return self._loop.run_until_complete(self._read_resource_async(uri))

    def get_man(self) -> str:
        """Return a human-readable summary of available tools.

        Returns:
            Formatted string listing each tool's name, description,
            and input schema, followed by any resources and prompts
            exposed by the connected server.
        """
        man = "=== MCP TOOLS AVAILABLE ===\n"
        for name, tool in self._tools.items():
            man += f"- Tool: {name}\n"
            man += f"  Description: {tool.description}\n"
            man += f"  Schema: {tool.inputSchema}\n"

        if self._resources:
            man += "\n=== MCP RESOURCES AVAILABLE ===\n"
            for uri, resource in self._resources.items():
                man += f"- Resource: {resource.name}\n"
                man += f"  URI: {uri}\n"
                man += f"  Description: {resource.description}\n"

        if self._prompts:
            man += "\n=== MCP PROMPTS AVAILABLE ===\n"
            for name, prompt in self._prompts.items():
                man += f"- Prompt: {name}\n"
                man += f"  Description: {prompt.description}\n"
                args = getattr(prompt, "arguments", None)
                if args:
                    arg_names = ", ".join(a.name for a in args)
                    man += f"  Arguments: {arg_names}\n"

        return man
