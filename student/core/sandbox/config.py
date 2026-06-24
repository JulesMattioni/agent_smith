from pydantic import BaseModel, Field
from typing import List


class SandboxConfig(BaseModel):
    """Sandbox configuration for student solutions.
    Uses allowlist approach: only imports in authorized_imports are allowed.
    Everything else is blocked by default.
    """

    authorized_imports: List[str] = Field(
        default_factory=lambda: [
            "math",
            "math.*",
            "collections",
            "collections.*",
            "itertools",
            "re",
            "json",
            "typing",
            "typing.*",
            "functools",
            "operator",
            "heapq",
            "bisect",
            "copy",
            "string",
            "random",
            "datetime",
            "datetime.*",
            "array",
            "cmath",
        ]
    )
    allowed_directories: List[str] = Field(
        default_factory=lambda: ["/testbed", "/tmp/agent"]
    )
    max_execution_time_seconds: int = 30
    max_memory_mb: int = 512

    def describe_constraints(self) -> str:
        """Render the sandbox limits as a prompt-ready text block.

        Built dynamically from this config so the system prompt and the
        sandbox enforcement can never drift apart: change the allowlist
        here and every prompt that embeds this description follows.

        Returns:
            A human-readable description of the import and filesystem
            restrictions, suitable for injection into a system prompt.
        """
        modules = sorted(
            {imp.split(".")[0] for imp in self.authorized_imports}
        )
        dirs = ", ".join(self.allowed_directories)
        return (
            "SANDBOX ENVIRONMENT CONSTRAINTS:\n"
            f"- Allowed imports (host sandbox): {', '.join(modules)}. "
            "Any other import (e.g. os, subprocess) will raise ImportError. "
            "The tools listed above are pre-injected as functions — call them "
            "directly, NEVER import them.\n"
            f"- Filesystem access is restricted to: {dirs}. "
            "open() on any other path raises PermissionError; to work on the "
            "repository, use the provided tools (read_file, edit_file, "
            "run_command) instead."
        )
