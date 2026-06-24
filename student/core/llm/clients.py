from abc import ABC, abstractmethod
from .model import LlmResponse
from .key_manager import KeyManager
import requests
import time
import json
import re
import sys
from pydantic import ValidationError


class BaseClient(ABC):
    """Abstract base class for LLM API clients."""

    def __init__(self, model_name: str, base_url: str):
        """Initialize the client and load API keys.

        Args:
            model_name: The model identifier to use for generation.
            base_url: Base URL of the LLM API endpoint.
        """
        self._key_manager = KeyManager()
        self.model_name = model_name
        self.base_url = base_url

    @abstractmethod
    def generate(
        self,
        messages: list[dict],
        stop_sequences: list[str] = None,
        max_tokens: int = None,
    ) -> LlmResponse:
        """Generate a response from the LLM.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            stop_sequences: Optional list of stop strings.
            max_tokens: Optional hard cap on generated output tokens.

        Returns:
            An LlmResponse with content and token usage.
        """
        pass


class OpenAICompatibleClient(BaseClient):
    """LLM client for any OpenAI-compatible chat-completions API.

    Works with any provider exposing the ``/chat/completions`` endpoint
    (Groq, OpenRouter, Gemini's OpenAI-compatible URL, etc.); the target
    is selected purely by ``base_url``.
    """

    RATE_LIMIT_MAX_WAIT = 120

    def __init__(self, model_name: str, base_url: str) -> None:
        """Initialize the client.

        Args:
            model_name: The model identifier to use.
            base_url: Base URL of the OpenAI-compatible API.
        """
        super().__init__(model_name, base_url)

    def generate(
        self,
        messages: list[dict],
        stop_sequences: list[str] = None,
        max_tokens: int = None,
    ) -> LlmResponse:
        """Send a chat completion request, rotating keys on failure.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            stop_sequences: Optional list of stop strings.
            max_tokens: Optional hard cap on generated output tokens.

        Returns:
            An LlmResponse with content and token usage.

        Raises:
            ValueError: If all API keys are exhausted or an unexpected
                HTTP status is returned.
        """
        max_rate_limit_retries = 6
        max_server_retries = 4

        attempts = 0
        rate_limit_retries = 0
        rate_limit_sweep = 0
        server_retries = 0

        while True:
            payload = {
                "messages": messages,
                "model": self.model_name,
                "tool_choice": "none",
            }
            if stop_sequences:
                payload["stop"] = stop_sequences
            if max_tokens:
                payload["max_tokens"] = max_tokens
            headers = {
                "Authorization": f"Bearer {self._key_manager.current_key}",
                "Content-Type": "application/json",
            }

            start_time = time.time()
            try:
                response = requests.post(
                    url=f"{self.base_url}/chat/completions",
                    headers=headers,
                    data=json.dumps(payload),
                    timeout=(10, 120),
                )
            except requests.exceptions.RequestException as e:
                server_retries += 1
                if server_retries > max_server_retries:
                    raise ValueError(f"Network error: {e}")
                backoff = min(2**server_retries, 30)
                print(
                    f"Network error ({e.__class__.__name__}), retrying in "
                    f"{backoff}s...",
                    file=sys.stderr,
                )
                time.sleep(backoff)
                continue
            elapsed_time = (time.time() - start_time) * 1000
            attempts += 1

            if response.status_code == 200:
                data = response.json()
                message = data["choices"][0]["message"]
                content = (
                    message.get("content")
                    or message.get("reasoning_content")
                    or message.get("reasoning")
                    or ""
                )
                usage = data.get("usage") or {}

                try:
                    res = LlmResponse(
                        input_tokens=usage.get("prompt_tokens", 0),
                        output_tokens=usage.get("completion_tokens", 0),
                        content=content,
                        request_time_ms=elapsed_time,
                        model_name=self.model_name,
                        attempts=attempts,
                    )
                except ValidationError as e:
                    raise ValueError(f"Error in response format: {e}")

                return res

            elif response.status_code == 429 or (
                response.status_code == 413
                and "rate_limit_exceeded" in (response.text or "")
            ):
                rate_limit_sweep += 1
                if rate_limit_sweep < self._key_manager.live_count:
                    self._key_manager.rotate_key()
                    continue
                rate_limit_sweep = 0
                rate_limit_retries += 1
                if rate_limit_retries > max_rate_limit_retries:
                    raise ValueError("All API keys rate limit used.")
                wait = self._parse_retry_after(response, 5)
                if wait > self.RATE_LIMIT_MAX_WAIT:
                    raise ValueError(
                        f"Rate limit requires waiting {wait}s, over the "
                        f"{self.RATE_LIMIT_MAX_WAIT}s cap; aborting."
                    )
                print(
                    f"All keys rate limited, sleeping {wait}s "
                    f"({rate_limit_retries}/{max_rate_limit_retries})...",
                    file=sys.stderr,
                )
                self._key_manager.rotate_key()
                time.sleep(wait)

            elif response.status_code in [400, 401, 403]:
                self._key_manager.mark_current_dead()
                if self._key_manager.rotate_key() is None:
                    raise ValueError(
                        f"Request rejected by provider ({self.base_url}) "
                        f"with all available keys: {response.text}"
                    )
                print(
                    f"Error {response.status_code}, " "trying next API key...",
                    file=sys.stderr,
                )

            elif response.status_code >= 500:
                server_retries += 1
                if server_retries > max_server_retries:
                    raise ValueError(
                        f"Server error {response.status_code} persisted."
                    )
                backoff = min(2**server_retries, 30)
                print(
                    f"Server error {response.status_code}, retrying in "
                    f"{backoff}s...",
                    file=sys.stderr,
                )
                time.sleep(backoff)

            else:
                print(
                    f"DEBUG API ERROR {response.status_code}: "
                    f"{response.text}",
                    file=sys.stderr,
                )
                raise ValueError(
                    f"Unknown error {response.status_code}: {response.text}"
                )

    def _parse_retry_after(self, response, default: float) -> float:
        """Determine how long to wait before retrying after a 429.

        Reads the ``Retry-After`` header (seconds). Groq also exposes
        ``retry-after-ms`` on some responses; both are honored. Gemini
        instead embeds the delay in the JSON body (``retryDelay: "23s"``
        or a ``Please retry in 23s`` message), which is parsed as a
        fallback. Returns ``default`` when nothing is found.

        Args:
            response: The HTTP response carrying the rate-limit info.
            default: Wait time in seconds used when nothing is found.

        Returns:
            The number of seconds to sleep before the next attempt.
        """
        # Groq-style
        retry_after = response.headers.get("retry-after")
        if retry_after is not None:
            try:
                return float(retry_after)
            except ValueError:
                pass

        retry_after_ms = response.headers.get("retry-after-ms")
        if retry_after_ms is not None:
            try:
                return float(retry_after_ms) / 1000.0
            except ValueError:
                pass

        # Gemini-style
        body = response.text or ""
        match = re.search(r'"retryDelay"\s*:\s*"([0-9.]+)s"', body)
        if not match:
            match = re.search(r"retry in ([0-9.]+)s", body)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass

        return default
