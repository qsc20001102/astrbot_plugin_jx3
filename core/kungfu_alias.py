import json
from pathlib import Path
from typing import Any, Iterable

from .sqlite import AsyncSQLiteDB


class KungfuAliasService:
    """维护本地心法名称、JX3BOX 配装 ID 和别名。"""

    MAX_ALIASES = 5

    def __init__(self, sqlite: AsyncSQLiteDB, seed_path: Path):
        self.sql = sqlite
        self.seed_path = seed_path

    async def initialize(self):
        await self.sql.execute(
            """
            CREATE TABLE IF NOT EXISTS kungfu (
                pzid INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                name1 TEXT,
                name2 TEXT,
                name3 TEXT,
                name4 TEXT,
                name5 TEXT
            )
            """
        )
        await self._seed_defaults()

    async def _seed_defaults(self):
        try:
            records = json.loads(self.seed_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"读取心法种子数据失败：{exc}") from exc

        if not isinstance(records, list):
            raise RuntimeError("心法种子数据必须是数组")

        for record in records:
            if not isinstance(record, dict):
                continue
            pzid = self._parse_pzid(record.get("pzid"))
            name = self._clean(record.get("name"))
            aliases = self._normalize_aliases(name, record.get("aliases") or [])
            values = [*aliases, *([None] * (self.MAX_ALIASES - len(aliases)))]
            await self.sql.execute(
                """
                INSERT OR IGNORE INTO kungfu
                    (pzid, name, name1, name2, name3, name4, name5)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (pzid, name, *values),
            )

    async def list_kungfu(self) -> list[dict[str, Any]]:
        rows = await self.sql.fetch_all(
            "SELECT pzid, name, name1, name2, name3, name4, name5 "
            "FROM kungfu ORDER BY pzid"
        )
        return [
            {
                "pzid": int(row["pzid"]),
                "name": self._clean(row.get("name")),
                "aliases": [
                    alias
                    for key in ("name1", "name2", "name3", "name4", "name5")
                    if (alias := self._clean(row.get(key)))
                ],
            }
            for row in rows
        ]

    async def save_aliases(self, pzid: Any, aliases: Iterable[Any]):
        """只更新已有心法的别名，不允许修改 ID 和标准名称。"""
        normalized_pzid = self._parse_pzid(pzid)
        rows = await self.list_kungfu()
        current = next(
            (row for row in rows if row["pzid"] == normalized_pzid),
            None,
        )
        if current is None:
            raise ValueError("心法不存在")

        normalized_name = current["name"]
        normalized_aliases = self._normalize_aliases(normalized_name, aliases)
        occupied: dict[str, str] = {}
        for row in rows:
            if row["pzid"] == normalized_pzid:
                continue
            for value in [row["name"], *row["aliases"]]:
                occupied[self._key(value)] = row["name"]

        for value in [normalized_name, *normalized_aliases]:
            conflict = occupied.get(self._key(value))
            if conflict:
                raise ValueError(f"“{value}”已被心法“{conflict}”使用")

        values = [
            *normalized_aliases,
            *([None] * (self.MAX_ALIASES - len(normalized_aliases))),
        ]
        await self.sql.execute(
            """
            UPDATE kungfu
            SET name1=?, name2=?, name3=?, name4=?, name5=?
            WHERE pzid=?
            """,
            (*values, normalized_pzid),
        )

    def _normalize_aliases(self, name: str, aliases: Iterable[Any]) -> list[str]:
        result: list[str] = []
        seen: set[str] = {self._key(name)}
        for value in aliases:
            alias = self._clean(value)
            key = self._key(alias)
            if not alias or key in seen:
                continue
            if len(alias) > 64:
                raise ValueError(f"心法别名过长：{alias}")
            seen.add(key)
            result.append(alias)
        if len(result) > self.MAX_ALIASES:
            raise ValueError(f"每个心法最多配置 {self.MAX_ALIASES} 个别名")
        return result

    @staticmethod
    def _parse_pzid(value: Any) -> int:
        try:
            pzid = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("心法 ID 必须是整数") from exc
        if pzid <= 0:
            raise ValueError("心法 ID 必须大于 0")
        return pzid

    @staticmethod
    def _clean(value: Any) -> str:
        return str(value or "").strip()

    @classmethod
    def _key(cls, value: Any) -> str:
        return cls._clean(value).casefold()
