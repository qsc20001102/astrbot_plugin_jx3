from __future__ import annotations

import asyncio
import sqlite3
from typing import TYPE_CHECKING, Any

from .team import TeamNotFoundError

if TYPE_CHECKING:
    from .kungfu_alias import KungfuAliasService
    from .sqlite import AsyncSQLiteDB


class TeamRuleService:
    """Manage session defaults, team overrides, and signup restrictions."""

    RULE_TYPES = {"role", "kungfu"}
    ROLE_TYPES = {"T", "HEALER", "DPS", "BOSS"}
    CAPACITIES = {10, 25}

    def __init__(self, sqlite: AsyncSQLiteDB, kungfu_alias: KungfuAliasService):
        self.sql = sqlite
        self.kungfu_alias = kungfu_alias
        self.write_lock = asyncio.Lock()

    async def initialize(self):
        await self.sql.execute(
            """
            CREATE TABLE IF NOT EXISTS raid_team_rule_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                capacity INTEGER NOT NULL CHECK(capacity IN (10, 25)),
                team_id INTEGER NOT NULL DEFAULT 0 CHECK(team_id >= 0),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(session_id, capacity, team_id)
            )
            """
        )
        await self.sql.execute(
            """
            CREATE TABLE IF NOT EXISTS raid_team_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id INTEGER NOT NULL,
                rule_type TEXT NOT NULL
                    CHECK(rule_type IN ('role', 'kungfu')),
                target_value TEXT NOT NULL DEFAULT '',
                min_count INTEGER NOT NULL DEFAULT 0 CHECK(min_count >= 0),
                max_count INTEGER NOT NULL CHECK(max_count >= 0),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(profile_id) REFERENCES raid_team_rule_profiles(id)
                    ON DELETE CASCADE,
                UNIQUE(profile_id, rule_type, target_value)
            )
            """
        )
        schema = await self.sql.fetch_one(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='raid_team_rules'"
        )
        if schema and "'boss'" in str(schema.get("sql") or ""):
            await self.sql.execute_transaction(
                [
                    ("ALTER TABLE raid_team_rules RENAME TO raid_team_rules_legacy", ()),
                    (
                        """
                        CREATE TABLE raid_team_rules (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            profile_id INTEGER NOT NULL,
                            rule_type TEXT NOT NULL
                                CHECK(rule_type IN ('role', 'kungfu')),
                            target_value TEXT NOT NULL DEFAULT '',
                            min_count INTEGER NOT NULL DEFAULT 0
                                CHECK(min_count >= 0),
                            max_count INTEGER NOT NULL CHECK(max_count >= 0),
                            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            FOREIGN KEY(profile_id)
                                REFERENCES raid_team_rule_profiles(id)
                                ON DELETE CASCADE,
                            UNIQUE(profile_id, rule_type, target_value)
                        )
                        """,
                        (),
                    ),
                    (
                        """
                        INSERT INTO raid_team_rules (
                            id, profile_id, rule_type, target_value,
                            min_count, max_count, created_at, updated_at
                        )
                        SELECT
                            id,
                            profile_id,
                            CASE WHEN rule_type='boss' THEN 'role' ELSE rule_type END,
                            CASE WHEN rule_type='boss' THEN 'BOSS' ELSE target_value END,
                            min_count,
                            max_count,
                            created_at,
                            updated_at
                        FROM raid_team_rules_legacy
                        """,
                        (),
                    ),
                    ("DROP TABLE raid_team_rules_legacy", ()),
                ]
            )
        await self.sql.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_raid_team_rules_profile
            ON raid_team_rules(profile_id, id)
            """
        )

    @staticmethod
    def _session_id(value: Any) -> str:
        session_id = str(value or "").strip()
        if not session_id:
            raise ValueError("会话 ID 不能为空")
        if len(session_id) > 512:
            raise ValueError("会话 ID 不能超过 512 个字符")
        return session_id

    @classmethod
    def _capacity(cls, value: Any) -> int:
        try:
            capacity = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("团队人数只支持 10 或 25") from exc
        if capacity not in cls.CAPACITIES:
            raise ValueError("团队人数只支持 10 或 25")
        return capacity

    @staticmethod
    def _positive_id(value: Any, label: str) -> int:
        try:
            item_id = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label}必须是正整数") from exc
        if item_id <= 0:
            raise ValueError(f"{label}必须是正整数")
        return item_id

    @staticmethod
    def _count(value: Any, label: str) -> int:
        try:
            count = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label}必须是非负整数") from exc
        if count < 0:
            raise ValueError(f"{label}必须是非负整数")
        return count

    async def _team_scope(
        self,
        session_id: str,
        team_id: Any,
    ) -> tuple[int, int]:
        normalized_team_id = self._positive_id(team_id, "团队编号")
        team = await self.sql.fetch_one(
            "SELECT id, capacity FROM raid_teams WHERE id=? AND session_id=?",
            (normalized_team_id, session_id),
        )
        if not team:
            raise TeamNotFoundError("团队不存在")
        return normalized_team_id, int(team["capacity"])

    async def _ensure_default_profile(self, session_id: str, capacity: int) -> int:
        await self.sql.execute(
            """
            INSERT OR IGNORE INTO raid_team_rule_profiles
                (session_id, capacity, team_id)
            VALUES (?, ?, 0)
            """,
            (session_id, capacity),
        )
        profile = await self.sql.fetch_one(
            """
            SELECT id FROM raid_team_rule_profiles
            WHERE session_id=? AND capacity=? AND team_id=0
            """,
            (session_id, capacity),
        )
        if not profile:
            raise RuntimeError("默认团队规则配置创建失败")
        return int(profile["id"])

    async def ensure_session_defaults(self, session_id: Any):
        normalized_session = self._session_id(session_id)
        for capacity in sorted(self.CAPACITIES):
            await self._ensure_default_profile(normalized_session, capacity)

    async def list_sessions(self) -> list[str]:
        rows = await self.sql.fetch_all(
            """
            SELECT DISTINCT session_id
            FROM raid_team_rule_profiles
            ORDER BY session_id
            """
        )
        return [str(row["session_id"]) for row in rows]

    async def _profile(
        self,
        session_id: str,
        capacity: int,
        team_id: int,
    ) -> dict[str, Any] | None:
        return await self.sql.fetch_one(
            """
            SELECT id, session_id, capacity, team_id
            FROM raid_team_rule_profiles
            WHERE session_id=? AND capacity=? AND team_id=?
            """,
            (session_id, capacity, team_id),
        )

    async def _rules(self, profile_id: int) -> list[dict[str, Any]]:
        rows = await self.sql.fetch_all(
            """
            SELECT id, rule_type, target_value, min_count, max_count,
                   created_at, updated_at
            FROM raid_team_rules
            WHERE profile_id=?
            ORDER BY
                CASE rule_type WHEN 'role' THEN 1 ELSE 2 END,
                target_value,
                id
            """,
            (profile_id,),
        )
        for row in rows:
            row["min_count"] = int(row["min_count"])
            row["max_count"] = int(row["max_count"])
        return rows

    async def get_config(
        self,
        session_id: Any,
        capacity: Any = 25,
        team_id: Any = 0,
    ) -> dict[str, Any]:
        async with self.write_lock:
            return await self._get_config(session_id, capacity, team_id)

    async def _get_config(
        self,
        session_id: Any,
        capacity: Any = 25,
        team_id: Any = 0,
    ) -> dict[str, Any]:
        normalized_session = self._session_id(session_id)
        normalized_team_id = int(team_id or 0)
        if normalized_team_id:
            normalized_team_id, normalized_capacity = await self._team_scope(
                normalized_session,
                normalized_team_id,
            )
        else:
            normalized_capacity = self._capacity(capacity)

        await self.ensure_session_defaults(normalized_session)
        default_profile_id = await self._ensure_default_profile(
            normalized_session,
            normalized_capacity,
        )
        profile = None
        if normalized_team_id:
            profile = await self._profile(
                normalized_session,
                normalized_capacity,
                normalized_team_id,
            )
        active_profile_id = int(profile["id"]) if profile else default_profile_id
        return {
            "session_id": normalized_session,
            "capacity": normalized_capacity,
            "team_id": normalized_team_id,
            "inherited": bool(normalized_team_id and not profile),
            "rules": await self._rules(active_profile_id),
        }

    async def _ensure_team_profile(
        self,
        session_id: str,
        capacity: int,
        team_id: int,
    ) -> int:
        profile = await self._profile(session_id, capacity, team_id)
        if profile:
            return int(profile["id"])
        default_profile_id = await self._ensure_default_profile(session_id, capacity)
        await self.sql.execute(
            """
            INSERT OR IGNORE INTO raid_team_rule_profiles
                (session_id, capacity, team_id)
            VALUES (?, ?, ?)
            """,
            (session_id, capacity, team_id),
        )
        profile = await self._profile(session_id, capacity, team_id)
        if not profile:
            raise RuntimeError("团队专属规则配置创建失败")
        profile_id = int(profile["id"])
        await self.sql.execute(
            """
            INSERT OR IGNORE INTO raid_team_rules
                (profile_id, rule_type, target_value, min_count, max_count)
            SELECT ?, rule_type, target_value, min_count, max_count
            FROM raid_team_rules
            WHERE profile_id=?
            """,
            (profile_id, default_profile_id),
        )
        return profile_id

    def _normalize_target(self, rule_type: Any, target_value: Any) -> tuple[str, str]:
        normalized_type = str(rule_type or "").strip().lower()
        if normalized_type not in self.RULE_TYPES:
            raise ValueError("限制类型只能选择职责或心法")
        if normalized_type == "role":
            normalized_role = {
                "奶": "HEALER",
                "老板": "BOSS",
            }.get(str(target_value or "").strip())
            normalized_role = normalized_role or str(target_value or "").strip().upper()
            if normalized_role not in self.ROLE_TYPES:
                raise ValueError("职责只能选择 T、奶、DPS 或老板")
            return normalized_type, normalized_role
        canonical = self.kungfu_alias.match_kungfu(target_value)
        if not canonical:
            raise ValueError("心法必须是心法配置中的标准名称或别名")
        return normalized_type, canonical

    @staticmethod
    def _validate_minimum_totals(rules: list[dict[str, Any]], capacity: int):
        for rule_type in ("role", "kungfu"):
            total = sum(
                int(rule["min_count"])
                for rule in rules
                if rule["rule_type"] == rule_type
            )
            if total > capacity:
                label = "职责" if rule_type == "role" else "心法"
                raise ValueError(f"{label}规则的最小数量合计不能超过 {capacity}")

    async def save_rule(
        self,
        session_id: Any,
        capacity: Any,
        team_id: Any,
        rule_type: Any,
        target_value: Any,
        min_count: Any,
        max_count: Any,
        rule_id: Any = 0,
    ) -> dict[str, Any]:
        async with self.write_lock:
            return await self._save_rule(
                session_id,
                capacity,
                team_id,
                rule_type,
                target_value,
                min_count,
                max_count,
                rule_id,
            )

    async def _save_rule(
        self,
        session_id: Any,
        capacity: Any,
        team_id: Any,
        rule_type: Any,
        target_value: Any,
        min_count: Any,
        max_count: Any,
        rule_id: Any = 0,
    ) -> dict[str, Any]:
        normalized_session = self._session_id(session_id)
        normalized_team_id = int(team_id or 0)
        inherited_profile = False
        if normalized_team_id:
            normalized_team_id, normalized_capacity = await self._team_scope(
                normalized_session,
                normalized_team_id,
            )
            profile = await self._profile(
                normalized_session,
                normalized_capacity,
                normalized_team_id,
            )
            if profile:
                profile_id = int(profile["id"])
            else:
                profile_id = await self._ensure_default_profile(
                    normalized_session,
                    normalized_capacity,
                )
                inherited_profile = True
        else:
            normalized_capacity = self._capacity(capacity)
            profile_id = await self._ensure_default_profile(
                normalized_session,
                normalized_capacity,
            )

        normalized_type, normalized_target = self._normalize_target(
            rule_type,
            target_value,
        )
        normalized_min = self._count(min_count, "最小数量")
        normalized_max = self._count(max_count, "最大数量")
        if normalized_min > normalized_max:
            raise ValueError("最小数量不能大于最大数量")
        if normalized_max > normalized_capacity:
            raise ValueError(f"最大数量不能超过团队人数 {normalized_capacity}")

        normalized_rule_id = int(rule_id or 0)
        current_rules = await self._rules(profile_id)
        original_rule = None
        if normalized_rule_id:
            original_rule = next(
                (
                    rule
                    for rule in current_rules
                    if int(rule["id"]) == normalized_rule_id
                ),
                None,
            )
            if not original_rule:
                raise ValueError("限制规则不存在")
        candidate_rules = [
            rule for rule in current_rules if int(rule["id"]) != normalized_rule_id
        ]
        if any(
            rule["rule_type"] == normalized_type
            and rule["target_value"] == normalized_target
            for rule in candidate_rules
        ):
            raise ValueError("相同限制目标已经存在")
        candidate_rules.append(
            {
                "rule_type": normalized_type,
                "target_value": normalized_target,
                "min_count": normalized_min,
                "max_count": normalized_max,
            }
        )
        self._validate_minimum_totals(candidate_rules, normalized_capacity)

        if inherited_profile:
            profile_id = await self._ensure_team_profile(
                normalized_session,
                normalized_capacity,
                normalized_team_id,
            )
            if original_rule:
                copied_rule = await self.sql.fetch_one(
                    """
                    SELECT id FROM raid_team_rules
                    WHERE profile_id=? AND rule_type=? AND target_value=?
                    """,
                    (
                        profile_id,
                        original_rule["rule_type"],
                        original_rule["target_value"],
                    ),
                )
                if not copied_rule:
                    raise RuntimeError("继承规则复制后无法读取")
                normalized_rule_id = int(copied_rule["id"])

        if normalized_rule_id:
            affected = await self.sql.execute_affected(
                """
                UPDATE raid_team_rules
                SET rule_type=?, target_value=?, min_count=?, max_count=?,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=? AND profile_id=?
                """,
                (
                    normalized_type,
                    normalized_target,
                    normalized_min,
                    normalized_max,
                    normalized_rule_id,
                    profile_id,
                ),
            )
            if not affected:
                raise ValueError("限制规则不存在")
        else:
            try:
                await self.sql.execute(
                    """
                    INSERT INTO raid_team_rules
                        (profile_id, rule_type, target_value, min_count, max_count)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        profile_id,
                        normalized_type,
                        normalized_target,
                        normalized_min,
                        normalized_max,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("相同限制目标已经存在") from exc
        return await self._get_config(
            normalized_session,
            normalized_capacity,
            normalized_team_id,
        )

    async def delete_rule(
        self,
        session_id: Any,
        capacity: Any,
        team_id: Any,
        rule_id: Any,
    ) -> dict[str, Any]:
        async with self.write_lock:
            return await self._delete_rule(session_id, capacity, team_id, rule_id)

    async def _delete_rule(
        self,
        session_id: Any,
        capacity: Any,
        team_id: Any,
        rule_id: Any,
    ) -> dict[str, Any]:
        config = await self._get_config(session_id, capacity, team_id)
        if config["inherited"]:
            raise ValueError("当前团队正在继承默认规则，不能直接删除")
        normalized_rule_id = self._positive_id(rule_id, "规则编号")
        profile = await self._profile(
            config["session_id"],
            config["capacity"],
            config["team_id"],
        )
        if not profile:
            raise ValueError("限制规则配置不存在")
        affected = await self.sql.execute_affected(
            "DELETE FROM raid_team_rules WHERE id=? AND profile_id=?",
            (normalized_rule_id, int(profile["id"])),
        )
        if not affected:
            raise ValueError("限制规则不存在")
        return await self._get_config(
            config["session_id"],
            config["capacity"],
            config["team_id"],
        )

    async def reset_team_rules(self, session_id: Any, team_id: Any) -> dict[str, Any]:
        async with self.write_lock:
            return await self._reset_team_rules(session_id, team_id)

    async def _reset_team_rules(
        self,
        session_id: Any,
        team_id: Any,
    ) -> dict[str, Any]:
        normalized_session = self._session_id(session_id)
        normalized_team_id, capacity = await self._team_scope(
            normalized_session,
            team_id,
        )
        profile = await self._profile(
            normalized_session,
            capacity,
            normalized_team_id,
        )
        if profile:
            await self.sql.execute_transaction(
                [
                    (
                        "DELETE FROM raid_team_rules WHERE profile_id=?",
                        (int(profile["id"]),),
                    ),
                    (
                        "DELETE FROM raid_team_rule_profiles WHERE id=?",
                        (int(profile["id"]),),
                    ),
                ]
            )
        return await self._get_config(normalized_session, capacity, normalized_team_id)

    async def effective_rules(
        self,
        session_id: str,
        capacity: int,
        team_id: int,
    ) -> list[dict[str, Any]]:
        profile = await self._profile(session_id, capacity, team_id)
        if not profile:
            profile = await self._profile(session_id, capacity, 0)
        if not profile:
            return []
        return await self._rules(int(profile["id"]))

    def _matches(self, rule: dict[str, Any], kungfu: str, is_boss: bool) -> bool:
        if is_boss:
            return rule["rule_type"] == "role" and rule["target_value"] == "BOSS"
        if rule["rule_type"] == "role":
            if rule["target_value"] == "BOSS":
                return False
            return self.kungfu_alias.role_type_of(kungfu) == rule["target_value"]
        return kungfu == rule["target_value"]

    @staticmethod
    def _rule_label(rule: dict[str, Any]) -> str:
        if rule["rule_type"] == "role":
            return {"T": "T", "HEALER": "奶", "DPS": "DPS", "BOSS": "老板"}.get(
                rule["target_value"],
                rule["target_value"],
            )
        return f"心法“{rule['target_value']}”"

    async def validate_signup(
        self,
        session_id: str,
        team_id: int,
        capacity: int,
        members: list[dict[str, Any]],
        kungfu: str,
        is_boss: bool,
    ):
        rules = await self.effective_rules(session_id, capacity, team_id)
        if not rules:
            return

        counts: dict[int, int] = {}
        for rule in rules:
            counts[int(rule["id"])] = sum(
                self._matches(rule, member["kungfu"], bool(member["is_boss"]))
                for member in members
            )

        for rule in rules:
            rule_id = int(rule["id"])
            if self._matches(rule, kungfu, is_boss) and counts[rule_id] >= int(
                rule["max_count"]
            ):
                raise ValueError(
                    f"{self._rule_label(rule)}最多允许 {rule['max_count']} 人"
                )

        remaining = capacity - len(members) - 1
        groups = (
            ("role", lambda rule: rule["rule_type"] == "role"),
            ("kungfu", lambda rule: rule["rule_type"] == "kungfu"),
        )
        for _, belongs_to_group in groups:
            required = 0
            labels = []
            for rule in rules:
                if not belongs_to_group(rule):
                    continue
                rule_id = int(rule["id"])
                projected = counts[rule_id] + int(self._matches(rule, kungfu, is_boss))
                deficit = max(0, int(rule["min_count"]) - projected)
                if deficit:
                    required += deficit
                    labels.append(f"{self._rule_label(rule)} {deficit} 人")
            if required > remaining:
                raise ValueError("需要预留报名位置：" + "、".join(labels))
