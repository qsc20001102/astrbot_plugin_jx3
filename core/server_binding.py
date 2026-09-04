import json
from pathlib import Path
from typing import Any, Iterable

from .sqlite import AsyncSQLiteDB


class ServerBindingService:
    """维护会话区服绑定、区服别名与指令解析所需的区服目录。"""

    ALL_SERVERS_KEYWORD = "全区"

    def __init__(self, sqlite: AsyncSQLiteDB, seed_path: Path):
        self.sql = sqlite
        self.seed_path = seed_path
        self._remote_servers: set[str] = set()
        self._known_servers: set[str] = set()
        self._server_lookup: dict[str, str] = {}

    async def initialize(self):
        await self.sql.execute(
            """
            CREATE TABLE IF NOT EXISTS session_server_bindings (
                session_id TEXT PRIMARY KEY,
                server TEXT NOT NULL
            )
            """
        )
        await self.sql.execute(
            """
            CREATE TABLE IF NOT EXISTS server_aliases (
                server TEXT PRIMARY KEY,
                aliases TEXT NOT NULL DEFAULT '[]'
            )
            """
        )
        await self._seed_aliases()
        await self._reload_cache()

    async def _seed_aliases(self):
        try:
            records = json.loads(self.seed_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"读取区服别名种子数据失败：{exc}") from exc

        if not isinstance(records, list):
            raise RuntimeError("区服别名种子数据必须是数组")

        for record in records:
            if not isinstance(record, dict):
                continue
            server = self._clean(record.get("server"))
            raw_aliases = record.get("aliases") or []
            if not server or not isinstance(raw_aliases, list):
                continue
            aliases = []
            seen: set[str] = set()
            for value in raw_aliases:
                alias = self._clean(value)
                key = self._key(alias)
                if alias and key != self._key(server) and key not in seen:
                    seen.add(key)
                    aliases.append(alias)
            await self.sql.execute(
                """
                INSERT OR IGNORE INTO server_aliases (server, aliases)
                VALUES (?, ?)
                """,
                (server, json.dumps(aliases, ensure_ascii=False)),
            )

    async def _reload_cache(self):
        bindings = await self.list_bindings()
        alias_rows = await self.list_aliases()
        known = set(self._remote_servers)
        known.update(row["server"] for row in bindings)
        known.update(row["server"] for row in alias_rows)

        lookup = {self._key(server): server for server in known}
        for row in alias_rows:
            server = row["server"]
            lookup.setdefault(self._key(server), server)
            for alias in row["aliases"]:
                # 新增的官方区服名优先于历史别名，避免目录更新后误解析。
                lookup.setdefault(self._key(alias), server)

        self._known_servers = known
        self._server_lookup = lookup

    async def update_server_catalog(self, servers: Iterable[str]):
        self._remote_servers = {
            normalized
            for value in servers
            if (normalized := self._clean(value))
        }
        await self._reload_cache()

    def known_servers(self) -> list[str]:
        return sorted(self._known_servers)

    def is_known_server(self, value: Any) -> bool:
        return self._key(value) in self._server_lookup

    def resolve_server(self, value: Any) -> str:
        server = self._clean(value)
        return self._server_lookup.get(self._key(server), server)

    def is_all_servers_query(self, value: Any) -> bool:
        """判断指令中的区服参数是否要求查询全区。"""
        return self._key(value) == self._key(self.ALL_SERVERS_KEYWORD)

    def resolve_query_server(self, value: Any) -> str:
        """解析查询区服；“全区”作为保留值转换为接口所需的空字符串。"""
        if self.is_all_servers_query(value):
            return ""
        return self.resolve_server(value)

    async def get_binding(self, session_id: str) -> str:
        row = await self.sql.select_one(
            "session_server_bindings",
            "session_id=?",
            (session_id,),
        )
        return self._clean(row.get("server")) if row else ""

    async def set_binding(self, session_id: str, server: str):
        session_id = self._clean(session_id)
        server = self.resolve_server(server)
        if not session_id:
            raise ValueError("会话 ID 不能为空")
        if not server:
            raise ValueError("绑定区服不能为空")
        if len(session_id) > 512 or len(server) > 64:
            raise ValueError("会话 ID 或区服名称过长")

        await self.sql.execute(
            """
            INSERT INTO session_server_bindings (session_id, server)
            VALUES (?, ?)
            ON CONFLICT(session_id) DO UPDATE SET server=excluded.server
            """,
            (session_id, server),
        )
        await self._reload_cache()

    async def delete_binding(self, session_id: str):
        await self.sql.delete(
            "session_server_bindings",
            "session_id=?",
            (self._clean(session_id),),
        )
        await self._reload_cache()

    async def list_bindings(self) -> list[dict[str, str]]:
        rows = await self.sql.fetch_all(
            "SELECT session_id, server FROM session_server_bindings "
            "ORDER BY session_id"
        )
        return [
            {
                "session_id": self._clean(row.get("session_id")),
                "server": self._clean(row.get("server")),
            }
            for row in rows
        ]

    async def set_aliases(self, server: str, aliases: Iterable[str]):
        server = self._clean(server)
        if not server:
            raise ValueError("标准区服名不能为空")
        if len(server) > 64:
            raise ValueError("区服名称过长")

        cleaned_aliases: list[str] = []
        seen: set[str] = set()
        for value in aliases:
            alias = self._clean(value)
            key = self._key(alias)
            if not alias or key == self._key(server) or key in seen:
                continue
            if len(alias) > 64:
                raise ValueError(f"区服别名过长：{alias}")
            seen.add(key)
            cleaned_aliases.append(alias)
        if len(cleaned_aliases) > 50:
            raise ValueError("每个区服最多配置 50 个别名")

        alias_rows = await self.list_aliases()
        occupied: dict[str, str] = {
            self._key(known_server): known_server
            for known_server in self._known_servers
            if self._key(known_server) != self._key(server)
        }
        for row in alias_rows:
            existing_server = row["server"]
            if self._key(existing_server) == self._key(server):
                continue
            occupied[self._key(existing_server)] = existing_server
            for alias in row["aliases"]:
                occupied[self._key(alias)] = existing_server

        for value in [server, *cleaned_aliases]:
            conflict = occupied.get(self._key(value))
            if conflict:
                raise ValueError(f"“{value}”已被区服“{conflict}”使用")

        await self.sql.execute(
            """
            INSERT INTO server_aliases (server, aliases)
            VALUES (?, ?)
            ON CONFLICT(server) DO UPDATE SET aliases=excluded.aliases
            """,
            (server, json.dumps(cleaned_aliases, ensure_ascii=False)),
        )
        await self._reload_cache()

    async def delete_aliases(self, server: str):
        await self.sql.delete(
            "server_aliases",
            "server=?",
            (self._clean(server),),
        )
        await self._reload_cache()

    async def list_aliases(self) -> list[dict[str, Any]]:
        rows = await self.sql.fetch_all(
            "SELECT server, aliases FROM server_aliases ORDER BY server"
        )
        result = []
        for row in rows:
            aliases: list[str] = []
            try:
                raw_aliases = json.loads(row.get("aliases") or "[]")
                if isinstance(raw_aliases, list):
                    aliases = [
                        self._clean(value)
                        for value in raw_aliases
                        if self._clean(value)
                    ]
            except (TypeError, json.JSONDecodeError):
                aliases = []
            result.append(
                {"server": self._clean(row.get("server")), "aliases": aliases}
            )
        return result

    @staticmethod
    def _clean(value: Any) -> str:
        return str(value or "").strip()

    @classmethod
    def _key(cls, value: Any) -> str:
        return cls._clean(value).casefold()
