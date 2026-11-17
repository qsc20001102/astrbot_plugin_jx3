"""功能开关目录、本地持久化与 WebUI 保存逻辑的测试。"""

import ast
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from core import features
from core.feature_settings import FeatureSettingsService
from core.sqlite import AsyncSQLiteDB

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
MAIN_PATH = PLUGIN_ROOT / "main.py"
SCHEMA_PATH = PLUGIN_ROOT / "_conf_schema.json"


def command_map_commands() -> set[str]:
    """从 main.py 的 ini_command_map 里提取全部已注册指令名。"""
    tree = ast.parse(MAIN_PATH.read_text(encoding="utf-8"))
    plugin = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "Jx3ApiPlugin"
    )
    ini = next(
        node for node in plugin.body if getattr(node, "name", "") == "ini_command_map"
    )
    commands: set[str] = set()
    for node in ast.walk(ini):
        if isinstance(node, ast.Dict):
            for key in node.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    commands.add(key.value)
    return commands


class FeatureCatalogTest(unittest.TestCase):
    def test_every_command_has_a_home(self):
        commands = command_map_commands()
        covered = set(features.ALWAYS_ON_COMMANDS)
        for key in features.FEATURE_ORDER:
            covered |= set(features.FEATURE_COMMANDS[key])
        missing = sorted(commands - covered)
        self.assertFalse(
            missing,
            f"以下指令没有归入任何功能分组，请补录到 core/features.py：{missing}",
        )

    def test_groups_do_not_overlap(self):
        seen: dict[str, str] = {}
        for key in features.FEATURE_ORDER:
            for command in features.FEATURE_COMMANDS[key]:
                self.assertNotIn(
                    command,
                    seen,
                    f"「{command}」同时出现在 {seen.get(command)} 与 {key}",
                )
                seen[command] = key

    def test_always_on_commands_are_not_grouped(self):
        for command in features.ALWAYS_ON_COMMANDS:
            self.assertIsNone(
                features.command_feature(command),
                f"元指令「{command}」不应出现在功能分组里",
            )

    def test_grouped_commands_are_registered(self):
        commands = command_map_commands()
        for key in features.FEATURE_ORDER:
            for command in features.FEATURE_COMMANDS[key]:
                self.assertIn(
                    command,
                    commands,
                    f"分组 {key} 里的「{command}」并没有在 main.py 注册",
                )

    def test_groups_are_balanced(self):
        for key in features.FEATURE_ORDER:
            count = len(features.FEATURE_COMMANDS[key])
            self.assertGreaterEqual(
                count,
                2,
                f"分组 {key} 只有 {count} 条指令，卡片会显得过于零碎",
            )
            self.assertLessEqual(
                count,
                12,
                f"分组 {key} 有 {count} 条指令，卡片会过高；请按官方子类拆分",
            )

    def test_sections_cover_every_group(self):
        self.assertEqual(
            set(features.FEATURE_SECTIONS),
            set(features.FEATURE_SECTION_ORDER),
        )
        for key in features.FEATURE_ORDER:
            self.assertIn(
                features.FEATURE_INFO[key]["section"], features.FEATURE_SECTIONS
            )
        self.assertEqual(
            {features.FEATURE_INFO[key]["section"] for key in features.FEATURE_ORDER},
            set(features.FEATURE_SECTION_ORDER),
        )

    def test_removed_api_commands_are_absent(self):
        """JX3API 已移除的查询接口不再注册指令，也不再出现在功能目录中。"""
        commands = command_map_commands()
        for command in ("关隘", "阵营奉献", "未出", "成就", "装饰", "器物"):
            with self.subTest(command=command):
                self.assertNotIn(command, commands)
                self.assertNotIn(command, features.command_defaults())

    def test_config_schema_has_no_feature_switches(self):
        """功能开关只在 WebUI 中配置，不应再出现在插件配置结构中。"""
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertNotIn("features", schema)

    def test_resolve_enabled_falls_back_to_defaults(self):
        resolved = features.resolve_enabled(None)
        self.assertEqual(resolved, features.command_defaults())
        partial = features.resolve_enabled({"开团": False, "报名": "bad"})
        self.assertFalse(partial["开团"])
        # 非法类型回退默认开启。
        self.assertTrue(partial["报名"])
        self.assertTrue(partial["资历"])

    def test_normalize_selection_accepts_grouped_and_flat_payloads(self):
        grouped = features.normalize_selection(
            {"activity_calendar": {"日常": False, "未知指令": True}}
        )
        self.assertEqual(grouped, {"日常": False})
        flat = features.normalize_selection({"818": False, "日常": "关闭"})
        self.assertEqual(flat, {"818": False})

    def test_command_enabled_respects_toggles(self):
        enabled = features.resolve_enabled({"奇遇": False, "开团": False})
        self.assertTrue(features.command_enabled("资历", enabled))
        self.assertTrue(features.command_enabled("绑定区服", enabled))
        self.assertFalse(features.command_enabled("奇遇", enabled))
        self.assertFalse(features.command_enabled("开团", enabled))

    def test_describe_has_per_command_state(self):
        resolved = features.resolve_enabled({"818": False})
        tieba = next(
            item
            for item in features.describe(resolved)
            if item["key"] == "community_tieba"
        )
        self.assertEqual(
            tieba["total_count"],
            len(features.FEATURE_COMMANDS["community_tieba"]),
        )
        self.assertEqual(tieba["enabled_count"], tieba["total_count"] - 1)
        self.assertEqual(tieba["section_name"], "游戏社区")
        eight = next(cmd for cmd in tieba["commands"] if cmd["name"] == "818")
        self.assertFalse(eight["enabled"])


class FeatureSettingsServiceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.sql = AsyncSQLiteDB(str(Path(self.temp_dir.name) / "test.db"))
        await self.sql.connect()
        self.service = FeatureSettingsService(self.sql)
        await self.service.initialize()

    async def asyncTearDown(self):
        await self.sql.close()
        self.temp_dir.cleanup()

    async def test_defaults_are_all_enabled(self):
        self.assertEqual(await self.service.get_enabled(), features.command_defaults())

    async def test_save_persists_across_instances(self):
        saved = await self.service.save({"activity_calendar": {"日常": False}})
        self.assertFalse(saved["日常"])
        self.assertTrue(saved["日常预测"])

        reloaded = FeatureSettingsService(self.sql)
        await reloaded.initialize()
        self.assertFalse((await reloaded.get_enabled())["日常"])

    async def test_invalid_selection_is_rejected(self):
        with self.assertRaises(ValueError):
            await self.service.save({"activity_calendar": {"日常": "关闭"}})
        self.assertTrue((await self.service.get_enabled())["日常"])

    async def test_concurrent_saves_keep_both_updates(self):
        await asyncio.gather(
            self.service.save({"日常": False}),
            self.service.save({"开团": False}),
        )
        enabled = await self.service.get_enabled()
        self.assertFalse(enabled["日常"])
        self.assertFalse(enabled["开团"])
        self.assertTrue(enabled["日常预测"])


def load_feature_webui():
    """在不启动宿主的情况下加载真实的 WebUI 功能开关方法。

    Returns:
        使用隔离宿主响应实现的 WebUI 服务类。
    """
    path = PLUGIN_ROOT / "core" / "webui.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    service = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "WebUIService"
    )
    service.body = [
        node
        for node in service.body
        if getattr(node, "name", "")
        in {"__init__", "get_feature_status", "save_features"}
    ]
    namespace = {
        "asyncio": asyncio,
        "features": features,
        "logger": Mock(),
        "json_response": lambda data: data,
        "error_response": lambda message, status_code: {
            "error": message,
            "status_code": status_code,
        },
    }
    module = ast.Module(body=[tree.body[0], service], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(path), "exec"), namespace)
    return namespace["WebUIService"]


class FeatureWebUITest(unittest.IsolatedAsyncioTestCase):
    service_class = load_feature_webui()

    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.sql = AsyncSQLiteDB(str(Path(self.temp_dir.name) / "test.db"))
        await self.sql.connect()
        self.feature_settings = FeatureSettingsService(self.sql)
        await self.feature_settings.initialize()
        self.plugin = SimpleNamespace(apply_feature_settings=Mock())
        self.service = self.service_class(
            jx3api=None,
            event_push=None,
            server_binding=None,
            kungfu_alias=None,
            session_control=None,
            feature_settings=self.feature_settings,
            cache=None,
            team=None,
            team_rules=None,
            team_kungfu_icons=None,
            plugin=self.plugin,
        )
        self.service._json_payload = AsyncMock(
            return_value={"features": {"activity_calendar": {"日常": False}}}
        )

    async def asyncTearDown(self):
        await self.sql.close()
        self.temp_dir.cleanup()

    async def test_save_persists_and_applies_after_storage(self):
        result = await self.service.save_features()
        self.assertTrue(result["saved"])
        self.assertFalse(result["features"]["日常"])
        self.assertTrue(result["features"]["日常预测"])
        self.plugin.apply_feature_settings.assert_called_once_with()

        reloaded = FeatureSettingsService(self.sql)
        await reloaded.initialize()
        self.assertFalse((await reloaded.get_enabled())["日常"])

        status = await self.service.get_feature_status()
        self.assertFalse(status["features"]["日常"])
        self.assertEqual(len(status["feature_catalog"]), len(features.FEATURE_ORDER))

    async def test_invalid_payload_does_not_apply_settings(self):
        self.service._json_payload = AsyncMock(
            return_value={"features": {"activity_calendar": {"日常": "关闭"}}}
        )
        result = await self.service.save_features()
        self.assertEqual(result["status_code"], 400)
        self.plugin.apply_feature_settings.assert_not_called()
        self.assertTrue((await self.feature_settings.get_enabled())["日常"])

    async def test_storage_failure_does_not_apply_settings(self):
        self.feature_settings.save = AsyncMock(side_effect=RuntimeError("disk full"))
        result = await self.service.save_features()
        self.assertEqual(result["status_code"], 500)
        self.plugin.apply_feature_settings.assert_not_called()

    async def test_concurrent_saves_apply_both_updates(self):
        self.service._json_payload.side_effect = [
            {"features": {"activity_calendar": {"日常": False}}},
            {"features": {"local_team_signup": {"开团": False}}},
        ]
        first, second = await asyncio.gather(
            self.service.save_features(),
            self.service.save_features(),
        )
        self.assertTrue(first["saved"])
        self.assertTrue(second["saved"])
        enabled = await self.feature_settings.get_enabled()
        self.assertFalse(enabled["日常"])
        self.assertFalse(enabled["开团"])
        self.assertEqual(self.plugin.apply_feature_settings.call_count, 2)


if __name__ == "__main__":
    unittest.main()
