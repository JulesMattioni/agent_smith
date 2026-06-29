import argparse
import os
import dotenv
from abc import ABC, abstractmethod
from pydantic import BaseModel


class BaseAgentCLI(ABC):
    """Abstract base class for agent CLI entrypoints."""

    def __init__(self) -> None:
        """Parse CLI arguments and load the environment."""
        self.args = self._parse_args()
        self._load_env()

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
        parser.add_argument("--env-file", default=None)
        return parser.parse_args()

    def _load_env(self) -> None:
        """Load environment variables from the chosen .env file.

        The evaluation harness passes the keys file via ``--env-file``; we
        honor it explicitly so the agent loads the right file regardless of
        the working directory. Resolution order: the ``--env-file`` flag,
        then the ``ENV_FILE`` environment variable, then dotenv's default
        upward search for a ``.env``. Variables already set in the real
        environment are never overridden.

        Raises:
            FileNotFoundError: If an explicit --env-file path does not exist.
        """
        explicit = self.args.env_file or os.getenv("ENV_FILE")
        if explicit:
            if not os.path.isfile(explicit):
                raise FileNotFoundError(f"--env-file not found: {explicit}")
            dotenv.load_dotenv(explicit, override=False)
        else:
            dotenv.load_dotenv(override=False)

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
