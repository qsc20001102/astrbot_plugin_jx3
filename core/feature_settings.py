"""功能开关的本地持久化。

功能开关只在插件管理页（WebUI）配置，不再出现在 AstrBot 的插件配置结构中，
因此开关状态与插件配置分离，保存在本地 SQLite 的 ``feature_switches`` 表。
"""

from __future__ import annotations

import asyncio
from typing import Any

from . import features
from .sqlite import AsyncSQLiteDB


class FeatureSettingsService:
    """保存并缓存每条指令的启用状态。"""

    def __init__(self, sqlite: AsyncSQLiteDB):
        self.sql = sqlite
        self._enabled = features.command_defaults()
        self._lock = asyncio.Lock()

    async def initialize(self):
        """创建开关表，并载入已经保存的状态。"""
        await self.sql.execute(
            """
            CREATE TABLE IF NOT EXISTS feature_switches (
                command TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        rows = await self.sql.fetch_all(
            "SELECT command, enabled FROM feature_switches"
        )
        stored = {
            str(row["command"]): bool(row["enabled"])
            for row in rows
        }
        self._enabled = features.resolve_enabled(stored)

    def enabled(self) -> dict[str, bool]:
        """返回当前开关快照，供同步的指令表构建流程使用。"""
        return dict(self._enabled)

    async def get_enabled(self) -> dict[str, bool]:
        """等待进行中的保存结束后返回最新开关状态。"""
        async with self._lock:
            return dict(self._enabled)

    async def save(self, selection: Any) -> dict[str, bool]:
        """校验并保存 WebUI 提交的开关选择。

        Args:
            selection: WebUI 提交的 ``{分组: {指令名: bool}}`` 或扁平结构。

        Returns:
            保存后的完整开关状态。

        Raises:
            ValueError: 提交内容中没有任何可识别的指令开关。
        """
        selected = features.normalize_selection(selection)
        if not selected:
            raise ValueError("功能开关数据无效")

        async with self._lock:
            updated = features.resolve_enabled(self._enabled)
            updated.update(selected)
            await self.sql.execute_transaction(
                [
                    (
                        """
                        INSERT INTO feature_switches (
                            command, enabled, updated_at
                        ) VALUES (?, ?, CURRENT_TIMESTAMP)
                        ON CONFLICT(command) DO UPDATE SET
                            enabled=excluded.enabled,
                            updated_at=CURRENT_TIMESTAMP
                        """,
                        (command, int(enabled)),
                    )
                    for command, enabled in updated.items()
                ]
            )
            self._enabled = updated
            return dict(updated)
