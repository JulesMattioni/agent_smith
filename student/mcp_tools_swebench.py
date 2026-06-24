from mcp.server.fastmcp import FastMCP
import os
import subprocess
import shlex


class SWEBenchTools:
    """MCP server exposing filesystem and execution tools for SWE-bench."""

    TESTBED = "/testbed"

    def __init__(self):
        """Initialize the Docker-backed MCP server and register tools.

        Raises:
            ValueError: If SWE_DOCKER_IMAGE or SWE_EVAL_SCRIPT env vars
                are not set.
        """
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
        """Register all MCP tools on the FastMCP instance."""
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
        """Start the Docker container if not already running.

        Raises:
            RuntimeError: If the docker run command fails.
        """
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
        """Run a bash command inside the Docker container.

        Args:
            command: Bash command to execute.
            workdir: Working directory inside the container.
            timeout: Timeout in seconds before the command is killed.
            input_data: Optional stdin data to pipe into the command.

        Returns:
            Dict with keys 'stdout', 'stderr', and 'exit_code'.
        """
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
        """Read the content of a file with line numbers.

        Args:
            filepath: The absolute or relative path to the file.
            start_line: The line number to start reading from (1-indexed).
            end_line: The line number to stop reading at (-1 = end).

        Returns:
            File content formatted as '<line_number>: <line_content>'.
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
        """Replace an exact string in a file with a new string.

        Args:
            filepath: The path to the file to edit.
            old_str: The exact string to find and replace.
            new_str: The replacement string.

        Returns:
            A success message or an error if the string was not found.
        """
        read = self._exec(f"cat {shlex.quote(filepath)}")
        if read["exit_code"] != 0:
            raise FileNotFoundError(
                f"edit_file made NO changes: file '{filepath}' not found."
            )
        content = read["stdout"]
        if old_str not in content:
            lines = content.splitlines()
            anchor = max(
                (ln.strip() for ln in old_str.splitlines()),
                key=len,
                default="",
            )[:40]
            hints = []
            if anchor:
                for i, line in enumerate(lines, 1):
                    if anchor in line:
                        window = lines[i - 1: i + 1]
                        hints.extend(
                            f"{i + off}: {w}" for off, w in enumerate(window)
                        )
            hint_text = "\n".join(hints[:12]) or "(no similar lines found)"
            raise ValueError(
                "edit_file made NO changes: 'old_str' was not found "
                "exactly. It must match the file byte-for-byte, including "
                "leading indentation and newlines (the target often spans "
                "several lines). Closest lines in the file:\n"
                f"{hint_text}\n"
                "Re-read these exact lines and copy them verbatim as "
                "old_str."
            )
        occurrences = content.count(old_str)
        new_content = content.replace(old_str, new_str)
        write = self._exec(
            f"cat > {shlex.quote(filepath)}", input_data=new_content
        )
        if write["exit_code"] != 0:
            raise IOError(
                f"edit_file failed to write: {write['stderr'].strip()}"
            )
        return f"Success: Replaced {occurrences} occurrence(s)."

    def list_files(self, directory: str, pattern: str = "*") -> str:
        """List files in a directory matching a given pattern.

        Args:
            directory: The directory path to search in.
            pattern: Glob pattern to match (e.g., '*.py', '*test*').

        Returns:
            A list of matching file paths, one per line.
        """
        out = self._exec(
            f"find {shlex.quote(directory)} -type f "
            f"-name {shlex.quote(pattern)}"
        )
        if out["exit_code"] != 0:
            return f"Error: {out['stderr'].strip()}"
        return out["stdout"].strip() or f"No files matching '{pattern}'."

    # Code Search Tools

    def search_code(self, pattern: str, file_pattern: str = "*.py") -> str:
        """Search for a regex pattern across the testbed.

        Args:
            pattern: Regular expression to search for.
            file_pattern: Glob pattern to filter files (e.g., '*.py').

        Returns:
            Matching lines formatted as '/path:line content', capped
            at 100 results.
        """
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
        """Find a function or class definition by name.

        Args:
            name: The function or class name to search for.

        Returns:
            Matching definition lines from the testbed.
        """
        return self.search_code(f"(def|class) {name}")

    def find_references(
        self, name: str,
    ) -> str:
        """Find all usages of a symbol in the testbed.

        Args:
            name: Symbol name to search for.

        Returns:
            Matching lines containing the symbol name.
        """
        return self.search_code(name)

    # Execution Tools

    def run_command(self, command: str, workdir: str = TESTBED) -> str:
        """Run an arbitrary bash command in the Docker container.

        Args:
            command: Command to execute.
            workdir: Working directory inside the container.

        Returns:
            Formatted string with stdout, stderr, and exit code.
        """
        out = self._exec(command, workdir)
        return (
            f"STDOUT:\n{out['stdout']}\n\nSTDERR:\n{out['stderr']}"
            f"\n\nEXIT_CODE:\n{out['exit_code']}"
        )

    def get_patch(self) -> str:
        """Return the current git diff from the testbed.

        Returns:
            Unified diff string of all uncommitted changes.
        """
        out = self._exec("git -c core.fileMode=false diff")
        return out["stdout"]

    def run_tests(self) -> str:
        """Run the evaluation script inside the Docker container.

        Returns:
            Formatted string with stdout, stderr, and exit code.
        """
        out = self._exec(self._eval_script, timeout=900)
        return (
            f"STDOUT:\n{out['stdout']}\n\nSTDERR:\n{out['stderr']}"
            f"\n\nEXIT_CODE:\n{out['exit_code']}"
        )

    def run(self):
        """Start the MCP server and clean up the container on exit."""
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
