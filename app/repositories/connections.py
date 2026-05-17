import json
import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConnectionConfig:
    connection_ref: str
    dialect: str
    dsn: str = ""
    connect_timeout_seconds: int = 10
    statement_timeout_ms: int = 30000
    extra: dict[str, Any] = field(default_factory=dict)

    def to_registry_entry(self) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "connection_ref": self.connection_ref,
            "dialect": self.dialect,
        }
        if self.dsn:
            entry["dsn"] = self.dsn
        entry["connect_timeout_seconds"] = self.connect_timeout_seconds
        entry["statement_timeout_ms"] = self.statement_timeout_ms
        entry.update(self.extra)
        return entry


class ConnectionsFileRepository:
    def __init__(self, file_path: str) -> None:
        self._file_path = file_path
        self._configs: dict[str, ConnectionConfig] = {}
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self._file_path):
            return
        with open(self._file_path, "r", encoding="utf-8") as f:
            data: list[dict[str, Any]] = json.load(f)
        for entry in data:
            ref = entry.get("connection_ref", "")
            if not ref:
                continue
            self._configs[ref] = ConnectionConfig(
                connection_ref=ref,
                dialect=entry.get("dialect", ""),
                dsn=entry.get("dsn", ""),
                connect_timeout_seconds=int(entry.get("connect_timeout_seconds", 10)),
                statement_timeout_ms=int(entry.get("statement_timeout_ms", 30000)),
            )

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self._file_path) or ".", exist_ok=True)
        entries = [cfg.to_registry_entry() for cfg in self._configs.values()]
        with open(self._file_path, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)

    def get(self, connection_ref: str) -> ConnectionConfig | None:
        return self._configs.get(connection_ref)

    def list_all(self) -> list[ConnectionConfig]:
        return list(self._configs.values())

    def upsert(self, config: ConnectionConfig) -> None:
        self._configs[config.connection_ref] = config
        self._save()

    def delete(self, connection_ref: str) -> None:
        self._configs.pop(connection_ref, None)
        self._save()

    def to_registry_json(self) -> str:
        return json.dumps([cfg.to_registry_entry() for cfg in self._configs.values()])
