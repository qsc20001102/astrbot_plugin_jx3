from typing import Any

from .sqlite import AsyncSQLiteDB


class SessionControlService:
    """使用 SQLite 保存并缓存插件的会话访问策略。"""

    MODE_ALL = "all"
    MODE_WHITELIST = "whitelist"
    MODE_BLACKLIST = "blacklist"
    MODES = {MODE_ALL, MODE_WHITELIST, MODE_BLACKLIST}

    def __init__(self, sqlite: AsyncSQLiteDB):
        self.sql = sqlite
        self._mode = self.MODE_ALL
        self._entries: dict[str, dict[str, str]] = {}

    async def initialize(self):
        await self.sql.execute(
            """
            CREATE TABLE IF NOT EXISTS session_control_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await self.sql.execute(
            """
            CREATE TABLE IF NOT EXISTS session_control_entries (
                session_id TEXT PRIMARY KEY,
                list_type TEXT NOT NULL CHECK(list_type IN ('whitelist', 'blacklist')),
                remark TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await self.sql.execute(
            """
            INSERT OR IGNORE INTO session_control_settings (key, value)
            VALUES ('mode', 'all')
            """
        )
        await self._reload()

    async def _reload(self):
        setting = await self.sql.fetch_one(
            "SELECT value FROM session_control_settings WHERE key='mode'"
        )
        mode = str(setting.get("value") or "") if setting else ""
        self._mode = mode if mode in self.MODES else self.MODE_ALL

        rows = await self.sql.fetch_all(
            """
            SELECT session_id, list_type, remark
            FROM session_control_entries
            ORDER BY session_id
            """
        )
        self._entries = {
            str(row["session_id"]): {
                "session_id": str(row["session_id"]),
                "list_type": str(row["list_type"]),
                "remark": str(row.get("remark") or ""),
            }
            for row in rows
        }

    @staticmethod
    def _normalize_session_id(session_id: Any) -> str:
        value = str(session_id or "").strip()
        if not value:
            raise ValueError("会话 ID 不能为空")
        if len(value) > 512:
            raise ValueError("会话 ID 不能超过 512 个字符")
        return value

    def is_allowed(self, session_id: Any) -> bool:
        """同步检查缓存策略，供高频消息和推送分发入口调用。"""
        value = str(session_id or "").strip()
        if self._mode == self.MODE_ALL:
            return True

        entry = self._entries.get(value)
        if self._mode == self.MODE_WHITELIST:
            return bool(entry and entry["list_type"] == self.MODE_WHITELIST)
        return not (entry and entry["list_type"] == self.MODE_BLACKLIST)

    async def set_mode(self, mode: Any):
        value = str(mode or "").strip().lower()
        if value not in self.MODES:
            raise ValueError("会话控制模式无效")
        await self.sql.execute(
            """
            INSERT INTO session_control_settings (key, value, updated_at)
            VALUES ('mode', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value=excluded.value,
                updated_at=CURRENT_TIMESTAMP
            """,
            (value,),
        )
        self._mode = value

    async def save_entry(
        self,
        session_id: Any,
        list_type: Any,
        remark: Any = "",
    ):
        normalized_session_id = self._normalize_session_id(session_id)
        normalized_type = str(list_type or "").strip().lower()
        if normalized_type not in {self.MODE_WHITELIST, self.MODE_BLACKLIST}:
            raise ValueError("名单类型必须是白名单或黑名单")
        normalized_remark = str(remark or "").strip()
        if len(normalized_remark) > 200:
            raise ValueError("备注不能超过 200 个字符")

        await self.sql.execute(
            """
            INSERT INTO session_control_entries (
                session_id, list_type, remark, updated_at
            ) VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(session_id) DO UPDATE SET
                list_type=excluded.list_type,
                remark=excluded.remark,
                updated_at=CURRENT_TIMESTAMP
            """,
            (normalized_session_id, normalized_type, normalized_remark),
        )
        self._entries[normalized_session_id] = {
            "session_id": normalized_session_id,
            "list_type": normalized_type,
            "remark": normalized_remark,
        }

    async def delete_entry(self, session_id: Any):
        normalized_session_id = self._normalize_session_id(session_id)
        await self.sql.delete(
            "session_control_entries",
            "session_id=?",
            (normalized_session_id,),
        )
        self._entries.pop(normalized_session_id, None)

    async def get_state(self) -> dict[str, Any]:
        return {
            "mode": self._mode,
            "entries": sorted(
                (dict(entry) for entry in self._entries.values()),
                key=lambda entry: entry["session_id"],
            ),
        }
