from typing import Any

from .sqlite import AsyncSQLiteDB


class ServerBindingService:
    """维护会话区服绑定。"""

    ALL_SERVERS_KEYWORDS = frozenset({"全区", "全服"})

    def __init__(self, sqlite: AsyncSQLiteDB):
        self.sql = sqlite

    async def initialize(self):
        await self.sql.execute(
            """
            CREATE TABLE IF NOT EXISTS session_server_bindings (
                session_id TEXT PRIMARY KEY,
                server TEXT NOT NULL
            )
            """
        )
        # 区服别名功能已下线，移除旧版本遗留的本地别名表。
        await self.sql.execute("DROP TABLE IF EXISTS server_aliases")

    def is_all_servers_query(self, value: Any) -> bool:
        """判断指令中的区服参数是否要求查询全区/全服。"""
        return self._key(value) in {
            self._key(keyword) for keyword in self.ALL_SERVERS_KEYWORDS
        }

    async def get_binding(self, session_id: str) -> str:
        row = await self.sql.select_one(
            "session_server_bindings",
            "session_id=?",
            (session_id,),
        )
        return self._clean(row.get("server")) if row else ""

    async def set_binding(self, session_id: str, server: str):
        session_id = self._clean(session_id)
        server = self._clean(server)
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

    async def delete_binding(self, session_id: str):
        await self.sql.delete(
            "session_server_bindings",
            "session_id=?",
            (self._clean(session_id),),
        )

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

    @staticmethod
    def _clean(value: Any) -> str:
        return str(value or "").strip()

    @classmethod
    def _key(cls, value: Any) -> str:
        return cls._clean(value).casefold()
