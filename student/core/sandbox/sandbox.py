import multiprocessing
import sys
import io
import resource
import os
import socket
from .config import SandboxConfig
from ..mcp.client import MCPClient


class IsolatedWorker:

    @staticmethod
    def run(code: str, child_conn, config_dict: dict, tool_names: list):
        max_bytes = config_dict["max_memory_mb"] * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (max_bytes, max_bytes))

        import builtins

        _safe_exec = builtins.exec

        _original_open = builtins.open

        def _safe_open(file, mode="r", *args, **kwargs):
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
            name, globals=None, locals=None, fromlist=(), level=0
        ):
            base_name = name.split(".")[0]
            if base_name not in config_dict["allowed_imports"]:
                raise ImportError(f"Import '{name}' not allowed.")
            return _original_import(name, globals, locals, fromlist, level)

        builtins.__import__ = _safe_import

        def _blocked_socket(*args, **kwargs):
            raise PermissionError("Network access is not allowed.")

        socket.socket = _blocked_socket

        for _name in ["eval", "exec", "compile"]:
            if hasattr(builtins, _name):
                delattr(builtins, _name)

        exec_globals = {}

        def make_tool_stub(tool_name):
            def tool_stub(**kwargs):
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

        def final_answer(answer):
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
        except Exception as e:
            output = stdout_capture.getvalue()
            child_conn.send({"type": "ERROR", "output": output, "error": str(e)})
        finally:
            sys.stdout = sys.__stdout__
            sys.stderr = sys.__stderr__


class Sandbox:
    def __init__(
        self, config: SandboxConfig, mcp_client: MCPClient | None = None
    ) -> None:
        self.config = config
        self.mcp_client = mcp_client
        self.tool_names = (
            list(self.mcp_client.get_tools().keys()) if self.mcp_client else []
        )

    def execute(self, code: str) -> str:
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
                    output_log += msg["output"]
                    break

                elif msg["type"] == "ERROR":
                    output_log += msg["output"] + f"\nError: {msg['error']}"
                    break

            else:
                p.terminate()
                p.join()
                return "Error: execution has timed out."

        p.join()

        if not output_log.strip():
            return "Code executed with success!"

        return output_log
