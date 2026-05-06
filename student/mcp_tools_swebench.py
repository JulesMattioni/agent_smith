from mcp.server.fastmcp import FastMCP
import os
import glob


class SWEBenchTools:
    def __init__(self):
        self.mcp = FastMCP("swebench-tools")
        self._register_tools()

    def _register_tools(self):
        self.mcp.tool()(self.read_file)
        self.mcp.tool()(self.edit_file)
        self.mcp.tool()(self.list_files)

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
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                lines = f.readlines()

            total_lines = len(lines)

            start_idx = max(0, start_line - 1) if start_line is not None else 0
            end_idx = (
                end_line
                if end_line is not None and end_line != -1
                else total_lines
            )

            end_idx = min(end_idx, total_lines)

            output = []
            for i in range(start_idx, end_idx):
                output.append(f"{i + 1}: {lines[i].rstrip(-1)}")

            if not output:
                return "Error: No lines found in the specified range."

            return "\n".join(output)

        except FileNotFoundError:
            return f"Error: File '{filepath}' not found."
        except Exception as e:
            return f"Error reading file: {str(e)}"

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
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            if old_str not in content:
                return (
                    "Error: 'old_str' not found in the file. No changes "
                    "made. Make sure the indentation and line breaks match "
                    "exactly."
                )

            occurrences = content.count(old_str)
            new_content = content.replace(old_str, new_str)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(new_content)

            return (
                f"Success: Replaced {occurrences} occurrence(s) of the string."
            )

        except FileNotFoundError:
            return f"Error: File '{filepath}' not found."
        except Exception as e:
            return f"Error editing file: {str(e)}"

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
        try:
            if not os.path.isdir(directory):
                return f"Error: Directory '{directory}' not found."

            search_path = os.path.join(directory, "**", pattern)
            files = glob.glob(search_path, recursive=True)

            if not files:
                return (
                    f"No files found matching pattern '{pattern}' "
                    f"in '{directory}'."
                )

            files = [f for f in files if os.path.isfile(f)]
            return "\n".join(files)

        except Exception as e:
            return f"Error listing files: {str(e)}"

    def search_code(self, directory: str, query: str) -> str:
        """
        Search for an exact string or keyword across all Python files in a directory.

        Args:
            directory: The directory path to search in.
            query: The exact string to search for.

        Returns:
            A list of matches formatted as 'filepath:line_number: matched_line_content'.
        """
        try:
            if not os.path.isdir(directory):
                return f"Error: Directory '{directory}' not found."

            matches = []
            for filepath in glob.glob(
                os.path.join(directory, "**", "*.py"), recursive=True
            ):
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        for i, line in enumerate(f):
                            if query in line:
                                matches.append(
                                    f"{filepath}:{i + 1}: {line.strip()}"
                                )
                except Exception:
                    continue

            if not matches:
                return f"No matches found for '{query}' in '{directory}'."

            if len(matches) > 100:
                return (
                    "\n".join(matches[:100])
                    + f"\n...and {len(matches) - 100} more matches. Please refine your search."
                )

            return "\n".join(matches)

        except Exception as e:
            return f"Error searching code: {str(e)}"

    def search_function_or_class(self, directory: str, name: str) -> str:
        """
        Search for the definition of a specific Python function or class (e.g., 'def my_func' or 'class MyClass').

        Args:
            directory: The directory path to search in.
            name: The exact name of the function or class.

        Returns:
            A list of file paths and line numbers where the definition was found.
        """
        def_query = f"def {name}"
        class_query = f"class {name}"

        try:
            matches = []
            for filepath in glob.glob(
                os.path.join(directory, "**", "*.py"), recursive=True
            ):
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        for i, line in enumerate(f):
                            if def_query in line or class_query in line:
                                matches.append(
                                    f"{filepath}:{i + 1}: {line.strip()}"
                                )
                except Exception:
                    continue

            if not matches:
                return f"No definition found for '{name}' in '{directory}'."

            return "\n".join(matches)

        except Exception as e:
            return f"Error searching for definition: {str(e)}"

    def find_references(self, directory: str, name: str) -> str:
        """
        Find where a specific function, class, or variable is used/called in the codebase.

        Args:
            directory: The directory path to search in.
            name: The name of the identifier to find references for.

        Returns:
            A list of matches showing where the identifier is used.
        """
        return self.search_code(directory, name)

    def run(self):
        self.mcp.run()


if __name__ == "__main__":
    server = SWEBenchTools()
    server.run()
