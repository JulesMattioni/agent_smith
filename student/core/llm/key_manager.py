import os
from itertools import cycle


class KeyManager:
    """Manage a pool of API keys with round-robin rotation."""

    def __init__(self, provider_name: str) -> None:
        """Load API keys from the environment and initialize rotation.

        Args:
            provider_name: Provider name; the env var
                ``<PROVIDER>_API_KEYS`` is read for comma-separated keys.

        Raises:
            ValueError: If no keys are found in the environment.
        """
        env_var = f"{provider_name.upper()}_API_KEYS"
        keys_str = os.getenv(env_var, "")
        self.__keys = [k.strip() for k in keys_str.split(",") if k.strip()]

        if not self.__keys:
            raise ValueError(f"No keys found for {env_var}")

        self.__keys_iterator = cycle(self.__keys)
        self.current_key = next(self.__keys_iterator)

    def rotate_key(self) -> str:
        """Advance to the next API key in the pool.

        Returns:
            The newly selected API key.
        """
        self.current_key = next(self.__keys_iterator)
        return self.current_key

    @property
    def key_count(self) -> int:
        """Return the total number of API keys in the pool."""
        return len(self.__keys)
