import os


class KeyManager:
    """Manage a single pool of API keys, skipping ones proven dead.

    Keys are provider-agnostic: the same pool is tried against whatever
    provider URL the client targets. A key that the provider rejects as
    invalid (HTTP 401/403) is marked dead and never retried for the rest
    of the run, so a mixed pool does not keep probing wrong-provider keys.
    """

    def __init__(self) -> None:
        """Load API keys from the ``API_KEYS`` environment variable.

        Raises:
            ValueError: If no keys are found in the environment.
        """
        keys_str = os.getenv("API_KEYS", "")
        self.__keys = [k.strip() for k in keys_str.split(",") if k.strip()]

        if not self.__keys:
            raise ValueError("No keys found in API_KEYS")

        self.__dead: set[str] = set()
        self.__index = 0
        self.current_key = self.__keys[0]

    def mark_current_dead(self) -> None:
        """Mark the current key as invalid so it is never retried."""
        self.__dead.add(self.current_key)

    def rotate_key(self) -> str | None:
        """Advance to the next key that has not been marked dead.

        Returns:
            The newly selected key, or ``None`` if every key is dead.
        """
        n = len(self.__keys)
        for step in range(1, n + 1):
            candidate = self.__keys[(self.__index + step) % n]
            if candidate not in self.__dead:
                self.__index = (self.__index + step) % n
                self.current_key = candidate
                return candidate
        return None

    @property
    def has_live_keys(self) -> bool:
        """Return whether at least one key is not marked dead."""
        return any(k not in self.__dead for k in self.__keys)

    @property
    def key_count(self) -> int:
        """Return the total number of API keys in the pool."""
        return len(self.__keys)
