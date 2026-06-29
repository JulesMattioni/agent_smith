import multiprocessing
import sys
import io
import resource
import os
import socket
from .config import SandboxConfig
from ..mcp.client import MCPClient
import traceback
from typing import Any, Callable
from multiprocessing.connection import Connection


class IsolatedWorker:
    """Run user code in an isolated subprocess with restricted builtins."""

    @staticmethod
    def run(
        code: str,
        child_conn: Connection,
        config_dict: dict[str, Any],
        tool_names: list[str],
    ) -> None:
        """Execute code in isolation with resource and import limits.

        Communicates with the parent process over ``child_conn`` to
        handle tool calls and report the final output.

        Args:
            code: Python source code to execute.
            child_conn: Child end of a multiprocessing Pipe.
            config_dict: Configuration with keys 'max_memory_mb',
                'allowed_dirs', and 'allowed_imports'.
            tool_names: Names of MCP tools to expose as stubs.
        """
        max_bytes = config_dict["max_memory_mb"] * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (max_bytes, max_bytes))

        import builtins

        _safe_exec = builtins.exec

        _original_open = builtins.open

        def _safe_open(
            file: Any, mode: str = "r", *args: Any, **kwargs: Any
        ) -> Any:
            abs_path = os.path.abspath(str(file))
            if not any(
                abs_path.startswith(d) for d in config_dict["allowed_dirs"]
            ):
                raise PermissionError(
                    f"Access to '{abs_path}' is not allowed."
                )
            return _original_open(file, mode, *args, **kwargs)

        builtins.open = _safe_open

        _original_import = builtins.__import__

        def _safe_import(
            name: str,
            globals: Any = None,
            locals: Any = None,
            fromlist: Any = (),
            level: int = 0,
        ) -> Any:
            base_name = name.split(".")[0]
            if base_name not in config_dict["allowed_imports"]:
                raise ImportError(f"Import '{name}' not allowed.")
            return _original_import(name, globals, locals, fromlist, level)

        builtins.__import__ = _safe_import

        def _blocked_socket(*args: Any, **kwargs: Any) -> Any:
            raise PermissionError("Network access is not allowed.")

        socket.socket = _blocked_socket  # type: ignore[assignment,misc]

        for _name in ["eval", "exec", "compile"]:
            if hasattr(builtins, _name):
                delattr(builtins, _name)

        exec_globals: dict[str, Any] = {}

        def make_tool_stub(tool_name: str) -> Callable[..., Any]:
            def tool_stub(**kwargs: Any) -> Any:
                child_conn.send(
                    {"type": "CALL_TOOL", "name": tool_name, "args": kwargs}
                )
                response = child_conn.recv()
                if response["status"] == "error":
                    raise Exception(f"Tool error: {response['message']}")
                return response["result"]

            return tool_stub

        for name in tool_names:
            exec_globals[name] = make_tool_stub(name)

        def final_answer(answer: Any) -> None:
            child_conn.send({"type": "FINAL_ANSWER", "answer": answer})
            sys.exit(0)

        exec_globals["final_answer"] = final_answer

        stdout_capture = io.StringIO()
        sys.stdout = stdout_capture
        sys.stderr = stdout_capture

        try:
            _safe_exec(code, exec_globals)
            output = stdout_capture.getvalue()
            child_conn.send({"type": "SUCCESS", "output": output})
        except Exception:
            output = stdout_capture.getvalue()
            child_conn.send(
                {
                    "type": "ERROR",
                    "output": output,
                    "error": traceback.format_exc(),
                }
            )
        finally:
            sys.stdout = sys.__stdout__
            sys.stderr = sys.__stderr__


class Sandbox:
    """Orchestrate isolated code execution with optional MCP tooling."""

    MAX_OBSERVATION_CHARS = 6000

    @classmethod
    def _truncate(cls, text: str) -> str:
        """Cap an observation and signal truncation explicitly.

        A single oversized tool output (e.g. listing a whole repo) can
        blow up the conversation context. We keep the head and tail of
        the output and insert an explicit notice so the LLM is never left
        guessing about what was cut.

        Args:
            text: The raw observation text.

        Returns:
            The text unchanged if within the limit, otherwise a truncated
            version with an explicit marker.
        """
        limit = cls.MAX_OBSERVATION_CHARS
        if len(text) <= limit:
            return text
        head = limit // 2
        tail = limit - head
        notice = (
            f"\n[... output truncated due to size limit: "
            f"{len(text)} chars total, kept first {head} and last {tail} "
            f"...]\n"
        )
        return text[:head] + notice + text[-tail:]

    def __init__(
        self, config: SandboxConfig, mcp_client: MCPClient | None = None
    ) -> None:
        """Initialize the sandbox with a config and optional MCP client.

        Args:
            config: Sandbox configuration (limits, allowed imports).
            mcp_client: Optional MCP client exposing tools to executed
                code.
        """
        self.config = config
        self.mcp_client = mcp_client
        self.tool_names = (
            list(self.mcp_client.get_tools().keys()) if self.mcp_client else []
        )

    def get_man(self) -> str:
        """Return the tool manual for the LLM prompt.

        The sandbox is the layer that exposes MCP tools as callable
        functions in the execution namespace, so it owns the manual too:
        it delegates to the connected MCP client for the dynamically-
        discovered tool docs. Routing through the sandbox (rather than
        letting the prompt reach into the MCP client directly) keeps the
        architectural boundary intact — the sandbox wraps the MCP client.

        Returns:
            The dynamically-generated tool manual, or an explicit notice
            if no MCP client is connected.
        """
        if not self.mcp_client:
            return "No MCP client connected."
        return self.mcp_client.get_man()

    def execute(self, code: str) -> str:
        """Execute code in a subprocess and return its output.

        Args:
            code: Python source code to run.

        Returns:
            Captured stdout, a final answer marker, or an error string.
        """
        worker_config = {
            "max_memory_mb": self.config.max_memory_mb,
            "allowed_dirs": self.config.allowed_directories,
            "allowed_imports": self.config.authorized_imports,
        }

        parent_conn, child_conn = multiprocessing.Pipe()

        p = multiprocessing.Process(
            target=IsolatedWorker.run,
            args=(code, child_conn, worker_config, self.tool_names),
        )
        p.start()

        child_conn.close()

        output_log = ""
        timeout = self.config.max_execution_time_seconds

        while p.is_alive():
            if parent_conn.poll(timeout):
                msg = parent_conn.recv()

                if msg["type"] == "CALL_TOOL":
                    try:
                        if self.mcp_client:
                            result = self.mcp_client.call_tool(
                                msg["name"], msg["args"]
                            )
                            parent_conn.send(
                                {"status": "ok", "result": result}
                            )
                        else:
                            parent_conn.send(
                                {
                                    "status": "error",
                                    "message": "No MCP client connected.",
                                }
                            )
                    except Exception as e:
                        parent_conn.send(
                            {"status": "error", "message": str(e)}
                        )

                elif msg["type"] == "FINAL_ANSWER":
                    output_log += f"\n<<<FINAL_ANSWER:{msg['answer']}>>>"
                    p.terminate()
                    break

                elif msg["type"] == "SUCCESS":
                    output_log += self._truncate(msg["output"])
                    break

                elif msg["type"] == "ERROR":
                    output_log += (
                        self._truncate(msg["output"])
                        + f"\nError: {msg['error']}"
                    )
                    break

            else:
                p.terminate()
                p.join()
                return "Error: execution has timed out."

        p.join()

        if not output_log.strip():
            return "Code executed with success!"

        return output_log
