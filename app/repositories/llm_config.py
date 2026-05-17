import json
import os
from dataclasses import dataclass


@dataclass
class LlmConfig:
    provider: str = "stub"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    timeout_seconds: float = 30.0

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "base_url": self.base_url,
            "api_key": self.api_key,
            "model": self.model,
            "timeout_seconds": self.timeout_seconds,
        }


class LlmConfigFileRepository:
    def __init__(self, file_path: str) -> None:
        self._file_path = file_path
        self._config: LlmConfig = LlmConfig()
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self._file_path):
            return
        with open(self._file_path, "r", encoding="utf-8") as f:
            data: dict = json.load(f)
        self._config = LlmConfig(
            provider=data.get("provider", "stub"),
            base_url=data.get("base_url", ""),
            api_key=data.get("api_key", ""),
            model=data.get("model", ""),
            timeout_seconds=float(data.get("timeout_seconds", 30.0)),
        )

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self._file_path) or ".", exist_ok=True)
        with open(self._file_path, "w", encoding="utf-8") as f:
            json.dump(self._config.to_dict(), f, ensure_ascii=False, indent=2)

    def get(self) -> LlmConfig:
        return self._config

    def update(self, config: LlmConfig) -> None:
        self._config = config
        self._save()
