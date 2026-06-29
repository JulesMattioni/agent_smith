import os


class KeyManager:
    """Manage a single pool of API keys, skipping ones proven dead.

    Keys are loaded from both our ``API_KEYS`` variable and any standard
    ``*_API_KEY`` variables (see ``__init__``), then merged into one pool.
    Keys are provider-agnostic: the same pool is tried against whatever
    provider URL the client targets. A key that the provider rejects as
    invalid (HTTP 401/403) is marked dead and never retried for the rest
    of the run, so a mixed pool does not keep probing wrong-provider keys.
    """

    def __init__(self) -> None:
        """Load API keys from the environment.

        Two formats are accepted, and both are merged into one pool so the
        agent works whatever the evaluation ``.env`` provides:

        - ``API_KEYS``: our own format, a comma-separated list of keys.
        - Standard ``*_API_KEY`` variables (e.g. ``OPENROUTER_API_KEY``,
          ``GROQ_API_KEY``, ``GEMINI_API_KEY``): each may itself hold a
          comma-separated list. The subject's evaluation injects keys via
          such standard variables, so reading them is required.

        Keys are deduplicated while preserving discovery order. The pool
        stays provider-agnostic: a key the targeted provider rejects
        (401/403) is marked dead and skipped for the rest of the run.

        Raises:
            ValueError: If no keys are found in the environment.
        """
        raw: list[str] = []
        raw.extend(os.getenv("API_KEYS", "").split(","))
        for name, value in os.environ.items():
            if name.endswith("_API_KEY") and value:
                raw.extend(value.split(","))

        seen: set[str] = set()
        self.__keys: list[str] = []
        for key in (k.strip() for k in raw):
            if key and key not in seen:
                seen.add(key)
                self.__keys.append(key)

        if not self.__keys:
            raise ValueError(
                "No API keys found. Set API_KEYS (comma-separated) or a "
                "standard *_API_KEY variable (e.g. OPENROUTER_API_KEY)."
            )

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
    def live_count(self) -> int:
        """Return the number of keys not marked dead."""
        return sum(1 for k in self.__keys if k not in self.__dead)

    @property
    def key_count(self) -> int:
        """Return the total number of API keys in the pool."""
        return len(self.__keys)
