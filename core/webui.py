from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING, Any

from astrbot.api.star import Context
from astrbot.api.web import error_response, json_response, request

from .event_push import EVENT_NAMES

if TYPE_CHECKING:
    from .event_push import EventPushService
    from .jx3api_data import JX3APIService
    from .kungfu_alias import KungfuAliasService
    from .server_binding import ServerBindingService
    from .session_control import SessionControlService


class WebUIService:
    """注册插件管理页接口，并处理 WebUI 的数据读写。"""

    def __init__(
        self,
        jx3api: JX3APIService,
        event_push: EventPushService,
        server_binding: ServerBindingService,
        kungfu_alias: KungfuAliasService,
        session_control: SessionControlService,
    ):
        self.jx3api = jx3api
        self.event_push = event_push
        self.server_binding = server_binding
        self.kungfu_alias = kungfu_alias
        self.session_control = session_control

    def register(self, context: Context, plugin_name: str):
        routes = (
            ("dashboard", self.dashboard, ["GET"], "读取会话管理数据"),
            ("bindings/save", self.save_binding, ["POST"], "保存会话区服绑定"),
            ("bindings/delete", self.delete_binding, ["POST"], "删除会话区服绑定"),
            ("aliases/save", self.save_aliases, ["POST"], "保存区服别名"),
            ("aliases/delete", self.delete_aliases, ["POST"], "删除区服别名"),
            ("aliases/restore", self.restore_aliases, ["POST"], "恢复默认区服别名"),
            ("kungfu/save", self.save_kungfu, ["POST"], "保存心法别名"),
            ("kungfu/restore", self.restore_kungfu, ["POST"], "恢复默认心法别名"),
            ("servers/refresh", self.refresh_servers, ["POST"], "刷新区服目录"),
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
            token_stats,
        ) = await asyncio.gather(
            self.server_binding.list_bindings(),
            self.event_push.list_subscription_statuses(),
            self.server_binding.list_aliases(),
            self.kungfu_alias.list_kungfu(),
            self.session_control.get_state(),
            self.jx3api.token_stats(),
        )
        return json_response(
            {
                "bindings": bindings,
                "subscriptions": subscriptions,
                "aliases": aliases,
                "kungfu": kungfu,
                "servers": self.server_binding.standard_servers(),
                "events": {
                    str(action): name for action, name in EVENT_NAMES.items()
                },
                "session_control": session_control,
                "token_stats": token_stats,
            }
        )

    async def save_binding(self):
        try:
            payload = await self._json_payload()
            server = self.server_binding.resolve_standard_server(
                payload.get("server")
            )
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
            await self.kungfu_alias.save_aliases(
                payload.get("pzid"),
                self._parse_aliases(payload.get("aliases", [])),
            )
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        return json_response({"saved": True})

    async def restore_kungfu(self):
        try:
            restored = await self.kungfu_alias.restore_defaults()
        except (RuntimeError, ValueError) as exc:
            return error_response(str(exc), status_code=500)
        return json_response({"restored": restored})

    async def refresh_servers(self):
        servers = await self.jx3api.server_list()
        if not servers:
            return error_response("区服目录刷新失败", status_code=502)
        await self.server_binding.update_server_catalog(servers)
        return json_response({"servers": self.server_binding.standard_servers()})

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
