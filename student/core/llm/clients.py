from abc import ABC, abstractmethod
from .model import LlmResponse
from .key_manager import KeyManager
import requests
import time
import json
import sys
from pydantic import ValidationError


class BaseClient(ABC):
    def __init__(self, model_name: str, provider_name: str, base_url: str):
        self.__provider_name = provider_name
        self._key_manager = KeyManager(self.__provider_name)
        self.model_name = model_name
        self.base_url = base_url

    @abstractmethod
    def generate(
        self, messages: list[dict], stop_sequences: list[str] = None
    ) -> LlmResponse:
        pass


class OpenRouterClient(BaseClient):
    def __init__(
        self, model_name: str, provider_name: str, base_url: str
    ) -> None:
        super().__init__(model_name, provider_name, base_url)

    def generate(
        self, messages: list[dict], stop_sequences: list[str] = None
    ) -> LlmResponse:

        max_attempts = self._key_manager.key_count
        attempts = 0

        while attempts < max_attempts:
            payload = {"messages": messages, "model": self.model_name}
            if stop_sequences:
                payload["stop"] = stop_sequences
            headers = {
                "Authorization": f"Bearer {self._key_manager.current_key}",
                "Content-Type": "application/json",
            }

            start_time = time.time()
            response = requests.post(
                url=f"{self.base_url}/chat/completions",
                headers=headers,
                data=json.dumps(payload),
            )
            elapsed_time = (time.time() - start_time) * 1000

            if response.status_code in [403, 401, 429]:
                print(
                    f"Error {response.status_code}, trying next API key...",
                    file=sys.stderr,
                )
                self._key_manager.rotate_key()
                attempts += 1
                time.sleep(1)
            elif response.status_code == 200:

                data = response.json()
                content = data["choices"][0]["message"]["content"]
                usage = data["usage"]

                try:
                    res = LlmResponse(
                        input_tokens=usage["prompt_tokens"],
                        output_tokens=usage["completion_tokens"],
                        content=content,
                        request_time_ms=elapsed_time,
                        model_name=self.model_name,
                        attempts=attempts + 1,
                    )
                except ValidationError as e:
                    raise ValueError(f"Error in response format: {e}")

                return res

            else:
                print(f"DEBUG API ERROR 400: {response.text}")
                raise ValueError(f"Unknown error {response.status_code}")

        if response.status_code == 429:
            raise ValueError("All API keys rate limit used.")
        raise ValueError("No valid API key.")
