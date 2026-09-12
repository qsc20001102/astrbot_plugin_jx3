from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING, Any

from astrbot.api.star import Context
from astrbot.api.web import error_response, json_response, request

from .event_push import EVENT_NAMES, FREE_EVENT_ACTIONS
from .team import TeamNotFoundError

if TYPE_CHECKING:
    from .bilei_data import BiLeidata
    from .cache import CacheService
    from .event_push import EventPushService
    from .jx3api_data import JX3APIService
    from .kungfu_alias import KungfuAliasService
    from .server_binding import ServerBindingService
    from .session_control import SessionControlService
    from .team import TeamService
    from .team_rules import TeamRuleService


class WebUIService:
    """注册插件管理页接口，并处理 WebUI 的数据读写。"""

    def __init__(
        self,
        jx3api: JX3APIService,
        event_push: EventPushService,
        server_binding: ServerBindingService,
        kungfu_alias: KungfuAliasService,
        session_control: SessionControlService,
        bilei: BiLeidata,
        cache: CacheService,
        team: TeamService,
        team_rules: TeamRuleService,
        team_kungfu_icons: dict[str, str],
    ):
        self.jx3api = jx3api
        self.event_push = event_push
        self.server_binding = server_binding
        self.kungfu_alias = kungfu_alias
        self.session_control = session_control
        self.bilei = bilei
        self.cache = cache
        self.team = team
        self.team_rules = team_rules
        self.team_kungfu_icons = team_kungfu_icons

    def register(self, context: Context, plugin_name: str):
        routes = (
            ("dashboard", self.dashboard, ["GET"], "读取会话管理数据"),
            (
                "subscriptions/save",
                self.save_subscription,
                ["POST"],
                "保存会话事件推送配置",
            ),
            (
                "subscriptions/delete",
                self.delete_subscription,
                ["POST"],
                "删除会话事件推送配置",
            ),
            ("bindings/save", self.save_binding, ["POST"], "保存会话区服绑定"),
            ("bindings/delete", self.delete_binding, ["POST"], "删除会话区服绑定"),
            ("aliases/save", self.save_aliases, ["POST"], "保存区服别名"),
            ("aliases/delete", self.delete_aliases, ["POST"], "删除区服别名"),
            ("aliases/restore", self.restore_aliases, ["POST"], "恢复默认区服别名"),
            ("kungfu/save", self.save_kungfu, ["POST"], "保存心法别名"),
            (
                "kungfu/role-type",
                self.save_kungfu_role_type,
                ["POST"],
                "保存心法职责分类",
            ),
            ("kungfu/restore", self.restore_kungfu, ["POST"], "恢复默认心法配置"),
            (
                "session-control/mode",
                self.save_session_control_mode,
                ["POST"],
                "保存会话控制模式",
            ),
            (
                "session-control/save",
                self.save_session_control_entry,
                ["POST"],
                "保存会话控制名单",
            ),
            (
                "session-control/delete",
                self.delete_session_control_entry,
                ["POST"],
                "删除会话控制名单",
            ),
            (
                "bilei/legacy/migrate",
                self.migrate_legacy_bilei,
                ["POST"],
                "迁移旧避雷记录到指定会话",
            ),
            ("cache/settings/save", self.save_cache_setting, ["POST"], "保存缓存时间"),
            ("cache/limits/save", self.save_cache_limits, ["POST"], "保存缓存容量限制"),
            ("cache/item/clear", self.clear_cache_item, ["POST"], "清理单项缓存"),
            ("cache/clear", self.clear_cache, ["POST"], "清理查询缓存"),
            ("teams/create", self.create_team, ["POST"], "创建团队"),
            (
                "teams/registration",
                self.set_team_registration,
                ["POST"],
                "设置团队报名状态",
            ),
            ("teams/delete", self.delete_team, ["POST"], "结束团队"),
            ("teams/delete-all", self.delete_all_teams, ["POST"], "结束会话全部团队"),
            ("teams/clear", self.clear_team_members, ["POST"], "清空团队报名"),
            ("teams/signup", self.signup_team, ["POST"], "添加团队报名"),
            ("teams/cancel", self.cancel_team_signup, ["POST"], "取消团队报名"),
            ("teams/member-update", self.update_team_member, ["POST"], "修改团队成员"),
            ("teams/swap", self.swap_team_slots, ["POST"], "交换团队位置"),
            (
                "team-rules/config",
                self.get_team_rule_config,
                ["POST"],
                "读取团队限制规则",
            ),
            ("team-rules/save", self.save_team_rule, ["POST"], "保存团队限制规则"),
            ("team-rules/delete", self.delete_team_rule, ["POST"], "删除团队限制规则"),
            (
                "team-rules/reset",
                self.reset_team_rules,
                ["POST"],
                "恢复团队默认限制规则",
            ),
        )
        for path, handler, methods, description in routes:
            context.register_web_api(
                f"/{plugin_name}/{path}",
                handler,
                methods,
                description,
            )

    @staticmethod
    async def _json_payload() -> dict[str, Any]:
        payload = await request.json(default={})
        if not isinstance(payload, dict):
            raise ValueError("请求正文必须是 JSON 对象")
        return payload

    @staticmethod
    def _parse_aliases(raw_aliases: Any) -> list[str]:
        if isinstance(raw_aliases, str):
            return re.split(r"[,，;；\n]+", raw_aliases)
        if isinstance(raw_aliases, list):
            return [str(value) for value in raw_aliases]
        raise ValueError("别名必须是字符串或数组")

    async def dashboard(self):
        (
            bindings,
            subscriptions,
            aliases,
            kungfu,
            session_control,
            legacy_bilei,
            token_stats,
            cache,
            teams,
            team_rule_sessions,
        ) = await asyncio.gather(
            self.server_binding.list_bindings(),
            self.event_push.list_subscription_statuses(),
            self.server_binding.list_aliases(),
            self.kungfu_alias.list_kungfu(),
            self.session_control.get_state(),
            self.bilei.list_legacy_records(),
            self.jx3api.token_stats(),
            self.cache.dashboard(),
            self.team.dashboard(),
            self.team_rules.list_sessions(),
        )
        return json_response(
            {
                "bindings": bindings,
                "subscriptions": subscriptions,
                "aliases": aliases,
                "kungfu": kungfu,
                "servers": [item["server"] for item in aliases],
                "events": {str(action): name for action, name in EVENT_NAMES.items()},
                "free_event_actions": sorted(FREE_EVENT_ACTIONS),
                "session_control": session_control,
                "legacy_bilei": legacy_bilei,
                "token_stats": token_stats,
                "cache": cache,
                "teams": teams,
                "team_kungfu_icons": {
                    kungfu: self.team_kungfu_icons[kungfu]
                    for kungfu in {
                        member["kungfu"]
                        for team in teams
                        for member in team["members"]
                    }
                    if kungfu in self.team_kungfu_icons
                },
                "team_rule_sessions": team_rule_sessions,
            }
        )

    async def save_subscription(self):
        try:
            payload = await self._json_payload()
            await self.event_push.save_subscription(
                payload.get("session_id"),
                payload.get("enabled"),
                payload.get("actions"),
                payload.get("mode"),
            )
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        return json_response({"saved": True})

    async def delete_subscription(self):
        try:
            payload = await self._json_payload()
            await self.event_push.delete_subscription(payload.get("session_id"))
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        return json_response({"deleted": True})

    async def save_binding(self):
        try:
            payload = await self._json_payload()
            server = self.server_binding.resolve_standard_server(payload.get("server"))
            if not server:
                raise ValueError("绑定区服必须选择标准区服")
            await self.server_binding.set_binding(
                str(payload.get("session_id") or ""),
                server,
            )
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        return json_response({"saved": True})

    async def delete_binding(self):
        try:
            payload = await self._json_payload()
            session_id = str(payload.get("session_id") or "")
            if not session_id.strip():
                raise ValueError("会话 ID 不能为空")
            await self.server_binding.delete_binding(session_id)
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        return json_response({"deleted": True})

    async def save_aliases(self):
        try:
            payload = await self._json_payload()
            await self.server_binding.set_aliases(
                str(payload.get("server") or ""),
                self._parse_aliases(payload.get("aliases", [])),
            )
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        return json_response({"saved": True})

    async def delete_aliases(self):
        try:
            payload = await self._json_payload()
            server = str(payload.get("server") or "")
            if not server.strip():
                raise ValueError("标准区服名不能为空")
            await self.server_binding.delete_aliases(server)
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        return json_response({"deleted": True})

    async def restore_aliases(self):
        try:
            restored = await self.server_binding.restore_default_aliases()
        except (RuntimeError, ValueError) as exc:
            return error_response(str(exc), status_code=500)
        return json_response({"restored": restored})

    async def save_kungfu(self):
        try:
            payload = await self._json_payload()
            async with self.team_rules.write_lock:
                await self.kungfu_alias.save_aliases(
                    payload.get("pzid"),
                    self._parse_aliases(payload.get("aliases", [])),
                )
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        return json_response({"saved": True})

    async def save_kungfu_role_type(self):
        try:
            payload = await self._json_payload()
            async with self.team_rules.write_lock:
                await self.kungfu_alias.save_role_type(
                    payload.get("pzid"),
                    payload.get("role_type"),
                )
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        return json_response({"saved": True})

    async def restore_kungfu(self):
        try:
            async with self.team_rules.write_lock:
                restored = await self.kungfu_alias.restore_defaults()
        except (RuntimeError, ValueError) as exc:
            return error_response(str(exc), status_code=500)
        return json_response({"restored": restored})

    async def save_session_control_mode(self):
        try:
            payload = await self._json_payload()
            await self.session_control.set_mode(payload.get("mode"))
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        return json_response({"saved": True})

    async def save_session_control_entry(self):
        try:
            payload = await self._json_payload()
            await self.session_control.save_entry(
                payload.get("session_id"),
                payload.get("list_type"),
                payload.get("remark"),
            )
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        return json_response({"saved": True})

    async def delete_session_control_entry(self):
        try:
            payload = await self._json_payload()
            await self.session_control.delete_entry(payload.get("session_id"))
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        return json_response({"deleted": True})

    async def migrate_legacy_bilei(self):
        try:
            payload = await self._json_payload()
            await self.bilei.migrate_legacy_record(
                payload.get("id"),
                payload.get("session_id"),
            )
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        return json_response({"migrated": True})

    async def save_cache_setting(self):
        try:
            payload = await self._json_payload()
            await self.cache.set_ttl(
                str(payload.get("cache_type") or ""),
                str(payload.get("cache_name") or ""),
                payload.get("ttl_seconds"),
                payload.get("inherit") is True,
            )
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        return json_response({"saved": True})

    async def save_cache_limits(self):
        try:
            payload = await self._json_payload()
            await self.cache.set_limits(
                payload.get("api_memory_max_mb"),
                payload.get("api_max_entries"),
                payload.get("image_max_mb"),
            )
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        return json_response({"saved": True})

    async def clear_cache_item(self):
        try:
            payload = await self._json_payload()
            removed = await self.cache.clear_item(
                str(payload.get("cache_type") or ""),
                str(payload.get("cache_name") or ""),
            )
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        return json_response({"cleared": True, "removed": removed})

    async def clear_cache(self):
        try:
            payload = await self._json_payload()
            removed = await self.cache.clear(str(payload.get("cache_type") or ""))
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        return json_response({"cleared": True, "removed": removed})

    async def _team_not_found(self, session_id: Any):
        """Return the requested session's team list for a missing team number.

        Args:
            session_id: AstrBot unified message origin from the request payload.

        Returns:
            JSON response containing a missing marker and basic team information.
        """
        teams = await self.team.list_teams(session_id)
        return json_response({"team_not_found": True, "teams": teams})

    async def create_team(self):
        """Create a team from the authenticated plugin management page."""
        try:
            payload = await self._json_payload()
            team = await self.team.create_team(
                payload.get("session_id"),
                payload.get("name"),
                payload.get("capacity"),
                payload.get("announcement"),
                "webui",
                "WebUI 管理员",
            )
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        return json_response({"created": True, "team": team})

    async def set_team_registration(self):
        """Open or close registration for one team from WebUI."""
        try:
            payload = await self._json_payload()
            registration_open = payload.get("registration_open")
            if not isinstance(registration_open, bool):
                raise ValueError("报名状态必须是布尔值")
            team = await self.team.set_registration(
                payload.get("session_id"),
                payload.get("team_id"),
                registration_open,
            )
            if not team:
                return await self._team_not_found(payload.get("session_id"))
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        return json_response({"saved": True, "team": team})

    async def delete_team(self):
        """Delete one team and all of its registrations from WebUI."""
        try:
            payload = await self._json_payload()
            deleted = await self.team.end_team(
                payload.get("session_id"),
                payload.get("team_id"),
            )
            if not deleted:
                return await self._team_not_found(payload.get("session_id"))
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        return json_response({"deleted": True})

    async def delete_all_teams(self):
        """Delete all teams in one explicitly selected WebUI session."""
        try:
            payload = await self._json_payload()
            count = await self.team.end_all(payload.get("session_id"))
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        return json_response({"deleted": True, "count": count})

    async def clear_team_members(self):
        """Clear all registrations for one team from WebUI."""
        try:
            payload = await self._json_payload()
            count = await self.team.clear_members(
                payload.get("session_id"),
                payload.get("team_id"),
            )
            if count is None:
                return await self._team_not_found(payload.get("session_id"))
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        return json_response({"cleared": True, "count": count})

    async def signup_team(self):
        """Add a role registration from WebUI."""
        try:
            payload = await self._json_payload()
            is_boss = payload.get("is_boss", False)
            if not isinstance(is_boss, bool):
                raise ValueError("老板标记必须是布尔值")
            member = await self.team.signup(
                payload.get("session_id"),
                payload.get("team_id"),
                self.kungfu_alias.resolve_kungfu(payload.get("kungfu")),
                payload.get("role_name"),
                is_boss,
                "webui",
                "WebUI 管理员",
            )
        except TeamNotFoundError:
            return await self._team_not_found(payload.get("session_id"))
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        return json_response({"created": True, "member": member})

    async def cancel_team_signup(self):
        """Remove a role registration from WebUI."""
        try:
            payload = await self._json_payload()
            removed = await self.team.cancel(
                payload.get("session_id"),
                payload.get("team_id"),
                payload.get("role_name"),
            )
        except TeamNotFoundError:
            return await self._team_not_found(payload.get("session_id"))
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        if not removed:
            return error_response("团队中没有该角色", status_code=400)
        return json_response({"deleted": removed})

    async def update_team_member(self):
        """Update a team's existing member from WebUI."""
        try:
            payload = await self._json_payload()
            is_boss = payload.get("is_boss")
            if not isinstance(is_boss, bool):
                raise ValueError("老板标记必须是布尔值")
            member = await self.team.update_member(
                payload.get("session_id"),
                payload.get("team_id"),
                payload.get("role_name"),
                payload.get("new_role_name"),
                payload.get("kungfu"),
                is_boss,
            )
        except TeamNotFoundError:
            return await self._team_not_found(payload.get("session_id"))
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        return json_response({"saved": True, "member": member})

    async def swap_team_slots(self):
        """Swap two team positions after a WebUI drag operation."""
        try:
            payload = await self._json_payload()
            team = await self.team.swap_slots(
                payload.get("session_id"),
                payload.get("team_id"),
                payload.get("first_slot"),
                payload.get("second_slot"),
            )
        except TeamNotFoundError:
            return await self._team_not_found(payload.get("session_id"))
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        return json_response({"saved": True, "team": team})

    async def get_team_rule_config(self):
        """Return one session default or team-specific restriction profile."""
        try:
            payload = await self._json_payload()
            config = await self.team_rules.get_config(
                payload.get("session_id"),
                payload.get("capacity", 25),
                payload.get("team_id", 0),
            )
        except TeamNotFoundError:
            return await self._team_not_found(payload.get("session_id"))
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        return json_response({"config": config})

    async def save_team_rule(self):
        """Add or update a restriction in one selected profile."""
        try:
            payload = await self._json_payload()
            config = await self.team_rules.save_rule(
                payload.get("session_id"),
                payload.get("capacity", 25),
                payload.get("team_id", 0),
                payload.get("rule_type"),
                payload.get("target_value"),
                payload.get("min_count"),
                payload.get("max_count"),
                payload.get("rule_id", 0),
            )
        except TeamNotFoundError:
            return await self._team_not_found(payload.get("session_id"))
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        return json_response({"saved": True, "config": config})

    async def delete_team_rule(self):
        """Delete one restriction from one selected profile."""
        try:
            payload = await self._json_payload()
            config = await self.team_rules.delete_rule(
                payload.get("session_id"),
                payload.get("capacity", 25),
                payload.get("team_id", 0),
                payload.get("rule_id"),
            )
        except TeamNotFoundError:
            return await self._team_not_found(payload.get("session_id"))
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        return json_response({"deleted": True, "config": config})

    async def reset_team_rules(self):
        """Delete a team profile so it inherits its session default again."""
        try:
            payload = await self._json_payload()
            config = await self.team_rules.reset_team_rules(
                payload.get("session_id"),
                payload.get("team_id"),
            )
        except TeamNotFoundError:
            return await self._team_not_found(payload.get("session_id"))
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        return json_response({"reset": True, "config": config})
