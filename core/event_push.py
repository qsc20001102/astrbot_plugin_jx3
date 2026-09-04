# pyright: reportOptionalMemberAccess=false
import asyncio
import contextlib
import json
from datetime import datetime
from typing import Any, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import aiohttp
from aiohttp import ClientSession, ClientTimeout, WSMsgType

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import MessageChain
from astrbot.api.star import Context

from .sqlite import AsyncSQLiteDB
from .server_binding import ServerBindingService


DEFAULT_WSS_URL = "wss://socket.nicemoe.cn"
FREE_EVENT_ACTIONS = frozenset({2001, 2002, 2003, 2004, 2005, 2006})
EVENT_NAMES = {
    1001: "奇遇触发",
    1002: "马驹刷新",
    1003: "马驹捕获",
    1004: "扶摇预告",
    1005: "扶摇开启",
    1006: "扶摇点名",
    1007: "烟花报时",
    1008: "的卢预告",
    1009: "的卢刷新",
    1010: "的卢捕获",
    1011: "的卢拍卖",
    1012: "玄晶报时",
    1013: "阵营拍卖",
    1014: "诛恶事件",
    1015: "追魂点名",
    1016: "阵营祭天预告",
    1017: "阵营祭天终点",
    1101: "领地宣战·开始",
    1102: "领地宣战·结束",
    1108: "帮会野外宣战·开始",
    1109: "帮会野外宣战·结束",
    1111: "抢占粮仓",
    1112: "大旗重置",
    1113: "大旗被夺",
    1114: "据点占领",
    1115: "据点占领（无帮会）",
    1116: "小攻防贡献（非开战）",
    1117: "小攻防贡献",
    1118: "大攻防贡献",
    1119: "战利品竞拍",
    1120: "小攻防分红",
    1121: "大攻防分红",
    1122: "大攻防分红（含指挥）",
    2001: "开服状态",
    2002: "官方新闻",
    2003: "版本更新",
    2004: "八卦速报",
    2005: "关隘首领",
    2006: "云丛预告",
}
EVENT_ACTIONS = tuple(EVENT_NAMES)

