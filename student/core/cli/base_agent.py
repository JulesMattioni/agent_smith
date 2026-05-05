import argparse
import os
from abc import ABC, abstractmethod
from pydantic import BaseModel


class BaseAgentCLI(ABC):
    def __init__(self):
        self.args = self._parse_args()

    def _parse_args(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("--task-file", required=True)
        parser.add_argument("--output", required=True)
        parser.add_argument("--model-name", required=True)
        parser.add_argument("--provider-url", required=True)
        return parser.parse_args()

    def _save_output(self, output: BaseModel):
        os.makedirs(os.path.dirname(self.args.output), exist_ok=True)
        with open(self.args.output, "w") as f:
            f.write(output.model_dump_json(indent=2))

    @abstractmethod
    def _load_task(self) -> BaseModel:
        pass

    @abstractmethod
    def run(self):
        pass
