from __future__ import annotations

from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from .team import TeamNotFoundError, TeamService
from .team_blacklist import TeamBlacklistError, TeamBlacklistService
from .team_rules import TeamRuleService
from .template import load_template


class TeamManager:
    """Implement team command behavior independently from message dispatch."""

    def __init__(
        self,
        team: TeamService,
        team_rules: TeamRuleService,
        team_blacklist: TeamBlacklistService,
        config: dict[str, Any] | None = None,
    ):
        self.team = team
        self.team_rules = team_rules
        self.team_blacklist = team_blacklist
        self.config = config if isinstance(config, dict) else {}

    @staticmethod
    def _result(text: str, success: bool = True) -> dict[str, Any]:
        """Build the standard text result consumed by ``MessageBuilder.plain_msg``.

        Args:
            text: User-facing result text.
            success: Whether the operation succeeded.

        Returns:
            Standard message result dictionary.
        """
        return {
            "code": 200 if success else 400,
            "data": text if success else "",
            "msg": "" if success else text,
        }

    async def _permission_error(self, event: AstrMessageEvent) -> str | None:
        """Check whether the sender may use team management commands.

        Args:
            event: Current message event.

        Returns:
            ``None`` when authorized, otherwise the denial message.
        """
        if event.is_admin():
            return None
        if not event.get_group_id():
            return "仅群主、群管理员或 AstrBot 管理员可使用该指令。"
        try:
            group = await event.get_group()
        except Exception as exc:
            logger.warning(f"获取群管理信息失败，无法授权团队管理指令: {exc}")
            return "无法确认群管理身份，请将账号加入 AstrBot 管理员后重试。"
        if group:
            sender_id = str(event.get_sender_id())
            manager_ids = {str(admin_id) for admin_id in (group.group_admins or [])}
            manager_ids.add(str(group.group_owner or ""))
            if sender_id in manager_ids:
                return None
        return "仅群主、群管理员或 AstrBot 管理员可使用该指令。"

    @staticmethod
    def _format_team_list(teams: list[dict[str, Any]]) -> str:
        """Format basic team information as plain text.

        Args:
            teams: Basic team dictionaries from the data service.

        Returns:
            Plain-text team summary.
        """
        if not teams:
            return "当前会话暂无团队。"
        lines = ["当前会话团队列表："]
        for team in teams:
            status = "报名中" if team["registration_open"] else "未开放"
            lines.append(
                f"#{team['id']} {team['name']}｜{status}｜"
                f"{team['member_count']}/{team['capacity']} 人｜"
                f"老板 {team['boss_count']} 人"
            )
            if team.get("announcement"):
                lines.append(f"  公告：{team['announcement']}")
        return "\n".join(lines)

    @staticmethod
    def _prepare_team_image(team: dict[str, Any]) -> dict[str, Any]:
        """Build fixed slot data and visual roles for the team image."""
        rendered = dict(team)
        members_by_slot = {
            int(member["slot_number"]): member for member in team["members"]
        }
        slots: list[dict[str, Any] | None] = []
        role_labels = {"T": "T", "HEALER": "奶", "DPS": "DPS"}
        role_classes = {"T": "tank", "HEALER": "healer", "DPS": "dps"}
        for slot_number in range(1, int(team["capacity"]) + 1):
            member = members_by_slot.get(slot_number)
            if not member:
                slots.append(None)
                continue
            prepared = dict(member)
            if prepared["is_boss"]:
                prepared["visual_role"] = "老板"
                prepared["role_class"] = "boss"
            else:
                role_type = str(prepared.get("role_type") or "DPS")
                prepared["visual_role"] = role_labels.get(role_type, "DPS")
                prepared["role_class"] = role_classes.get(role_type, "dps")
            slots.append(prepared)
        rendered["slots"] = slots
        rendered["columns"] = int(team["capacity"]) // TeamService.SQUAD_SIZE
        return rendered

    @classmethod
    def _format_team_detail(cls, team: dict[str, Any]) -> str:
        """Format one detailed team for text output."""
        status = "报名中" if team["registration_open"] else "未开放"
        lines = [
            f"团队 #{team['id']} {team['name']}",
            f"状态：{status}｜人数：{team['member_count']}/{team['capacity']}｜"
            f"老板：{team['boss_count']} 人",
            f"公告：{team.get('announcement') or '无'}",
        ]
        if not team["members"]:
            lines.append("成员：暂无")
            return "\n".join(lines)

        role_labels = {"T": "T", "HEALER": "奶", "DPS": "DPS"}
        lines.append("成员：")
        for member in team["members"]:
            responsibility = (
                "老板"
                if member["is_boss"]
                else role_labels.get(str(member.get("role_type")), "DPS")
            )
            lines.append(
                f"{member['slot_number']}. {member['role_name']}｜"
                f"{member['kungfu']}｜{responsibility}"
            )
        return "\n".join(lines)

    def _view_as_text(self) -> bool:
        mode = str(self.config.get("view_output") or "图片").strip().lower()
        return mode in {"文本", "text"}

    @staticmethod
    def _image_result(template: str, data: dict[str, Any]) -> dict[str, Any]:
        return {"code": 200, "data": data, "temp": template, "msg": ""}

    async def _team_list_result(self, session_id: str) -> dict[str, Any]:
        """Return the current session's team list in standard result form.

        Args:
            session_id: AstrBot unified message origin.

        Returns:
            Standard message result containing basic team information.
        """
        teams = await self.team.list_teams(session_id)
        return self._result(self._format_team_list(teams))

    async def create(
        self,
        event: AstrMessageEvent,
        team_name: str = "",
        capacity: str = "",
        *announcement_parts: str,
    ) -> dict[str, Any]:
        """Create a closed team for the current session.

        Args:
            event: Current message event.
            team_name: New team name.
            capacity: Team member limit, either 10 or 25.
            announcement_parts: Optional announcement words.

        Returns:
            Standard message result.
        """
        permission_error = await self._permission_error(event)
        if permission_error:
            return self._result(permission_error, False)
        if not team_name.strip() or not capacity.strip():
            return self._result(
                "用法：开团 团名 人数 [公告]（人数仅支持 10 或 25）", False
            )
        try:
            team = await self.team.create_team(
                event.unified_msg_origin,
                team_name,
                capacity,
                " ".join(announcement_parts),
                event.get_sender_id(),
                event.get_sender_name(),
            )
        except ValueError as exc:
            return self._result(str(exc), False)
        return self._result(
            f"开团成功，团队编号：{team['id']}\n"
            f"团名：{team['name']}\n"
            f"人数：{team['capacity']} 人\n"
            f"公告：{team['announcement'] or '无'}\n"
            f"当前未开放报名，请使用：打开报名 {team['id']}"
        )

    async def open_registration(
        self,
        event: AstrMessageEvent,
        team_id: int = 0,
    ) -> dict[str, Any]:
        """Open registration for one team.

        Args:
            event: Current message event.
            team_id: Generated team number.

        Returns:
            Standard message result.
        """
        permission_error = await self._permission_error(event)
        if permission_error:
            return self._result(permission_error, False)
        if team_id <= 0:
            return self._result("用法：打开报名 团编号", False)
        team = await self.team.set_registration(event.unified_msg_origin, team_id, True)
        if not team:
            return await self._team_list_result(event.unified_msg_origin)
        return self._result(f"团队 #{team_id} 已打开报名。")

    async def close_registration(
        self,
        event: AstrMessageEvent,
        team_id: int = 0,
    ) -> dict[str, Any]:
        """Close registration for one team.

        Args:
            event: Current message event.
            team_id: Generated team number.

        Returns:
            Standard message result.
        """
        permission_error = await self._permission_error(event)
        if permission_error:
            return self._result(permission_error, False)
        if team_id <= 0:
            return self._result("用法：关闭报名 团编号", False)
        team = await self.team.set_registration(
            event.unified_msg_origin, team_id, False
        )
        if not team:
            return await self._team_list_result(event.unified_msg_origin)
        return self._result(f"团队 #{team_id} 已关闭报名。")

    async def end(self, event: AstrMessageEvent, team_id: int = 0) -> dict[str, Any]:
        """Delete one team and all of its registrations.

        Args:
            event: Current message event.
            team_id: Generated team number.

        Returns:
            Standard message result.
        """
        permission_error = await self._permission_error(event)
        if permission_error:
            return self._result(permission_error, False)
        if team_id <= 0:
            return self._result("用法：结束团队 团编号", False)
        if not await self.team.end_team(event.unified_msg_origin, team_id):
            return await self._team_list_result(event.unified_msg_origin)
        return self._result(f"团队 #{team_id} 及其全部报名已删除。")

    async def end_all(self, event: AstrMessageEvent) -> dict[str, Any]:
        """Delete all teams in the current session.

        Args:
            event: Current message event.

        Returns:
            Standard message result.
        """
        permission_error = await self._permission_error(event)
        if permission_error:
            return self._result(permission_error, False)
        count = await self.team.end_all(event.unified_msg_origin)
        return self._result(f"已结束当前会话的全部团队，共删除 {count} 个团队。")

    async def clear_members(
        self,
        event: AstrMessageEvent,
        team_id: int = 0,
    ) -> dict[str, Any]:
        """Remove every registration from one team.

        Args:
            event: Current message event.
            team_id: Generated team number.

        Returns:
            Standard message result.
        """
        permission_error = await self._permission_error(event)
        if permission_error:
            return self._result(permission_error, False)
        if team_id <= 0:
            return self._result("用法：清空报名 团编号", False)
        count = await self.team.clear_members(event.unified_msg_origin, team_id)
        if count is None:
            return await self._team_list_result(event.unified_msg_origin)
        return self._result(f"团队 #{team_id} 的报名已清空，共移除 {count} 人。")

    async def signup(
        self,
        event: AstrMessageEvent,
        team_id: int = 0,
        kungfu: str = "",
        role_name: str = "",
        boss_mark: str = "",
    ) -> dict[str, Any]:
        """Register one role in an open team.

        Args:
            event: Current message event.
            team_id: Generated team number.
            kungfu: Role kungfu name.
            role_name: Game role name.
            boss_mark: Optional boss marker.

        Returns:
            Standard message result.
        """
        if team_id <= 0 or not kungfu.strip() or not role_name.strip():
            return self._result("用法：报名 团编号 心法 角色名 [老板]", False)
        if boss_mark and boss_mark != "老板":
            return self._result("可选标记只能填写“老板”。", False)
        try:
            member = await self.team.signup(
                event.unified_msg_origin,
                team_id,
                kungfu,
                role_name,
                boss_mark == "老板",
                event.get_sender_id(),
                event.get_sender_name(),
            )
        except TeamNotFoundError:
            return await self._team_list_result(event.unified_msg_origin)
        except ValueError as exc:
            return self._result(str(exc), False)
        boss = "，已标记为老板" if member["is_boss"] else ""
        return self._result(
            f"报名成功：团队 #{team_id}，{member['squad_number']}队"
            f"{((member['slot_number'] - 1) % 5) + 1}号位，"
            f"{member['role_name']}（{member['kungfu']}）{boss}。"
        )

    async def cancel_signup(
        self,
        event: AstrMessageEvent,
        team_id: int = 0,
        role_name: str = "",
    ) -> dict[str, Any]:
        """Cancel one role signup.

        Args:
            event: Current message event.
            team_id: Generated team number.
            role_name: Registered game role name.

        Returns:
            Standard message result.
        """
        if team_id <= 0 or not role_name.strip():
            return self._result("用法：取消报名 团编号 角色名", False)
        try:
            removed = await self.team.cancel(
                event.unified_msg_origin,
                team_id,
                role_name,
            )
        except TeamNotFoundError:
            return await self._team_list_result(event.unified_msg_origin)
        except ValueError as exc:
            return self._result(str(exc), False)
        if not removed:
            return self._result(f"团队 #{team_id} 中没有角色 {role_name}。", False)
        return self._result(f"已取消 {role_name} 在团队 #{team_id} 的报名。")

    async def view(
        self,
        event: AstrMessageEvent,
        team_id: int = 0,
    ) -> dict[str, Any]:
        """Return text or image data according to the team output configuration.

        Args:
            event: Current message event.
            team_id: Optional generated team number.

        Returns:
            Standard message result.
        """
        if team_id > 0:
            team = await self.team.get_team(event.unified_msg_origin, team_id)
            if team:
                if self._view_as_text():
                    return self._result(self._format_team_detail(team))
                template = await load_template("team.html")
                return self._image_result(
                    template,
                    {"mode": "detail", "team": self._prepare_team_image(team)},
                )
        teams = await self.team.list_teams(event.unified_msg_origin)
        if self._view_as_text():
            return self._result(self._format_team_list(teams))
        template = await load_template("team.html")
        return self._image_result(template, {"mode": "list", "teams": teams})

    async def blacklist(
        self,
        event: AstrMessageEvent,
        team_id: int = 0,
    ) -> dict[str, Any]:
        """Ask an AstrBot LLM to select one member for the team blacklist."""
        permission_error = await self._permission_error(event)
        if permission_error:
            return self._result(permission_error, False)
        if team_id <= 0:
            return self._result("用法：团队黑本 团编号", False)

        team = await self.team.get_team(event.unified_msg_origin, team_id)
        if not team:
            return await self._team_list_result(event.unified_msg_origin)
        try:
            answer = await self.team_blacklist.recommend(event, team)
        except TeamBlacklistError as exc:
            return self._result(str(exc), False)
        return self._result(f"团队 #{team_id} 黑本建议：\n{answer}")

    async def update_member(
        self,
        event: AstrMessageEvent,
        team_id: int = 0,
        role_name: str = "",
        new_role_name: str = "",
        kungfu: str = "",
        boss_mark: str = "",
    ) -> dict[str, Any]:
        """Update an existing team member in the current session."""
        permission_error = await self._permission_error(event)
        if permission_error:
            return self._result(permission_error, False)
        if team_id <= 0 or not role_name or not new_role_name or not kungfu:
            return self._result(
                "用法：修改报名 团编号 原角色名 新角色名 心法 [老板]",
                False,
            )
        if boss_mark and boss_mark != "老板":
            return self._result("可选标记只能填写“老板”。", False)
        try:
            member = await self.team.update_member(
                event.unified_msg_origin,
                team_id,
                role_name,
                new_role_name,
                kungfu,
                boss_mark == "老板",
            )
        except TeamNotFoundError:
            return await self._team_list_result(event.unified_msg_origin)
        except ValueError as exc:
            return self._result(str(exc), False)
        boss = "，老板" if member["is_boss"] else ""
        return self._result(
            f"团队 #{team_id} 成员已修改：{member['role_name']}｜"
            f"{member['kungfu']}{boss}。"
        )

    async def swap_slots(
        self,
        event: AstrMessageEvent,
        team_id: int = 0,
        first_slot: int = 0,
        second_slot: int = 0,
    ) -> dict[str, Any]:
        """Swap two positions in a current-session team."""
        permission_error = await self._permission_error(event)
        if permission_error:
            return self._result(permission_error, False)
        if team_id <= 0 or first_slot <= 0 or second_slot <= 0:
            return self._result("用法：交换位置 团编号 位置1 位置2", False)
        try:
            await self.team.swap_slots(
                event.unified_msg_origin,
                team_id,
                first_slot,
                second_slot,
            )
        except TeamNotFoundError:
            return await self._team_list_result(event.unified_msg_origin)
        except ValueError as exc:
            return self._result(str(exc), False)
        return self._result(
            f"团队 #{team_id} 的位置 {first_slot} 与 {second_slot} 已交换。"
        )

    async def _rule_scope(
        self,
        event: AstrMessageEvent,
        scope: str,
    ) -> tuple[int, int]:
        normalized = str(scope or "").strip()
        if normalized.startswith("默认"):
            return int(normalized.removeprefix("默认")), 0
        team_number = normalized.removeprefix("团队")
        if team_number.isdigit():
            team_id = int(team_number)
            team = await self.team.get_team(event.unified_msg_origin, team_id)
            if not team:
                raise TeamNotFoundError("团队不存在")
            return int(team["capacity"]), team_id
        raise ValueError("规则范围格式应为“默认10”“默认25”或团编号")

    @staticmethod
    def _format_rules(config: dict[str, Any]) -> str:
        scope = (
            f"团队{config['team_id']}"
            if config["team_id"]
            else f"默认{config['capacity']}"
        )
        inherited = "（继承会话默认）" if config["inherited"] else ""
        lines = [f"{scope} 报名限制{inherited}："]
        if not config["rules"]:
            lines.append("暂无规则。")
            return "\n".join(lines)
        for rule in config["rules"]:
            rule_type = "职责" if rule["rule_type"] == "role" else "心法"
            target = {
                "HEALER": "奶",
                "BOSS": "老板",
            }.get(rule["target_value"], rule["target_value"])
            lines.append(
                f"#{rule['id']} {rule_type} {target}｜"
                f"最少 {rule['min_count']}｜最多 {rule['max_count']}"
            )
        return "\n".join(lines)

    async def view_rules(
        self,
        event: AstrMessageEvent,
        scope: str = "",
    ) -> dict[str, Any]:
        permission_error = await self._permission_error(event)
        if permission_error:
            return self._result(permission_error, False)
        if not scope:
            return self._result("用法：查看限制 默认10|默认25|团编号", False)
        try:
            capacity, team_id = await self._rule_scope(event, scope)
            config = await self.team_rules.get_config(
                event.unified_msg_origin,
                capacity,
                team_id,
            )
        except TeamNotFoundError:
            return await self._team_list_result(event.unified_msg_origin)
        except ValueError as exc:
            return self._result(str(exc), False)
        return self._result(self._format_rules(config))

    async def save_rule(
        self,
        event: AstrMessageEvent,
        scope: str = "",
        rule_type: str = "",
        target: str = "",
        min_count: int = -1,
        max_count: int = -1,
        rule_id: int = 0,
    ) -> dict[str, Any]:
        permission_error = await self._permission_error(event)
        if permission_error:
            return self._result(permission_error, False)
        if not scope or not rule_type or not target or min_count < 0 or max_count < 0:
            return self._result(
                "新增用法：添加限制 默认10|默认25|团编号 "
                "职责|心法 目标 最小数量 最大数量\n"
                "修改用法：修改限制 默认10|默认25|团编号 规则编号 "
                "职责|心法 目标 最小数量 最大数量",
                False,
            )
        normalized_type = {"职责": "role", "心法": "kungfu"}.get(rule_type)
        if not normalized_type:
            return self._result("限制类型只能填写“职责”或“心法”。", False)
        try:
            capacity, team_id = await self._rule_scope(event, scope)
            config = await self.team_rules.save_rule(
                event.unified_msg_origin,
                capacity,
                team_id,
                normalized_type,
                target,
                min_count,
                max_count,
                rule_id,
            )
        except TeamNotFoundError:
            return await self._team_list_result(event.unified_msg_origin)
        except ValueError as exc:
            return self._result(str(exc), False)
        return self._result(self._format_rules(config))

    async def delete_rule(
        self,
        event: AstrMessageEvent,
        scope: str = "",
        rule_id: int = 0,
    ) -> dict[str, Any]:
        permission_error = await self._permission_error(event)
        if permission_error:
            return self._result(permission_error, False)
        if not scope or rule_id <= 0:
            return self._result("用法：删除限制 默认10|默认25|团编号 规则编号", False)
        try:
            capacity, team_id = await self._rule_scope(event, scope)
            config = await self.team_rules.delete_rule(
                event.unified_msg_origin,
                capacity,
                team_id,
                rule_id,
            )
        except TeamNotFoundError:
            return await self._team_list_result(event.unified_msg_origin)
        except ValueError as exc:
            return self._result(str(exc), False)
        return self._result(self._format_rules(config))

    async def reset_rules(
        self,
        event: AstrMessageEvent,
        scope: str = "",
    ) -> dict[str, Any]:
        permission_error = await self._permission_error(event)
        if permission_error:
            return self._result(permission_error, False)
        if not scope:
            return self._result("用法：恢复默认限制 团编号", False)
        try:
            _, team_id = await self._rule_scope(event, scope)
            if not team_id:
                return self._result("用法：恢复默认限制 团编号", False)
            config = await self.team_rules.reset_team_rules(
                event.unified_msg_origin,
                team_id,
            )
        except TeamNotFoundError:
            return await self._team_list_result(event.unified_msg_origin)
        except ValueError as exc:
            return self._result(str(exc), False)
        return self._result(self._format_rules(config))
