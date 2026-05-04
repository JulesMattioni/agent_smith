import subprocess
import tempfile
from .config import SandboxConfig


class Sandbox:
    def __init__(self, config: SandboxConfig) -> None:
        self.config = config

    def execute(self, code: str) -> str:

        allowed = self.config.authorized_imports

        injection = f"""
import builtins

_original_import = builtins.__import__
_allowed_imports = {allowed}

def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    base_name = name.split('.')[0]

    if base_name not in _allowed_imports:
        raise ImportError(f"Import '{{name}}' not allowed.")

    return _original_import(name, globals, locals, fromlist, level)

builtins.__import__ = _safe_import

def final_answer(answer):
    print("<<<FINAL_ANSWER:" + str(answer) + ">>>")
"""
        full_code = injection + "\n" + code
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py") as temp_file:
            temp_file.write(full_code)
            temp_file.flush()

            try:
                res = subprocess.run(
                    ["python", temp_file.name],
                    capture_output=True,
                    text=True,
                    timeout=self.config.max_execution_time_seconds,
                )
                output = res.stdout
                if res.stderr:
                    output += f"\nError: {res.stderr}"

                return output if output else "Code executed with success!"
            except subprocess.TimeoutExpired:
                return "Error: execution has timed out."
            except Exception as e:
                return f"Critical error: {e}"
