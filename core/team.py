from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING, Any

from .sqlite import AsyncSQLiteDB

if TYPE_CHECKING:
    from .kungfu_alias import KungfuAliasService
    from .team_rules import TeamRuleService


class TeamNotFoundError(ValueError):
    """Raised when a team is not present in the requested session."""


class TeamService:
    """Store and manage session-scoped raid teams in SQLite."""

    MAX_MEMBERS = 25
    SQUAD_SIZE = 5
    SUPPORTED_CAPACITIES = (10, 25)

    def __init__(
        self,
        sqlite: AsyncSQLiteDB,
        kungfu_alias: KungfuAliasService,
        team_rules: TeamRuleService,
    ):
        self.sql = sqlite
        self.kungfu_alias = kungfu_alias
        self.team_rules = team_rules
        self._write_lock = team_rules.write_lock

    async def initialize(self):
        """Create the team tables and indexes when they do not exist."""
        await self.sql.execute(
            """
            CREATE TABLE IF NOT EXISTS raid_teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                name TEXT NOT NULL,
                announcement TEXT NOT NULL DEFAULT '',
                capacity INTEGER NOT NULL DEFAULT 25
                    CHECK(capacity IN (10, 25)),
                registration_open INTEGER NOT NULL DEFAULT 0
                    CHECK(registration_open IN (0, 1)),
                created_by TEXT NOT NULL DEFAULT '',
                created_by_name TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        columns = await self.sql.fetch_all("PRAGMA table_info(raid_teams)")
        if "capacity" not in {column["name"] for column in columns}:
            await self.sql.execute(
                """
                ALTER TABLE raid_teams
                ADD COLUMN capacity INTEGER NOT NULL DEFAULT 25
                    CHECK(capacity IN (10, 25))
                """
            )
        await self.sql.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_raid_teams_session
            ON raid_teams(session_id, id)
            """
        )
        await self.sql.execute(
            """
            CREATE TABLE IF NOT EXISTS raid_team_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id INTEGER NOT NULL,
                slot_number INTEGER NOT NULL CHECK(slot_number BETWEEN 1 AND 25),
                squad_number INTEGER NOT NULL CHECK(squad_number BETWEEN 1 AND 5),
                kungfu TEXT NOT NULL,
                role_name TEXT NOT NULL COLLATE NOCASE,
                is_boss INTEGER NOT NULL DEFAULT 0 CHECK(is_boss IN (0, 1)),
                user_id TEXT NOT NULL DEFAULT '',
                user_name TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(team_id) REFERENCES raid_teams(id) ON DELETE CASCADE,
                UNIQUE(team_id, slot_number),
                UNIQUE(team_id, role_name)
            )
            """
        )
        await self.sql.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_raid_team_members_team
            ON raid_team_members(team_id, slot_number)
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

    @staticmethod
    def _text(value: Any, label: str, max_length: int, required: bool = True) -> str:
        text = str(value or "").strip()
        if required and not text:
            raise ValueError(f"{label}不能为空")
        if len(text) > max_length:
            raise ValueError(f"{label}不能超过 {max_length} 个字符")
        return text

    @staticmethod
    def _team_id(value: Any) -> int:
        try:
            team_id = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("团队编号必须是正整数") from exc
        if team_id <= 0:
            raise ValueError("团队编号必须是正整数")
        return team_id

    @classmethod
    def _capacity(cls, value: Any) -> int:
        try:
            capacity = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("团队人数只支持 10 或 25") from exc
        if capacity not in cls.SUPPORTED_CAPACITIES:
            raise ValueError("团队人数只支持 10 或 25")
        return capacity

    async def list_teams(self, session_id: Any | None = None) -> list[dict[str, Any]]:
        """List basic team information, optionally scoped to one session.

        Args:
            session_id: Optional AstrBot unified message origin.

        Returns:
            Basic team dictionaries ordered by session and team number.
        """
        params: tuple[Any, ...] = ()
        where = ""
        if session_id is not None:
            where = "WHERE t.session_id=?"
            params = (self._session_id(session_id),)
        rows = await self.sql.fetch_all(
            f"""
            SELECT
                t.id,
                t.session_id,
                t.name,
                t.announcement,
                t.capacity,
                t.registration_open,
                t.created_by,
                t.created_by_name,
                t.created_at,
                t.updated_at,
                COUNT(m.id) AS member_count,
                COALESCE(SUM(m.is_boss), 0) AS boss_count
            FROM raid_teams AS t
            LEFT JOIN raid_team_members AS m ON m.team_id=t.id
            {where}
            GROUP BY t.id
            ORDER BY t.session_id, t.id
            """,
            params,
        )
        for row in rows:
            row["registration_open"] = bool(row["registration_open"])
            row["member_count"] = int(row["member_count"])
            row["boss_count"] = int(row["boss_count"])
        return rows

    async def get_team(self, session_id: Any, team_id: Any) -> dict[str, Any] | None:
        """Get one team and its members within a session.

        Args:
            session_id: AstrBot unified message origin.
            team_id: Generated numeric team identifier.

        Returns:
            Detailed team dictionary, or ``None`` when it does not exist.
        """
        normalized_session = self._session_id(session_id)
        normalized_team_id = self._team_id(team_id)
        team = await self.sql.fetch_one(
            """
            SELECT id, session_id, name, announcement, capacity, registration_open,
                   created_by, created_by_name, created_at, updated_at
            FROM raid_teams
            WHERE id=? AND session_id=?
            """,
            (normalized_team_id, normalized_session),
        )
        if not team:
            return None
        members = await self.sql.fetch_all(
            """
            SELECT id, slot_number, squad_number, kungfu, role_name, is_boss,
                   user_id, user_name, created_at
            FROM raid_team_members
            WHERE team_id=?
            ORDER BY slot_number
            """,
            (normalized_team_id,),
        )
        for member in members:
            member["is_boss"] = bool(member["is_boss"])
            try:
                member["role_type"] = self.kungfu_alias.role_type_of(
                    member["kungfu"]
                )
            except ValueError:
                member["role_type"] = "DPS"
        team["registration_open"] = bool(team["registration_open"])
        team["members"] = members
        team["member_count"] = len(members)
        team["boss_count"] = sum(1 for member in members if member["is_boss"])
        return team

    async def dashboard(self) -> list[dict[str, Any]]:
        """Return all teams with member details for the authenticated WebUI."""
        teams = await self.list_teams()
        detailed = []
        for team in teams:
            item = await self.get_team(team["session_id"], team["id"])
            if item:
                detailed.append(item)
        return detailed

    async def create_team(
        self,
        session_id: Any,
        name: Any,
        capacity: Any,
        announcement: Any = "",
        created_by: Any = "",
        created_by_name: Any = "",
    ) -> dict[str, Any]:
        """Create a closed team and return its generated number.

        Args:
            session_id: AstrBot unified message origin.
            name: Team display name.
            capacity: Team member limit; only 10 and 25 are supported.
            announcement: Optional team announcement.
            created_by: Creator platform user ID.
            created_by_name: Creator display name.

        Returns:
            The newly created detailed team.
        """
        normalized_session = self._session_id(session_id)
        normalized_name = self._text(name, "团名", 80)
        normalized_capacity = self._capacity(capacity)
        normalized_announcement = self._text(announcement, "公告", 500, False)
        normalized_creator = self._text(created_by, "创建人 ID", 128, False)
        normalized_creator_name = self._text(created_by_name, "创建人名称", 100, False)
        async with self._write_lock:
            await self.team_rules.ensure_session_defaults(normalized_session)
            cursor = await self.sql.conn.execute(
                """
                INSERT INTO raid_teams (
                    session_id, name, capacity, announcement, created_by,
                    created_by_name
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized_session,
                    normalized_name,
                    normalized_capacity,
                    normalized_announcement,
                    normalized_creator,
                    normalized_creator_name,
                ),
            )
            await self.sql.conn.commit()
            team_id = cursor.lastrowid
            await cursor.close()
        team = await self.get_team(normalized_session, team_id)
        if not team:
            raise RuntimeError("团队创建后无法读取")
        return team

    async def set_registration(
        self,
        session_id: Any,
        team_id: Any,
        registration_open: bool,
    ) -> dict[str, Any] | None:
        """Open or close registration for one session-scoped team.

        Args:
            session_id: AstrBot unified message origin.
            team_id: Generated numeric team identifier.
            registration_open: Whether new registrations are accepted.

        Returns:
            Updated team details, or ``None`` when the team does not exist.
        """
        normalized_session = self._session_id(session_id)
        normalized_team_id = self._team_id(team_id)
        async with self._write_lock:
            affected = await self.sql.execute_affected(
                """
                UPDATE raid_teams
                SET registration_open=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=? AND session_id=?
                """,
                (int(registration_open), normalized_team_id, normalized_session),
            )
        if not affected:
            return None
        return await self.get_team(normalized_session, normalized_team_id)

    async def end_team(self, session_id: Any, team_id: Any) -> bool:
        """Delete one team and every registration in it.

        Args:
            session_id: AstrBot unified message origin.
            team_id: Generated numeric team identifier.

        Returns:
            Whether a team was deleted.
        """
        normalized_session = self._session_id(session_id)
        normalized_team_id = self._team_id(team_id)
        async with self._write_lock:
            team = await self.sql.fetch_one(
                "SELECT id FROM raid_teams WHERE id=? AND session_id=?",
                (normalized_team_id, normalized_session),
            )
            if not team:
                return False
            await self.sql.execute_transaction(
                [
                    (
                        "DELETE FROM raid_team_members WHERE team_id=?",
                        (normalized_team_id,),
                    ),
                    (
                        """
                        DELETE FROM raid_team_rules
                        WHERE profile_id IN (
                            SELECT id FROM raid_team_rule_profiles
                            WHERE session_id=? AND team_id=?
                        )
                        """,
                        (normalized_session, normalized_team_id),
                    ),
                    (
                        """
                        DELETE FROM raid_team_rule_profiles
                        WHERE session_id=? AND team_id=?
                        """,
                        (normalized_session, normalized_team_id),
                    ),
                    (
                        "DELETE FROM raid_teams WHERE id=? AND session_id=?",
                        (normalized_team_id, normalized_session),
                    ),
                ]
            )
        return True

    async def end_all(self, session_id: Any) -> int:
        """Delete every team and registration in one session.

        Args:
            session_id: AstrBot unified message origin.

        Returns:
            Number of deleted teams.
        """
        normalized_session = self._session_id(session_id)
        async with self._write_lock:
            row = await self.sql.fetch_one(
                "SELECT COUNT(*) AS count FROM raid_teams WHERE session_id=?",
                (normalized_session,),
            )
            count = int(row["count"]) if row else 0
            await self.sql.execute_transaction(
                [
                    (
                        """
                        DELETE FROM raid_team_members
                        WHERE team_id IN (
                            SELECT id FROM raid_teams WHERE session_id=?
                        )
                        """,
                        (normalized_session,),
                    ),
                    (
                        """
                        DELETE FROM raid_team_rules
                        WHERE profile_id IN (
                            SELECT p.id FROM raid_team_rule_profiles AS p
                            INNER JOIN raid_teams AS t ON t.id=p.team_id
                            WHERE t.session_id=? AND p.team_id > 0
                        )
                        """,
                        (normalized_session,),
                    ),
                    (
                        """
                        DELETE FROM raid_team_rule_profiles
                        WHERE session_id=? AND team_id > 0
                        """,
                        (normalized_session,),
                    ),
                    (
                        "DELETE FROM raid_teams WHERE session_id=?",
                        (normalized_session,),
                    ),
                ]
            )
        return count

    async def clear_members(self, session_id: Any, team_id: Any) -> int | None:
        """Remove every registration from one team while preserving the team.

        Args:
            session_id: AstrBot unified message origin.
            team_id: Generated numeric team identifier.

        Returns:
            Number of removed members, or ``None`` when the team does not exist.
        """
        normalized_session = self._session_id(session_id)
        normalized_team_id = self._team_id(team_id)
        async with self._write_lock:
            team = await self.sql.fetch_one(
                "SELECT id FROM raid_teams WHERE id=? AND session_id=?",
                (normalized_team_id, normalized_session),
            )
            if not team:
                return None
            cursor = await self.sql.conn.execute(
                "DELETE FROM raid_team_members WHERE team_id=?",
                (normalized_team_id,),
            )
            await self.sql.conn.commit()
            affected = cursor.rowcount
            await cursor.close()
        return affected

    async def signup(
        self,
        session_id: Any,
        team_id: Any,
        kungfu: Any,
        role_name: Any,
        is_boss: bool = False,
        user_id: Any = "",
        user_name: Any = "",
    ) -> dict[str, Any]:
        """Register a role in the first available slot of an open team.

        Raises:
            TeamNotFoundError: The team is absent from the requested session.
            ValueError: Registration is closed, full, or the role already exists.
        """
        normalized_session = self._session_id(session_id)
        normalized_team_id = self._team_id(team_id)
        requested_kungfu = self._text(kungfu, "心法", 50)
        normalized_role = self._text(role_name, "角色名", 80)
        normalized_user = self._text(user_id, "报名人 ID", 128, False)
        normalized_user_name = self._text(user_name, "报名人名称", 100, False)

        async with self._write_lock:
            await self.sql.conn.execute("BEGIN IMMEDIATE")
            try:
                team = await self.sql.fetch_one(
                    """
                    SELECT registration_open, capacity
                    FROM raid_teams
                    WHERE id=? AND session_id=?
                    """,
                    (normalized_team_id, normalized_session),
                )
                if not team:
                    raise TeamNotFoundError("团队不存在")
                normalized_kungfu = self.kungfu_alias.match_kungfu(requested_kungfu)
                if not normalized_kungfu:
                    raise ValueError("心法必须是心法配置中的标准名称或别名")
                if not team["registration_open"]:
                    raise ValueError("该团队尚未打开报名")
                existing = await self.sql.fetch_one(
                    """
                    SELECT id FROM raid_team_members
                    WHERE team_id=? AND role_name=? COLLATE NOCASE
                    """,
                    (normalized_team_id, normalized_role),
                )
                if existing:
                    raise ValueError(f"角色 {normalized_role} 已在该团队中")
                used_rows = await self.sql.fetch_all(
                    """
                    SELECT slot_number, kungfu, is_boss FROM raid_team_members
                    WHERE team_id=? ORDER BY slot_number
                    """,
                    (normalized_team_id,),
                )
                used_slots = {int(row["slot_number"]) for row in used_rows}
                capacity = int(team["capacity"])
                await self.team_rules.validate_signup(
                    normalized_session,
                    normalized_team_id,
                    capacity,
                    used_rows,
                    normalized_kungfu,
                    bool(is_boss),
                )
                slot_number = next(
                    (slot for slot in range(1, capacity + 1) if slot not in used_slots),
                    None,
                )
                if slot_number is None:
                    raise ValueError(f"该团队已满 {capacity} 人")
                squad_number = ((slot_number - 1) // self.SQUAD_SIZE) + 1
                cursor = await self.sql.conn.execute(
                    """
                    INSERT INTO raid_team_members (
                        team_id, slot_number, squad_number, kungfu, role_name,
                        is_boss, user_id, user_name
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        normalized_team_id,
                        slot_number,
                        squad_number,
                        normalized_kungfu,
                        normalized_role,
                        int(bool(is_boss)),
                        normalized_user,
                        normalized_user_name,
                    ),
                )
                member_id = cursor.lastrowid
                await cursor.close()
                await self.sql.conn.commit()
            except sqlite3.IntegrityError as exc:
                await self.sql.conn.rollback()
                raise ValueError("角色名或团队位置发生冲突，请重试") from exc
            except Exception:
                await self.sql.conn.rollback()
                raise
        member = await self.sql.fetch_one(
            """
            SELECT id, slot_number, squad_number, kungfu, role_name, is_boss,
                   user_id, user_name, created_at
            FROM raid_team_members WHERE id=?
            """,
            (member_id,),
        )
        if not member:
            raise RuntimeError("报名成功后无法读取成员")
        member["is_boss"] = bool(member["is_boss"])
        member["role_type"] = self.kungfu_alias.role_type_of(member["kungfu"])
        return member

    async def update_member(
        self,
        session_id: Any,
        team_id: Any,
        role_name: Any,
        new_role_name: Any,
        kungfu: Any,
        is_boss: bool,
    ) -> dict[str, Any]:
        """Update a member while preserving its current team position."""
        normalized_session = self._session_id(session_id)
        normalized_team_id = self._team_id(team_id)
        normalized_role = self._text(role_name, "原角色名", 80)
        normalized_new_role = self._text(new_role_name, "新角色名", 80)
        requested_kungfu = self._text(kungfu, "心法", 50)

        async with self._write_lock:
            await self.sql.conn.execute("BEGIN IMMEDIATE")
            try:
                team = await self.sql.fetch_one(
                    """
                    SELECT capacity FROM raid_teams
                    WHERE id=? AND session_id=?
                    """,
                    (normalized_team_id, normalized_session),
                )
                if not team:
                    raise TeamNotFoundError("团队不存在")
                canonical_kungfu = self.kungfu_alias.match_kungfu(requested_kungfu)
                if not canonical_kungfu:
                    raise ValueError("心法必须是心法配置中的标准名称或别名")
                member = await self.sql.fetch_one(
                    """
                    SELECT id, slot_number FROM raid_team_members
                    WHERE team_id=? AND role_name=? COLLATE NOCASE
                    """,
                    (normalized_team_id, normalized_role),
                )
                if not member:
                    raise ValueError(f"团队中没有角色 {normalized_role}")
                other_members = await self.sql.fetch_all(
                    """
                    SELECT slot_number, kungfu, is_boss
                    FROM raid_team_members
                    WHERE team_id=? AND id<>?
                    ORDER BY slot_number
                    """,
                    (normalized_team_id, int(member["id"])),
                )
                await self.team_rules.validate_signup(
                    normalized_session,
                    normalized_team_id,
                    int(team["capacity"]),
                    other_members,
                    canonical_kungfu,
                    bool(is_boss),
                )
                await self.sql.conn.execute(
                    """
                    UPDATE raid_team_members
                    SET role_name=?, kungfu=?, is_boss=?
                    WHERE id=?
                    """,
                    (
                        normalized_new_role,
                        canonical_kungfu,
                        int(bool(is_boss)),
                        int(member["id"]),
                    ),
                )
                await self.sql.conn.commit()
            except sqlite3.IntegrityError as exc:
                await self.sql.conn.rollback()
                raise ValueError("新角色名已在该团队中") from exc
            except Exception:
                await self.sql.conn.rollback()
                raise

        updated = await self.sql.fetch_one(
            """
            SELECT id, slot_number, squad_number, kungfu, role_name, is_boss,
                   user_id, user_name, created_at
            FROM raid_team_members WHERE id=?
            """,
            (int(member["id"]),),
        )
        if not updated:
            raise RuntimeError("成员修改后无法读取")
        updated["is_boss"] = bool(updated["is_boss"])
        updated["role_type"] = self.kungfu_alias.role_type_of(updated["kungfu"])
        return updated

    async def swap_slots(
        self,
        session_id: Any,
        team_id: Any,
        first_slot: Any,
        second_slot: Any,
    ) -> dict[str, Any]:
        """Swap two occupied/empty positions in one session-scoped team."""
        normalized_session = self._session_id(session_id)
        normalized_team_id = self._team_id(team_id)
        try:
            normalized_first = int(first_slot)
            normalized_second = int(second_slot)
        except (TypeError, ValueError) as exc:
            raise ValueError("位置必须是正整数") from exc

        async with self._write_lock:
            await self.sql.conn.execute("BEGIN IMMEDIATE")
            try:
                team = await self.sql.fetch_one(
                    """
                    SELECT capacity FROM raid_teams
                    WHERE id=? AND session_id=?
                    """,
                    (normalized_team_id, normalized_session),
                )
                if not team:
                    raise TeamNotFoundError("团队不存在")
                capacity = int(team["capacity"])
                if not 1 <= normalized_first <= capacity:
                    raise ValueError(f"位置必须在 1 到 {capacity} 之间")
                if not 1 <= normalized_second <= capacity:
                    raise ValueError(f"位置必须在 1 到 {capacity} 之间")
                if normalized_first == normalized_second:
                    await self.sql.conn.rollback()
                    current = await self.get_team(normalized_session, normalized_team_id)
                    if not current:
                        raise TeamNotFoundError("团队不存在")
                    return current

                members = await self.sql.fetch_all(
                    """
                    SELECT id, team_id, slot_number, squad_number, kungfu,
                           role_name, is_boss, user_id, user_name, created_at
                    FROM raid_team_members
                    WHERE team_id=? AND slot_number IN (?, ?)
                    ORDER BY slot_number
                    """,
                    (normalized_team_id, normalized_first, normalized_second),
                )
                if not members:
                    raise ValueError("两个位置都是空位，无需交换")
                by_slot = {int(item["slot_number"]): item for item in members}
                first_member = by_slot.get(normalized_first)
                second_member = by_slot.get(normalized_second)
                if first_member and second_member:
                    await self.sql.conn.execute(
                        "DELETE FROM raid_team_members WHERE id IN (?, ?)",
                        (int(first_member["id"]), int(second_member["id"])),
                    )
                    for item, target_slot in (
                        (first_member, normalized_second),
                        (second_member, normalized_first),
                    ):
                        await self.sql.conn.execute(
                            """
                            INSERT INTO raid_team_members (
                                id, team_id, slot_number, squad_number, kungfu,
                                role_name, is_boss, user_id, user_name, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                int(item["id"]),
                                normalized_team_id,
                                target_slot,
                                ((target_slot - 1) // self.SQUAD_SIZE) + 1,
                                item["kungfu"],
                                item["role_name"],
                                int(item["is_boss"]),
                                item["user_id"],
                                item["user_name"],
                                item["created_at"],
                            ),
                        )
                else:
                    item = first_member or second_member
                    target_slot = (
                        normalized_second if first_member else normalized_first
                    )
                    await self.sql.conn.execute(
                        """
                        UPDATE raid_team_members
                        SET slot_number=?, squad_number=?
                        WHERE id=?
                        """,
                        (
                            target_slot,
                            ((target_slot - 1) // self.SQUAD_SIZE) + 1,
                            int(item["id"]),
                        ),
                    )
                await self.sql.conn.commit()
            except Exception:
                await self.sql.conn.rollback()
                raise

        updated_team = await self.get_team(normalized_session, normalized_team_id)
        if not updated_team:
            raise RuntimeError("位置交换后无法读取团队")
        return updated_team

    async def cancel(self, session_id: Any, team_id: Any, role_name: Any) -> bool:
        """Remove a role registration from a session-scoped team.

        Args:
            session_id: AstrBot unified message origin.
            team_id: Generated numeric team identifier.
            role_name: Registered game role name.

        Returns:
            Whether a matching registration was removed.

        Raises:
            TeamNotFoundError: The team is absent from the requested session.
        """
        normalized_session = self._session_id(session_id)
        normalized_team_id = self._team_id(team_id)
        normalized_role = self._text(role_name, "角色名", 80)
        async with self._write_lock:
            team = await self.sql.fetch_one(
                "SELECT id FROM raid_teams WHERE id=? AND session_id=?",
                (normalized_team_id, normalized_session),
            )
            if not team:
                raise TeamNotFoundError("团队不存在")
            cursor = await self.sql.conn.execute(
                """
                DELETE FROM raid_team_members
                WHERE team_id=? AND role_name=? COLLATE NOCASE
                """,
                (normalized_team_id, normalized_role),
            )
            await self.sql.conn.commit()
            affected = cursor.rowcount
            await cursor.close()
        return bool(affected)
