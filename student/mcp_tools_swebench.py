from mcp.server.fastmcp import FastMCP
import os
import subprocess
import shlex


class SWEBenchTools:
    TESTBED = "/testbed"

    def __init__(self):
        self.mcp = FastMCP("swebench-tools")

        self._docker_image = os.getenv("SWE_DOCKER_IMAGE")
        if not self._docker_image:
            raise ValueError("SWE_DOCKER_IMAGE missing.")
        self._eval_script = os.getenv("SWE_EVAL_SCRIPT")
        if not self._eval_script:
            raise ValueError("SWE_EVAL_SCRIPT missing.")
        self._container_id: str | None = None

        self._register_tools()

    # Utils

    def _register_tools(self):
        self.mcp.tool()(self.read_file)
        self.mcp.tool()(self.edit_file)
        self.mcp.tool()(self.list_files)
        self.mcp.tool()(self.search_code)
        self.mcp.tool()(self.search_function_or_class_definition_in_code)
        self.mcp.tool()(self.find_references)
        self.mcp.tool()(self.run_command)
        self.mcp.tool()(self.get_patch)
        self.mcp.tool()(self.run_tests)

    def _start_container(self) -> None:
        if self._container_id:
            return
        res = subprocess.run(
            ["docker", "run", "-d", self._docker_image, "sleep", "infinity"],
            capture_output=True,
            text=True,
        )
        if res.returncode != 0:
            raise RuntimeError(f"Docker failed: {res.stderr.strip()}")
        self._container_id = res.stdout.strip()

    def _exec(
        self,
        command: str,
        workdir: str = TESTBED,
        timeout: int = 300,
        input_data: str | None = None,
    ) -> dict:
        self._start_container()
        cmd = ["docker", "exec", "-w", workdir]
        if input_data is not None:
            cmd.append("-i")
        cmd += [self._container_id, "bash", "-c", command]
        try:
            res = subprocess.run(
                cmd,
                input=input_data,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {
                "stdout": res.stdout,
                "stderr": res.stderr,
                "exit_code": res.returncode,
            }
        except subprocess.TimeoutExpired:
            return {
                "stdout": "",
                "stderr": "Command timed out",
                "exit_code": -1,
            }

    # File System Tools

    def read_file(
        self,
        filepath: str,
        start_line: int | None = 1,
        end_line: int | None = -1,
    ) -> str:
        """
        Read the content of a file with line numbers.

        Args:
            filepath: The absolute or relative path to the file.
            start_line: The line number to start reading from (1-indexed).
            Defaults to 1.
            end_line: The line number to stop reading at.
            Defaults to -1 (read to end).

        Returns:
            The file content formatted as '<line_number>: <line_content>'.
        """
        out = self._exec(f"cat {shlex.quote(filepath)}")
        if out["exit_code"] != 0:
            return f"Error: {out['stderr'].strip()}"
        lines = out["stdout"].splitlines()
        total = len(lines)
        start_idx = max(0, start_line - 1)
        end_idx = total if end_line == -1 else min(end_line, total)
        chunk = [f"{i + 1}: {lines[i]}" for i in range(start_idx, end_idx)]
        return "\n".join(chunk) if chunk else "Error: No lines in range."

    def edit_file(self, filepath: str, old_str: str, new_str: str) -> str:
        """
        Replace an exact string in a file with a new string.

        Args:
            filepath: The path to the file to edit.
            old_str: The exact string to find and replace.
            new_str: The exact string to insert.

        Returns:
            A success message or an error if the string was not found.
        """
        read = self._exec(f"cat {shlex.quote(filepath)}")
        if read["exit_code"] != 0:
            return f"Error: File '{filepath}' not found."
        content = read["stdout"]
        if old_str not in content:
            return "Error: 'old_str' not found. No changes made. "
        occurrences = content.count(old_str)
        new_content = content.replace(old_str, new_str)
        write = self._exec(
            f"cat > {shlex.quote(filepath)}", input_data=new_content
        )
        if write["exit_code"] != 0:
            return f"Error writing file: {write['stderr'].strip()}"
        return f"Success: Replaced {occurrences} occurrence(s)."

    def list_files(self, directory: str, pattern: str = "*") -> str:
        """
        List files in a directory matching a given pattern.

        Args:
            directory: The directory path to search in.
            pattern: The glob pattern to match (e.g., '*.py', '*test*').
            Defaults to '*'.

        Returns:
            A list of matching file paths.
        """
        out = self._exec(
            f"find {shlex.quote(directory)} -type f -name {shlex.quote(pattern)}"
        )
        if out["exit_code"] != 0:
            return f"Error: {out['stderr'].strip()}"
        return out["stdout"].strip() or f"No files matching '{pattern}'."

    # Code Search Tools

    def search_code(self, pattern: str, file_pattern: str = "*.py") -> str:
        """Grep-like search. Output: /abs/path:line <content>."""
        out = self._exec(
            f"grep -rEn --include={shlex.quote(file_pattern)} "
            f"-e {shlex.quote(pattern)} {self.TESTBED}"
        )
        if out["exit_code"] not in (0, 1):
            return f"Error: {out['stderr'].strip()}"
        lines = out["stdout"].splitlines()
        if not lines:
            return f"No matches found for '{pattern}'."
        formatted = []
        for ln in lines[:100]:
            parts = ln.split(":", 2)
            formatted.append(
                f"{parts[0]}:{parts[1]} {parts[2]}" if len(parts) == 3 else ln
            )
        if len(lines) > 100:
            formatted.append(
                f"...and {len(lines) - 100} more. Refine your search."
            )
        return "\n".join(formatted)

    def search_function_or_class_definition_in_code(self, name: str) -> str:
        """Find a function or class definition."""
        return self.search_code(f"(def|class) {name}")

    def find_references(
        self, name: str, filepath: str = "", line: int = 0
    ) -> str:
        """Find all usages of a symbol."""
        return self.search_code(name)

    # Execution Tools

    def run_command(self, command: str, workdir: str = TESTBED) -> str:
        out = self._exec(command, workdir)
        return (
            f"STDOUT:\n{out['stdout']}\n\nSTDERR:\n{out['stderr']}"
            f"\n\nEXIT_CODE:\n{out['exit_code']}"
        )

    def get_patch(self) -> str:
        out = self._exec("git -c core.fileMode=false diff")
        return out["stdout"]

    def run_tests(self) -> str:
        out = self._exec(self._eval_script, timeout=900)
        return (
            f"STDOUT:\n{out['stdout']}\n\nSTDERR:\n{out['stderr']}"
            f"\n\nEXIT_CODE:\n{out['exit_code']}"
        )

    def run(self):
        try:
            self.mcp.run()
        finally:
            if self._container_id:
                subprocess.run(
                    ["docker", "rm", "-f", self._container_id],
                    capture_output=True,
                )
                self._container_id = None


if __name__ == "__main__":
    server = SWEBenchTools()
    server.run()
