import ast
import copy
import inspect
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from core.sqlite import AsyncSQLiteDB
from core.template import secure_render_template
from jinja2 import Environment, StrictUndefined

host = types.ModuleType("astrbot")
host.logger = Mock()
api = types.ModuleType("astrbot.api")
api.logger = host.logger
api.AstrBotConfig = dict
components = types.ModuleType("astrbot.api.message_components")
with patch.dict(
    "sys.modules",
    {
        "astrbot": host,
        "astrbot.api": api,
        "astrbot.api.message_components": components,
    },
):
    from core.cache import CacheService
    from core.jx3api_data import JX3APIService
    from core.request import APIErrorResponse


ROOT = Path(__file__).resolve().parents[1]
ATTRIBUTE_DATA = {
    "zoneName": "电信区",
    "serverName": "梦江南",
    "roleName": "测试角色",
    "forceName": "少林",
    "kungfuName": "易筋经",
    "kungfuType": "DPS",
    "bodyName": "正太",
    "campName": "浩气盟",
    "tongName": "测试帮会",
    "cacheTime": 1792502494,
    "equipType": "竞技对抗",
    "equipScore": 670564,
    "panelList": [
        {"name": "会心等级", "value": 66497, "percent": 33.63},
        {"name": "无双等级", "value": 0, "percent": 0},
        {"name": "破招值", "value": 0},
        {"name": "气血上限", "value": 3200614},
        {"name": "会心效果等级", "value": 5850, "percent": 183.03},
        {"name": "元气", "value": 15712},
    ],
    "equipList": [
        {
            "itemName": "普通装备",
            "iconId": 22119,
            "itemLevel": 37400,
            "magicType": "伤害,破防,化劲",
            "itemPlus": None,
            "itemSource": "威名点",
            "strengthLevel": 6,
            "maxStrengthLevel": 6,
            "colorDiamond": {"iconId": "2351", "itemName": "测试五彩石"},
            "mountDiamond": [{"iconId": 7529, "itemName": "五行石（七级）"}],
            "minEnchant": {"itemName": "测试小附魔"},
            "maxEnchant": {"itemName": "测试大附魔"},
            "itemMagic": [],
        },
        {
            "itemName": "特效装备",
            "iconId": 2852,
            "itemLevel": 33000,
            "magicType": "伤害,会心,化劲",
            "itemPlus": "特效",
            "itemSource": "",
            "strengthLevel": 6,
            "maxStrengthLevel": 8,
            "mountDiamond": [],
            "minEnchant": [],
            "maxEnchant": [],
            "itemMagic": [{"itemDesc": "装备：测试特效说明。\n第二行说明。"}],
        },
    ],
    "suits": [
        {
            "name": "测试套装",
            "count": 2,
            "attributes": [
                {"name": "会心等级", "value": 3716, "pieces": 2},
                {"name": "未激活属性", "value": 1000, "pieces": 4},
            ],
        }
    ],
}


class AttributeTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = AsyncSQLiteDB(":memory:")
        await self.db.connect()
        self.cache = CacheService(self.db, Path(self.temp_dir.name) / "images")
        await self.cache.initialize()
        self.service = JX3APIService(
            {"jx3api_token": "test-token"}, self.db, self.cache
        )
        self.api_get = AsyncMock(
            side_effect=[
                copy.deepcopy(ATTRIBUTE_DATA),
                {"showAvatar": "https://example.com/card.png"},
            ]
        )
        self.service._api.get = self.api_get

    async def asyncTearDown(self):
        await self.service.close()
        await self.cache.stop()
        await self.db.close()
        self.temp_dir.cleanup()

    async def render(self, result):
        template = Environment(undefined=StrictUndefined).from_string(
            secure_render_template(result["temp"])
        )
        return template.render(
            **result["data"], icons={"sect": {}}, data_time="2026-10-24 18:00:00"
        )

    async def test_request_contract_and_both_api_caches(self):
        first = await self.service.shuxing("梦江南", "测试角色")
        second = await self.service.shuxing("梦江南", "测试角色")
        self.assertEqual(first["code"], 200)
        self.assertEqual(second["code"], 200)
        self.assertEqual(self.api_get.await_count, 2)
        attribute_call, card_call = self.api_get.await_args_list
        self.assertEqual(
            attribute_call.args, ("https://www.jx3api.com/calcd/attribute",)
        )
        self.assertEqual(
            attribute_call.kwargs["params"],
            {
                "server": "梦江南",
                "name": "测试角色",
                "format": "calcd",
                "token": "test-token",
            },
        )
        self.assertEqual(card_call.args, ("https://www.jx3api.com/card/record",))
        self.assertEqual(
            card_call.kwargs["params"],
            {"server": "梦江南", "name": "测试角色", "token": "test-token"},
        )
        self.assertFalse(first["_cache"]["hit"])
        self.assertTrue(second["_cache"]["hit"])
        dashboard = await self.cache.dashboard()
        self.assertIn("/calcd/attribute", {item["name"] for item in dashboard["api"]})

    async def test_render_equipment_panel_stones_enchants_without_suits(self):
        result = await self.service.shuxing("梦江南", "测试角色")
        html = await self.render(result)
        for text in (
            "670,564",
            "3,200,614",
            "33.63%",
            "183.03%",
            "0.00%",
            "https://example.com/card.png",
            "icon/22119.png",
            "item/purple.png",
            "item/orange.gif",
            "测试五彩石",
            "测试小附魔",
            "测试大附魔",
            "五行石（七级）",
            "精炼 6/8",
            "第二行说明。",
            "2026-10-20 21:21:34",
            "data-jx3-data-time",
        ):
            with self.subTest(text=text):
                self.assertIn(text, html)
        self.assertEqual(html.count('class="equipment-row'), 2)
        self.assertNotIn("套装效果", html)
        self.assertNotIn("测试套装", html)
        self.assertNotIn("未激活属性", html)

    async def test_server_search_reuses_api_cache(self):
        self.api_get.side_effect = None
        self.api_get.return_value = {"server": "乾坤一掷"}

        first = await self.service.server_search("华乾")
        second = await self.service.server_search("华乾")

        self.assertEqual(first, "乾坤一掷")
        self.assertEqual(second, "乾坤一掷")
        self.assertEqual(self.api_get.await_count, 1)

    async def test_online_status_is_shown_in_role_info(self):
        self.service.ticket = "test-ticket"
        post = AsyncMock(
            return_value=[
                {
                    "roleName": "测试角色",
                    "serverName": "梦江南",
                    "onlineStatus": True,
                    "gameLogin": True,
                    "appLogin": False,
                }
            ]
        )
        self.service._api.post = post

        result = await self.service.shuxing("梦江南", "测试角色")
        html = await self.render(result)

        post.assert_awaited_once()
        self.assertEqual(
            post.await_args.args,
            ("https://www.jx3api.com/role/online/status",),
        )
        self.assertEqual(
            post.await_args.kwargs["data"],
            {
                "query": [{"server": "梦江南", "name": "测试角色"}],
                "ticket": "test-ticket",
            },
        )
        self.assertEqual(
            post.await_args.kwargs["headers"], {"token": "test-token"}
        )
        for text in (
            "在线状态",
            "attribute-online--online",
            "游戏登录",
            "推栏登录",
            "已登录",
            "未登录",
        ):
            with self.subTest(text=text):
                self.assertIn(text, html)

    async def test_online_status_hidden_when_ticket_is_missing(self):
        post = AsyncMock()
        self.service._api.post = post

        result = await self.service.shuxing("梦江南", "测试角色")
        html = await self.render(result)

        post.assert_not_awaited()
        self.assertNotIn("在线状态", html)
        self.assertIn("670,564", html)

    async def test_missing_or_failed_card_does_not_hide_attributes(self):
        for card in (
            None,
            APIErrorResponse(404, "暂无名片"),
            RuntimeError("card unavailable"),
        ):
            with self.subTest(card=type(card).__name__):
                await self.cache.clear_item("api", "/card/record")
                self.api_get.side_effect = [copy.deepcopy(ATTRIBUTE_DATA), card]
                await self.cache.clear_item("api", "/calcd/attribute")
                result = await self.service.shuxing("梦江南", "测试角色")
                self.assertEqual(result["code"], 200)
                html = await self.render(result)
                self.assertIn("暂未获取到角色名片", html)
                self.assertIn("670,564", html)

    async def test_attribute_errors_and_empty_data_do_not_request_card(self):
        for response in (None, {}, APIErrorResponse(403, "令牌权限不足")):
            with self.subTest(response=type(response).__name__):
                await self.cache.clear_item("api", "/calcd/attribute")
                self.api_get.reset_mock()
                self.api_get.side_effect = None
                self.api_get.return_value = response
                result = await self.service.shuxing("梦江南", "测试角色")
                self.assertNotEqual(result["code"], 200)
                self.api_get.assert_awaited_once()

    async def test_sparse_data_and_html_escaping(self):
        self.api_get.side_effect = [
            {"roleName": '<script>alert("role")</script>'},
            None,
        ]
        result = await self.service.shuxing("梦江南", "测试角色")
        html = await self.render(result)
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("暂无装备数据", html)
        self.assertIn("暂无属性数据", html)

    async def test_real_handler_reuses_image_pipeline_and_server_binding(self):
        from test_command_routing import load_dispatch_plugin

        tree = ast.parse((ROOT / "core" / "message.py").read_text(encoding="utf-8"))
        builder = next(node for node in tree.body if isinstance(node, ast.ClassDef))
        handler = next(
            node for node in builder.body if getattr(node, "name", "") == "shuxing"
        )
        namespace = {"AstrMessageEvent": object}
        exec(
            compile(ast.Module(body=[handler], type_ignores=[]), "message.py", "exec"),
            namespace,
        )
        self.service.server_search = AsyncMock(return_value=None)
        fake_builder = types.SimpleNamespace(jx3api=self.service)

        async def image_pipeline(event, action):
            return await action()

        fake_builder.T2I_image_msg = AsyncMock(side_effect=image_pipeline)
        bound_handler = types.MethodType(namespace["shuxing"], fake_builder)
        plugin = load_dispatch_plugin(ROOT / "main.py")()
        plugin.prefix = {"enable": False}
        plugin.command_map = {"属性": bound_handler}
        plugin.session_control = types.SimpleNamespace(
            is_allowed=Mock(return_value=True)
        )
        plugin.cache = self.cache
        plugin.jx3api = self.service
        plugin._prepare_kungfu_args = Mock(side_effect=lambda handler, args: args)
        for name in ("_prepare_server_args", "_call_with_auto_args"):
            main_tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
            plugin_class = next(
                node for node in main_tree.body if isinstance(node, ast.ClassDef)
            )
            method = next(
                node for node in plugin_class.body if getattr(node, "name", "") == name
            )
            namespace = {"AstrMessageEvent": object, "inspect": inspect}
            exec(
                compile(ast.Module(body=[method], type_ignores=[]), "main.py", "exec"),
                namespace,
            )
            setattr(plugin, name, types.MethodType(namespace[name], plugin))
        plugin.server_binding = types.SimpleNamespace(
            get_binding=AsyncMock(return_value="梦江南"),
            is_all_servers_query=Mock(return_value=False),
        )
        event = types.SimpleNamespace(
            message_str="属性 测试角色",
            message_obj=types.SimpleNamespace(message_str="属性 测试角色"),
            is_at_or_wake_command=False,
            unified_msg_origin="test:GroupMessage:example",
            stop_event=Mock(),
            should_call_llm=Mock(),
            plain_result=lambda message: message,
        )
        results = [item async for item in plugin.on_all_message(event)]
        self.assertEqual(results[0]["code"], 200)
        fake_builder.T2I_image_msg.assert_awaited_once()
        self.assertEqual(
            self.api_get.await_args_list[0].kwargs["params"]["server"], "梦江南"
        )
        event.stop_event.assert_called_once()


if __name__ == "__main__":
    unittest.main()
