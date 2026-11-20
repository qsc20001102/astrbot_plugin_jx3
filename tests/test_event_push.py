import types
import unittest
from unittest.mock import Mock, patch

from core.sqlite import AsyncSQLiteDB

with patch.dict(
    "sys.modules",
    {
        "astrbot": types.ModuleType("astrbot"),
        "astrbot.api": types.SimpleNamespace(AstrBotConfig=dict, logger=Mock()),
        "astrbot.api.event": types.SimpleNamespace(MessageChain=Mock()),
        "astrbot.api.star": types.SimpleNamespace(Context=Mock),
    },
):
    from core.event_push import (
        EVENT_ACTIONS,
        EVENT_FIELDS,
        EVENT_NAMES,
        FREE_EVENT_ACTIONS,
        EventPushService,
    )


# JX3API 事件版文档（/doc/json/openapi.socket.json，2026-11-15 更新）中的
# action -> detail 字段集合，用于防止本地目录与官方再次漂移。
OFFICIAL_FIELDS = {
    1001: ("event", "name", "server", "time", "zone"),
    1002: ("map_name", "server", "time", "zone"),
    1003: ("horse", "level", "map_name", "name", "server", "time", "zone"),
    1004: ("server", "time", "zone"),
    1005: ("server", "time", "zone"),
    1006: ("name", "server", "time", "zone"),
    1008: ("map_name", "name", "server", "time", "zone"),
    1009: ("map_name", "refresh_time", "server", "zone"),
    1010: (
        "capture_camp_name",
        "capture_role_name",
        "capture_time",
        "map_name",
        "refresh_time",
        "server",
        "zone",
    ),
    1011: (
        "auction_amount",
        "auction_camp_name",
        "auction_role_name",
        "auction_time",
        "refresh_time",
        "server",
        "zone",
    ),
    1012: (
        "item_amount",
        "item_name",
        "map_name",
        "role_name",
        "server",
        "time",
        "zone",
    ),
    1013: (
        "camp_name",
        "item_amount",
        "item_name",
        "role_name",
        "server",
        "time",
        "zone",
    ),
    1014: ("map_name", "server", "tier", "time", "zone"),
    1015: ("role_name", "role_server", "server", "time", "zone"),
    1017: (
        "camp_name",
        "castle_name",
        "role_name",
        "server",
        "time",
        "tong_name",
        "zone",
    ),
    1019: ("map_name", "name", "server", "time", "zone"),
    1101: (
        "accepting_tong_name",
        "battlefield_tong_name",
        "battlefield_type",
        "declaring_tong_name",
        "server",
        "start_time",
        "zone",
    ),
    1102: (
        "accepting_tong_name",
        "battlefield_tong_name",
        "battlefield_type",
        "declaring_tong_name",
        "end_time",
        "server",
        "victory_score",
        "victory_tong_name",
        "zone",
    ),
    1103: (
        "accepting_tong_name",
        "battlefield_type",
        "declaring_tong_name",
        "duration_hours",
        "server",
        "start_time",
        "zone",
    ),
    1104: (
        "accepting_tong_name",
        "battlefield_type",
        "declaring_tong_name",
        "end_time",
        "server",
        "zone",
    ),
    1105: (
        "challenge_tong_name",
        "opponent_tong_name",
        "server",
        "time",
        "victory_tong_name",
        "zone",
    ),
    1111: ("camp_name", "castle_name", "server", "time", "zone"),
    1112: ("castle_name", "server", "time", "zone"),
    1113: ("camp_name", "castle_name", "map_name", "server", "time", "zone"),
    1114: ("camp_name", "castle_name", "server", "time", "tong_name", "zone"),
    1115: ("camp_name", "castle_name", "server", "time", "zone"),
    1116: ("camp_name", "server", "time", "tong_name", "zone"),
    1117: ("camp_name", "server", "time", "tong_name", "zone"),
    1118: ("camp_name", "server", "time", "tong_name", "zone"),
    1119: (
        "camp_name",
        "item_amount",
        "item_name",
        "role_name",
        "server",
        "time",
        "zone",
    ),
    1120: ("camp_name", "server", "split_amount", "time", "tong_name", "zone"),
    1121: ("camp_name", "server", "split_amount", "time", "tong_name", "zone"),
    1122: (
        "camp_name",
        "chief_tong_name",
        "server",
        "split_amount",
        "time",
        "tong_names",
        "zone",
    ),
    1201: ("article_id", "article_text", "created_at", "url", "user_id", "user_name"),
    2001: ("server", "status", "time", "zone"),
    2002: ("date", "title", "type", "url"),
    2003: ("new_version", "now_version", "package_num", "package_size"),
    2004: ("date", "server", "tags", "tieba", "title", "url", "zone"),
    2007: (
        "depth",
        "intensity",
        "latitude",
        "location",
        "longitude",
        "magnitude",
        "time",
    ),
}

# refresh_time 是“捕获/拍卖时间减 86400 秒”的查询下界，不属于可读的推送字段。
HIDDEN_OFFICIAL_FIELDS = {1010: {"refresh_time"}, 1011: {"refresh_time"}}
REMOVED_ACTIONS = {1007, 1016, 1108, 1109, 2005, 2006}