SERVER_FIELDS = (
    ("大区", "zone", "text"),
    ("服务器", "server", "text"),
)
EVENT_FIELDS = {
    1001: SERVER_FIELDS + (
        ("角色", "name", "text"),
        ("奇遇", "event", "text"),
        ("等级", "level", "text"),
        ("时间", "time", "time"),
    ),
    1002: SERVER_FIELDS + (
        ("地图", "map_name", "text"),
        ("刷新时间", "time", "time"),
    ),
    1003: SERVER_FIELDS + (
        ("名称", "name", "text"),
        ("地图", "map_name", "text"),
        ("马驹", "horse", "text"),
        ("等级", "level", "text"),
        ("捕获时间", "time", "time"),
    ),
    1004: SERVER_FIELDS + (("预告时间", "time", "time"),),
    1005: SERVER_FIELDS + (("开启时间", "time", "time"),),
    1006: SERVER_FIELDS + (
        ("点名角色", "name", "list"),
        ("时间", "time", "time"),
    ),
    1007: SERVER_FIELDS + (
        ("燃放者", "sender", "text"),
        ("接收者", "receiver", "text"),
        ("烟花", "firework", "text"),
        ("地图", "map_name", "text"),
        ("时间", "time", "time"),
    ),
    1008: SERVER_FIELDS + (
        ("马驹", "name", "text"),
        ("地图", "map_name", "text"),
        ("预告时间", "time", "time"),
    ),
    1009: SERVER_FIELDS + (
        ("马驹", "name", "text"),
        ("地图", "map_name", "text"),
        ("刷新时间", "refresh_time", "time"),
    ),
    1010: SERVER_FIELDS + (
        ("马驹", "name", "text"),
        ("地图", "map_name", "text"),
        ("捕获角色", "capture_role_name", "text"),
        ("角色阵营", "capture_camp_name", "text"),
        ("捕获时间", "capture_time", "time"),
    ),
    1011: SERVER_FIELDS + (
        ("马驹", "name", "text"),
        ("竞拍角色", "auction_role_name", "text"),
        ("角色阵营", "auction_camp_name", "text"),
        ("成交金额", "auction_amount", "text"),
        ("拍卖时间", "auction_time", "time"),
    ),
    1012: SERVER_FIELDS + (
        ("角色", "role_name", "text"),
        ("副本", "map_name", "text"),
        ("物品", "item_name", "text"),
        ("时间", "time", "time"),
    ),
    1013: SERVER_FIELDS + (
        ("竞拍角色", "role_name", "text"),
        ("阵营", "camp_name", "text"),
        ("物品", "item_name", "text"),
        ("成交金额", "item_amount", "text"),
        ("时间", "time", "time"),
    ),
    1014: SERVER_FIELDS + (
        ("地图", "map_name", "text"),
        ("时间", "time", "time"),
    ),
    1015: SERVER_FIELDS + (
        ("角色所在服", "role_server", "text"),
        ("点名角色", "role_name", "text"),
        ("时间", "time", "time"),
    ),
    1016: SERVER_FIELDS + (("预告时间", "time", "time"),),
    1017: SERVER_FIELDS + (
        ("阵营", "camp_name", "text"),
        ("帮会", "tong_name", "text"),
        ("角色", "role_name", "text"),
        ("据点", "castle_name", "text"),
        ("时间", "time", "time"),
    ),
    1101: SERVER_FIELDS + (
        ("战场类型", "battlefield_type", "text"),
        ("宣战帮会", "declaring_tong_name", "text"),
        ("应战帮会", "accepting_tong_name", "text"),
        ("领地帮会", "battlefield_tong_name", "text"),
        ("开始时间", "start_time", "time"),
    ),
    1102: SERVER_FIELDS + (
        ("战场类型", "battlefield_type", "text"),
        ("宣战帮会", "declaring_tong_name", "text"),
        ("应战帮会", "accepting_tong_name", "text"),
        ("领地帮会", "battlefield_tong_name", "text"),
        ("获胜帮会", "victory_tong_name", "text"),
        ("获胜积分", "victory_score", "text"),
        ("结束时间", "end_time", "time"),
    ),
    1108: SERVER_FIELDS + (
        ("战场类型", "battlefield_type", "text"),
        ("宣战帮会", "declaring_tong_name", "text"),
        ("应战帮会", "accepting_tong_name", "text"),
        ("持续时长（小时）", "duration_hours", "text"),
        ("开始时间", "start_time", "time"),
    ),
    1109: SERVER_FIELDS + (
        ("战场类型", "battlefield_type", "text"),
        ("宣战帮会", "declaring_tong_name", "text"),
        ("应战帮会", "accepting_tong_name", "text"),
        ("结束时间", "end_time", "time"),
    ),
    1111: SERVER_FIELDS + (
        ("据点", "castle_name", "text"),
        ("阵营", "camp_name", "text"),
        ("时间", "time", "time"),
    ),
    1112: SERVER_FIELDS + (
        ("据点", "castle_name", "text"),
        ("时间", "time", "time"),
    ),
    1113: SERVER_FIELDS + (
        ("阵营", "camp_name", "text"),
        ("地图", "map_name", "text"),
        ("据点", "castle_name", "text"),
        ("时间", "time", "time"),
    ),
    1114: SERVER_FIELDS + (
        ("阵营", "camp_name", "text"),
        ("帮会", "tong_name", "text"),
        ("据点", "castle_name", "text"),
        ("时间", "time", "time"),
    ),
    1115: SERVER_FIELDS + (
        ("阵营", "camp_name", "text"),
        ("据点", "castle_name", "text"),
        ("时间", "time", "time"),
    ),
    1116: SERVER_FIELDS + (
        ("阵营", "camp_name", "text"),
        ("贡献帮会", "tong_name", "list"),
        ("时间", "time", "time"),
    ),
    1117: SERVER_FIELDS + (
        ("阵营", "camp_name", "text"),
        ("贡献帮会", "tong_name", "list"),
        ("时间", "time", "time"),
    ),
    1118: SERVER_FIELDS + (
        ("阵营", "camp_name", "text"),
        ("贡献帮会", "tong_name", "list"),
        ("时间", "time", "time"),
    ),
    1119: SERVER_FIELDS + (
        ("阵营", "camp_name", "text"),
        ("竞拍角色", "role_name", "text"),
        ("物品", "item_name", "text"),
        ("成交金额", "item_amount", "text"),
        ("时间", "time", "time"),
    ),
    1120: SERVER_FIELDS + (
        ("阵营", "camp_name", "text"),
        ("分红帮会", "tong_name", "list"),
        ("分红金额", "split_amount", "text"),
        ("时间", "time", "time"),
    ),
    1121: SERVER_FIELDS + (
        ("阵营", "camp_name", "text"),
        ("分红帮会", "tong_name", "list"),
        ("分红金额", "split_amount", "text"),
        ("时间", "time", "time"),
    ),
    1122: SERVER_FIELDS + (
        ("阵营", "camp_name", "text"),
        ("指挥帮会", "chief_tong_name", "text"),
        ("分红帮会", "tong_name", "list"),
        ("分红金额", "split_amount", "text"),
        ("时间", "time", "time"),
    ),
    2001: SERVER_FIELDS + (
        ("状态", "status", "status"),
        ("时间", "time", "time"),
    ),
    2002: (
        ("类型", "type", "text"),
        ("标题", "title", "text"),
        ("日期", "date", "text"),
        ("链接", "url", "text"),
    ),
    2003: (
        ("当前版本", "now_version", "text"),
        ("最新版本", "new_version", "text"),
        ("更新包数量", "package_num", "text"),
        ("更新大小", "package_size", "text"),
    ),
    2004: (
        ("分类", "tags", "text"),
        ("服务器", "server", "text"),
        ("发布者", "name", "text"),
        ("标题", "title", "text"),
        ("日期", "date", "text"),
        ("链接", "url", "text"),
    ),
    2005: (
        ("服务器", "server", "text"),
        ("关卡", "stage", "text"),
        ("开始时间", "start", "time"),
    ),
    2006: (
        ("事件", "name", "text"),
        ("地点", "site", "text"),
        ("说明", "desc", "text"),
        ("时间", "time", "time"),
    ),
}


