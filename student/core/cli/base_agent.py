import argparse
import os
from abc import ABC, abstractmethod
from pydantic import BaseModel


class BaseAgentCLI(ABC):
    """Abstract base class for agent CLI entrypoints."""

    def __init__(self) -> None:
        """Parse CLI arguments and store them."""
        self.args = self._parse_args()

    def _parse_args(self) -> argparse.Namespace:
        """Define and parse shared CLI arguments.

        Returns:
            Parsed argument namespace.
        """
        parser = argparse.ArgumentParser()
        parser.add_argument("--task-file", required=True)
        parser.add_argument("--output", required=True)
        parser.add_argument("--model-name", required=True)
        parser.add_argument("--provider-url", required=True)
        return parser.parse_args()

    def _save_output(self, output: BaseModel) -> None:
        """Serialize and write the output model to the output file.

        Args:
            output: Pydantic model to serialize as JSON.
        """
        out_dir = os.path.dirname(self.args.output)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(self.args.output, "w") as f:
            f.write(output.model_dump_json(indent=2))

    @abstractmethod
    def _load_task(self) -> BaseModel:
        """Load and return the task input from the task file."""
        pass

    @abstractmethod
    def run(self) -> None:
        """Execute the full agent pipeline for the task."""
        pass