class EventCatalogTest(unittest.TestCase):
    def test_catalog_matches_official_document(self):
        self.assertEqual(set(EVENT_NAMES), set(OFFICIAL_FIELDS))
        self.assertEqual(set(EVENT_ACTIONS), set(OFFICIAL_FIELDS))
        for action, fields in OFFICIAL_FIELDS.items():
            output_keys = {key for _, key, _ in EVENT_FIELDS[action]}
            self.assertLessEqual(
                output_keys,
                set(fields),
                msg=f"{action} 输出了官方文档之外的字段：{output_keys - set(fields)}",
            )
            missing = (
                set(fields) - output_keys - HIDDEN_OFFICIAL_FIELDS.get(action, set())
            )
            self.assertFalse(missing, msg=f"{action} 缺少官方字段：{missing}")

    def test_removed_actions_are_gone(self):
        self.assertTrue(REMOVED_ACTIONS.isdisjoint(EVENT_NAMES))
        self.assertTrue(REMOVED_ACTIONS.isdisjoint(EVENT_FIELDS))

    def test_replaced_actions_use_new_numbers(self):
        self.assertIn(1103, EVENT_NAMES)
        self.assertIn(1104, EVENT_NAMES)
        self.assertTrue({1108, 1109}.isdisjoint(EVENT_NAMES))

    def test_free_events_follow_level_zero_actions(self):
        self.assertEqual(FREE_EVENT_ACTIONS, frozenset({2001, 2002, 2003, 2004, 2007}))
        self.assertLessEqual(FREE_EVENT_ACTIONS, set(EVENT_NAMES))


class EventFormattingTest(unittest.TestCase):
    def setUp(self):
        self.service = EventPushService.__new__(EventPushService)

    def test_new_events_render_official_fields(self):
        text = self.service._format_event(
            1019,
            {
                "map_name": "洛阳·战乱",
                "name": "赤兔",
                "server": "梦江南",
                "zone": "双一",
                "time": 1763616000,
            },
        )
        self.assertIn("【赤兔预告】", text)
        self.assertIn("马驹：赤兔", text)
        self.assertIn("地图：洛阳·战乱", text)
        self.assertIn("服务器：梦江南", text)

        text = self.service._format_event(
            1105,
            {
                "challenge_tong_name": "帮会甲",
                "opponent_tong_name": "帮会乙",
                "victory_tong_name": "帮会甲",
                "server": "梦江南",
                "zone": "双一",
                "time": 1763616000,
            },
        )
        self.assertIn("【帮会约战·完胜】", text)
        self.assertIn("挑战帮会：帮会甲", text)
        self.assertIn("获胜帮会：帮会甲", text)

        text = self.service._format_event(
            2007,
            {
                "location": "四川汶川",
                "magnitude": "4.8",
                "intensity": "VI",
                "depth": "10 千米",
                "latitude": 31.0,
                "longitude": 103.4,
                "time": 1763616000,
            },
        )
        self.assertIn("【地震信息】", text)
        self.assertIn("震中位置：四川汶川", text)
        self.assertIn("震级：4.8", text)

        text = self.service._format_event(
            1201,
            {
                "user_name": "剑网3",
                "article_text": "新资料片预热",
                "created_at": 1763616000,
                "url": "https://weibo.com/1",
                "article_id": "abc",
                "user_id": "42",
            },
        )
        self.assertIn("【微博更新】", text)
        self.assertIn("用户：剑网3", text)
        self.assertIn("正文：新资料片预热", text)

    def test_drop_amount_and_status_mapping(self):
        text = self.service._format_event(
            1012,
            {
                "map_name": "白帝江关",
                "role_name": "角色甲",
                "item_name": "玄晶",
                "item_amount": 0,
                "server": "梦江南",
                "zone": "双一",
                "time": 1763616000,
            },
        )
        self.assertIn("金额：副本掉落", text)

        self.assertEqual(self.service._format_field(0, "status"), "关服")
        self.assertEqual(self.service._format_field(1, "status"), "开服")

    def test_array_fields_join_names(self):
        text = self.service._format_event(
            1122,
            {
                "camp_name": "浩气盟",
                "chief_tong_name": "指挥帮会",
                "tong_names": ["帮会甲", "帮会乙"],
                "split_amount": "1000 金",
                "server": "梦江南",
                "zone": "双一",
                "time": 1763616000,
            },
        )
        self.assertIn("分红帮会：帮会甲、帮会乙", text)


class SubscriptionTableTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = AsyncSQLiteDB(":memory:")
        await self.db.connect()

    async def asyncTearDown(self):
        await self.db.close()

    async def test_fresh_table_contains_all_official_actions(self):
        service = EventPushService(Mock(), {}, self.db, Mock(), Mock())
        await service._init_subscription_table()

        columns = {
            row["name"]
            for row in await self.db.fetch_all(
                "PRAGMA table_info(event_push_subscriptions)"
            )
        }
        self.assertTrue({f"action_{action}" for action in EVENT_NAMES} <= columns)
        self.assertNotIn("action_1108", columns)
        self.assertNotIn("action_2005", columns)

    async def test_new_actions_can_be_saved(self):
        service = EventPushService(Mock(), {}, self.db, Mock(), Mock())
        await service._init_subscription_table()
        await service.save_subscription("session", True, [1019, 1201, 2007], "create")

        row = await self.db.select_one(
            "event_push_subscriptions", "session_id=?", ("session",)
        )
        self.assertEqual(row["enabled"], 1)
        self.assertEqual(row["action_1019"], 1)
        self.assertEqual(row["action_1201"], 1)
        self.assertEqual(row["action_2007"], 1)
        self.assertEqual(row["action_1001"], 0)

    async def test_removed_actions_are_rejected(self):
        service = EventPushService(Mock(), {}, self.db, Mock(), Mock())
        await service._init_subscription_table()
        for action in sorted(REMOVED_ACTIONS):
            with self.assertRaises(ValueError):
                await service.save_subscription("session", True, [action], "create")


if __name__ == "__main__":
    unittest.main()