class EventPushService:
    """JX3API WebSocket 事件接收、会话订阅与消息分发。"""

    def __init__(
        self,
        context: Context,
        config: AstrBotConfig,
        sqlite: AsyncSQLiteDB,
        server_binding: ServerBindingService,
    ):
        self.context = context
        self.config = config
        self.sql = sqlite
        self.server_binding = server_binding
        self.url = str(config.get("jx3api_wss", "") or DEFAULT_WSS_URL).strip()
        self.token = str(config.get("jx3api_wss_token", "") or "").strip()
        self._runner: Optional[asyncio.Task] = None
        self._session: Optional[ClientSession] = None
        self._websocket: Optional[aiohttp.ClientWebSocketResponse] = None
        self._stopping = asyncio.Event()

    async def initialize(self):
        await self._init_subscription_table()
        if self._runner and not self._runner.done():
            return
        self._stopping.clear()
        self._runner = asyncio.create_task(
            self._connection_loop(),
            name="jx3api-event-push",
        )

    async def _init_subscription_table(self):
        columns = ",\n".join(
            f"action_{action} INTEGER NOT NULL DEFAULT 0"
            for action in EVENT_ACTIONS
        )
        await self.sql.execute(
            f"""
            CREATE TABLE IF NOT EXISTS event_push_subscriptions (
                session_id TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 0,
                {columns},
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # 以后增加事件编号时，旧数据库也能自动补齐新列。
        table_info = await self.sql.fetch_all(
            "PRAGMA table_info(event_push_subscriptions)"
        )
        existing_columns = {row["name"] for row in table_info}
        for action in EVENT_ACTIONS:
            column = self._action_column(action)
            if column not in existing_columns:
                await self.sql.execute(
                    f"ALTER TABLE event_push_subscriptions "
                    f"ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0"
                )

        # 旧轮询推送状态不再使用，按迁移要求清理。
        await self.sql.execute("DROP TABLE IF EXISTS tuishong")

    async def stop(self):
        self._stopping.set()
        if self._websocket and not self._websocket.closed:
            await self._websocket.close(code=1000, message=b"plugin stop")
        if self._runner and not self._runner.done():
            self._runner.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._runner
        self._runner = None
        self._websocket = None
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

    async def _connection_loop(self):
        retry_count = 0
        timeout = ClientTimeout(total=None, sock_connect=15)
        self._session = ClientSession(timeout=timeout)

        try:
            while not self._stopping.is_set():
                heartbeat_task = None
                try:
                    connection_url = self._connection_url()
                    async with self._session.ws_connect(
                        connection_url,
                        heartbeat=45,
                        autoping=True,
                    ) as websocket:
                        self._websocket = websocket
                        retry_count = 0
                        logger.info("JX3API 事件通道连接成功")
                        heartbeat_task = asyncio.create_task(
                            self._heartbeat_loop(websocket),
                            name="jx3api-event-heartbeat",
                        )

                        async for message in websocket:
                            if message.type == WSMsgType.TEXT:
                                await self._handle_message(message.data)
                            elif message.type in {
                                WSMsgType.CLOSE,
                                WSMsgType.CLOSED,
                                WSMsgType.ERROR,
                            }:
                                break
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    if not self._stopping.is_set():
                        error_text = str(exc)
                        if self.token:
                            error_text = error_text.replace(self.token, "***")
                        logger.warning(
                            f"JX3API 事件通道连接异常："
                            f"{type(exc).__name__}: {error_text}"
                        )
                finally:
                    self._websocket = None
                    if heartbeat_task:
                        heartbeat_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await heartbeat_task

                if self._stopping.is_set():
                    break

                delay = min(2 ** retry_count, 30)
                retry_count += 1
                logger.info(f"JX3API 事件通道将在 {delay} 秒后重连")
                try:
                    await asyncio.wait_for(self._stopping.wait(), timeout=delay)
                except asyncio.TimeoutError:
                    pass
        finally:
            if self._session and not self._session.closed:
                await self._session.close()
            self._session = None

    def _connection_url(self) -> str:
        if not self.token:
            return self.url

        parts = urlsplit(self.url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        # JX3API 官方 SDK 当前使用的事件令牌参数名即为 toekn。
        query["toekn"] = self.token
        return urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
        )

    async def _heartbeat_loop(self, websocket: aiohttp.ClientWebSocketResponse):
        while not self._stopping.is_set() and not websocket.closed:
            await asyncio.sleep(30)
            if not websocket.closed:
                await websocket.send_json({"action": -1})

    async def _handle_message(self, payload: str):
        try:
            message = json.loads(payload)
        except (TypeError, json.JSONDecodeError):
            logger.debug("忽略 JX3API 事件通道的非 JSON 消息")
            return

        if not isinstance(message, dict):
            return

        try:
            action = int(message.get("action"))
        except (TypeError, ValueError):
            return

        if action not in EVENT_NAMES:
            logger.debug(f"忽略未知 JX3API 事件：{action}")
            return

        status = str(message.get("status", "success")).lower()
        if status != "success":
            logger.warning(f"JX3API 事件状态异常：action={action}, status={status}")
            return

        detail = message.get("detail")
        if detail is None:
            detail = message.get("data")
        if not isinstance(detail, dict):
            logger.warning(f"JX3API 事件正文结构异常：action={action}")
            return

        recipients = await self._enabled_sessions(action)
        if "server" in detail:
            event_server = self.server_binding.resolve_server(detail.get("server"))
            recipients = [
                session_id
                for session_id, bound_server in recipients
                if not bound_server
                or self.server_binding.resolve_server(bound_server) == event_server
            ]
        else:
            recipients = [session_id for session_id, _ in recipients]
        if not recipients:
            return

        text = self._format_event(action, detail)
        results = await asyncio.gather(
            *(self._send_message(session_id, text) for session_id in recipients),
            return_exceptions=True,
        )
        for session_id, result in zip(recipients, results):
            if isinstance(result, Exception):
                logger.error(
                    f"JX3API 事件推送失败：action={action}, "
                    f"session={session_id}, error={result}"
                )

    async def _send_message(self, session_id: str, text: str):
        message_chain = MessageChain().message(text)
        await self.context.send_message(session_id, message_chain)

    async def _enabled_sessions(self, action: int) -> list[tuple[str, str]]:
        column = self._action_column(action)
        rows = await self.sql.fetch_all(
            f"SELECT subscriptions.session_id, "
            f"COALESCE(bindings.server, '') AS server "
            f"FROM event_push_subscriptions AS subscriptions "
            f"LEFT JOIN session_server_bindings AS bindings "
            f"ON bindings.session_id=subscriptions.session_id "
            f"WHERE subscriptions.enabled=1 "
            f"AND subscriptions.{column}=1"
        )
        return [
            (str(row["session_id"]), str(row.get("server") or "").strip())
            for row in rows
        ]

    async def list_subscription_statuses(self) -> list[dict[str, Any]]:
        rows = await self.sql.fetch_all(
            "SELECT * FROM event_push_subscriptions ORDER BY session_id"
        )
        return [
            {
                "session_id": str(row["session_id"]),
                "enabled": row.get("enabled") == 1,
                "actions": [
                    action
                    for action in EVENT_ACTIONS
                    if row.get(self._action_column(action)) == 1
                ],
            }
            for row in rows
        ]

    async def configure(
        self,
        session_id: str,
        first: str = "",
        second: str = "",
    ) -> str:
        first = first.strip().lower()
        second = second.strip().lower()
        await self._ensure_session(session_id)

        if first in {"列表", "list"}:
            return self._event_list_text()
        if not first or first in {"状态", "查看", "status"}:
            return await self._subscription_status(session_id)

        enable_words = {"开启", "启用", "开", "on"}
        disable_words = {"关闭", "禁用", "关", "off"}

        if not second and first in enable_words | disable_words:
            enabled = first in enable_words
            await self.sql.update(
                "event_push_subscriptions",
                {"enabled": int(enabled), "updated_at": self._now_text()},
                "session_id=?",
                (session_id,),
            )
            state = "已开启" if enabled else "已关闭"
            return f"当前会话的事件推送总开关{state}。"

        action_text = first
        switch_text = second
        if first in enable_words | disable_words and second.isdigit():
            action_text, switch_text = second, first

        try:
            action = int(action_text)
        except ValueError:
            return self._usage_text()

        if action not in EVENT_NAMES:
            return f"不支持事件 {action}。\n" + self._usage_text()
        if switch_text not in enable_words | disable_words:
            return self._usage_text()

        enabled = switch_text in enable_words
        column = self._action_column(action)
        await self.sql.update(
            "event_push_subscriptions",
            {column: int(enabled), "updated_at": self._now_text()},
            "session_id=?",
            (session_id,),
        )
        state = "已订阅" if enabled else "已取消订阅"
        result = f"{state}事件 {action}（{EVENT_NAMES[action]}）。"
        if enabled and action not in FREE_EVENT_ACTIONS and not self.token:
            result += "\n该事件需要事件版令牌，当前配置未填写令牌。"
        return result

    async def _ensure_session(self, session_id: str):
        await self.sql.execute(
            "INSERT OR IGNORE INTO event_push_subscriptions (session_id) VALUES (?)",
            (session_id,),
        )

    async def _subscription_status(self, session_id: str) -> str:
        row = await self.sql.select_one(
            "event_push_subscriptions",
            "session_id=?",
            (session_id,),
        )
        if not row:
            return self._usage_text()

        subscriptions = [
            f"{action} {EVENT_NAMES[action]}"
            for action in EVENT_ACTIONS
            if row.get(self._action_column(action)) == 1
        ]
        switch = "开启" if row.get("enabled") == 1 else "关闭"
        selected = "、".join(subscriptions) if subscriptions else "无"
        return (
            f"事件推送总开关：{switch}\n"
            f"已订阅事件：{selected}\n\n"
            f"{self._usage_text()}"
        )

    @staticmethod
    def _action_column(action: int) -> str:
        if action not in EVENT_NAMES:
            raise ValueError(f"不支持事件：{action}")
        return f"action_{action}"

    @staticmethod
    def _now_text() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _format_timestamp(value: Any) -> str:
        try:
            timestamp = float(value)
            if timestamp > 10_000_000_000:
                timestamp /= 1000
            return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
        except (TypeError, ValueError, OSError, OverflowError):
            return str(value or "未知")

    def _format_event(self, action: int, detail: dict[str, Any]) -> str:
        fields = EVENT_FIELDS.get(action)
        if not fields:
            detail_text = json.dumps(detail, ensure_ascii=False, indent=2)
            return f"【事件推送 · {action}】\n{detail_text}"

        lines = [f"【{EVENT_NAMES[action]}】"]
        for label, key, value_type in fields:
            lines.append(f"{label}：{self._format_field(detail.get(key), value_type)}")
        return "\n".join(lines)

    def _format_field(self, value: Any, value_type: str) -> str:
        if value_type == "time":
            return self._format_timestamp(value)
        if value_type == "status":
            if value in (0, "0"):
                return "维护"
            if value in (1, "1"):
                return "开服"
            return str(value if value is not None and value != "" else "未知")
        if value_type == "list":
            if isinstance(value, (list, tuple)):
                values = [str(item).strip() for item in value if str(item).strip()]
                return "、".join(values) if values else "无"
        return str(value if value is not None and value != "" else "未知")

    @staticmethod
    def _usage_text() -> str:
        return (
            "用法：\n"
            "事件推送 开启/关闭\n"
            "事件推送 事件编号 开启/关闭\n"
            "事件推送 状态\n"
            "事件推送 列表"
        )

    @staticmethod
    def _event_list_text() -> str:
        free = "\n".join(
            f"{action}：{EVENT_NAMES[action]}"
            for action in sorted(FREE_EVENT_ACTIONS)
        )
        paid = "\n".join(
            f"{action}：{EVENT_NAMES[action]}"
            for action in EVENT_ACTIONS
            if action not in FREE_EVENT_ACTIONS
        )
        return f"免费事件：\n{free}\n\n令牌事件：\n{paid}"
