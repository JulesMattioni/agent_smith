import os
from itertools import cycle


class KeyManager:
    def __init__(self, provider_name: str) -> None:
        env_var = f"{provider_name.upper()}_API_KEYS"
        keys_str = os.getenv(env_var, "")
        self.__keys = [k.strip() for k in keys_str.split(",") if k.strip()]

        if not self.__keys:
            raise ValueError(f"No keys found for {env_var}")

        self.__keys_iterator = cycle(self.__keys)
        self.current_key = next(self.__keys_iterator)

    def rotate_key(self) -> str:
        self.current_key = next(self.__keys_iterator)
        return self.current_key

    @property
    def key_count(self) -> int:
        return len(self.__keys)