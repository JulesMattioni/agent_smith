import subprocess
import tempfile
from .config import SandboxConfig
import sys


class Sandbox:
    def __init__(self, config: SandboxConfig) -> None:
        self.config = config

    def execute(self, code: str) -> str:

        allowed = self.config.authorized_imports

        injection = f"""
import builtins
import sys
import socket
import os
import resource

max_bytes = {self.config.max_memory_mb} * 1024 * 1024
resource.setrlimit(resource.RLIMIT_AS, (max_bytes, max_bytes))


_original_open = open
_allowed_dirs = {self.config.allowed_directories}

def _safe_open(file, mode='r', *args, **kwargs):
    abs_path = os.path.abspath(str(file))
    if not any(abs_path.startswith(d) for d in _allowed_dirs):
        raise PermissionError(f"Access to '{{abs_path}}' is not allowed.")
    return _original_open(file, mode, *args, **kwargs)

builtins.open = _safe_open

_original_import = builtins.__import__
_allowed_imports = {allowed}

def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    base_name = name.split('.')[0]

    if base_name not in _allowed_imports:
        if name == 'socket':
            raise PermissionError("Network access is not allowed.")
        raise ImportError(f"Import '{{name}}' not allowed.")

    return _original_import(name, globals, locals, fromlist, level)

builtins.__import__ = _safe_import

_dangerous = ['eval', 'exec', 'compile', '__import__', 'breakpoint']
for _name in _dangerous:
    if hasattr(builtins, _name):
        delattr(builtins, _name)

def _blocked_socket(*args, **kwargs):
    raise PermissionError("Network access is not allowed.")

socket.socket = _blocked_socket

def final_answer(answer):
    print("<<<FINAL_ANSWER:" + str(answer) + ">>>")
    sys.exit(0)
"""
        full_code = injection + "\n" + code
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py") as temp_file:
            temp_file.write(full_code)
            temp_file.flush()

            try:
                res = subprocess.run(
                    [sys.executable, temp_file.name],
                    capture_output=True,
                    text=True,
                    timeout=self.config.max_execution_time_seconds,
                )
                output = res.stdout
                if res.stderr:
                    output += f"\nError: {res.stderr}"
                if res.returncode == -9:
                    output += "\nError: Memory limit exceeded."

                return output if output else "Code executed with success!"
            except subprocess.TimeoutExpired:
                return "Error: execution has timed out."
            except Exception as e:
                return f"Critical error: {e}"
