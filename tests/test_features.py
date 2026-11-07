"""功能开关目录与实际指令表的一致性测试。"""

import ast
import asyncio
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from core import features

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

    def test_schema_features_match_catalog(self):
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        features_schema = schema["features"]
        self.assertEqual(features_schema["type"], "object")
        self.assertEqual(
            set(features_schema["items"]),
            set(features.FEATURE_ORDER),
            "schema 的 features 分组与 core/features.py 不一致",
        )
        for key, group in features_schema["items"].items():
            self.assertEqual(group["type"], "object")
            self.assertEqual(
                set(group["items"]),
                set(features.FEATURE_COMMANDS[key]),
                f"分组 {key} 的指令与 core/features.py 不一致",
            )
            for command, item in group["items"].items():
                self.assertEqual(item["type"], "bool")
                self.assertTrue(
                    bool(item["default"]),
                    f"分组 {key} 的「{command}」默认值应为开启",
                )

    def test_resolve_enabled_falls_back_to_defaults(self):
        resolved = features.resolve_enabled(None)
        self.assertEqual(resolved, features.command_defaults())
        partial = features.resolve_enabled(
            {"team": {"开团": False, "报名": "bad"}, "basic": "bad"}
        )
        self.assertFalse(partial["开团"])
        # 非法类型回退默认开启（报名 / basic 里的指令默认开启）。
        self.assertTrue(partial["报名"])
        self.assertTrue(partial["资历"])

    def test_command_enabled_respects_toggles(self):
        enabled = features.resolve_enabled(
            {
                "role_event": {"奇遇": False},
                "local_team_signup": {"开团": False},
            }
        )
        self.assertTrue(features.command_enabled("资历", enabled))
        self.assertTrue(features.command_enabled("绑定区服", enabled))
        self.assertFalse(features.command_enabled("奇遇", enabled))
        self.assertFalse(features.command_enabled("开团", enabled))

    def test_describe_has_per_command_state(self):
        resolved = features.resolve_enabled({"community_tieba": {"818": False}})
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


def load_feature_webui():
    """Load the production WebUI methods without starting the host.

    Returns:
        WebUI service class with isolated host response helpers.
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
        in {"__init__", "_plugin_conf", "get_feature_status", "save_features"}
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


class LegacyConfig(dict):
    """Expose the synchronous configuration API supported by older hosts."""

    def __init__(self, path):
        super().__init__(
            prefix={"enable": False},
            features={"activity_calendar": {"日常": True}},
        )
        self.path = path
        self.saved_thread = None

    def save_config(self):
        """Persist the current configuration and record the calling thread."""
        self.saved_thread = threading.get_ident()
        self.path.write_text(json.dumps(self), encoding="utf-8")


class FeatureSaveTest(unittest.IsolatedAsyncioTestCase):
    service_class = load_feature_webui()

    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "config.json"
        self.conf = LegacyConfig(self.path)
        self.conf.save_config()
        self.plugin = SimpleNamespace(
            conf=self.conf,
            apply_feature_settings=Mock(),
        )
        self.service = self.service_class(*([None] * 10), plugin=self.plugin)
        self.service._json_payload = AsyncMock(
            return_value={"features": {"activity_calendar": {"日常": False}}}
        )

    async def asyncTearDown(self):
        self.temp_dir.cleanup()

    async def test_save_works_with_sync_only_host_and_applies_after_persistence(self):
        self.plugin.apply_feature_settings.side_effect = lambda: self.assertFalse(
            json.loads(self.path.read_text(encoding="utf-8"))["features"][
                "activity_calendar"
            ]["日常"]
        )
        result = await self.service.save_features()
        self.assertTrue(result["saved"])
        self.assertFalse(result["features"]["日常"])
        self.assertTrue(result["features"]["日常预测"])
        self.assertEqual(self.conf["prefix"], {"enable": False})
        self.assertNotEqual(self.conf.saved_thread, threading.get_ident())
        self.plugin.apply_feature_settings.assert_called_once_with()

    async def test_failed_save_restores_status_and_does_not_apply_settings(self):
        for has_features in (True, False):
            with self.subTest(has_features=has_features):
                if not has_features:
                    self.conf.pop("features")
                    LegacyConfig.save_config(self.conf)
                previous = dict(self.conf)
                disk_before = self.path.read_bytes()
                self.conf.save_config = Mock(side_effect=OSError("disk full"))
                result = await self.service.save_features()
                self.assertEqual(result["status_code"], 500)
                self.assertEqual(self.conf, previous)
                self.assertEqual(self.path.read_bytes(), disk_before)
                self.plugin.apply_feature_settings.assert_not_called()
                status = await self.service.get_feature_status()
                self.assertTrue(status["features"]["日常"])

    async def test_concurrent_saves_preserve_both_updates_and_hide_pending_status(self):
        started, release = threading.Event(), threading.Event()
        save_config = self.conf.save_config

        def blocking_save():
            if not started.is_set():
                started.set()
                if not release.wait(3):
                    raise TimeoutError("Save was not released")
            save_config()

        self.conf.save_config = Mock(side_effect=blocking_save)
        self.service._json_payload.side_effect = [
            {"features": {"activity_calendar": {"日常": False}}},
            {"features": {"local_team_signup": {"开团": False}}},
        ]
        first = asyncio.create_task(self.service.save_features())
        pending = [first]
        try:
            self.assertTrue(await asyncio.to_thread(started.wait, 2))
            second = asyncio.create_task(self.service.save_features())
            status = asyncio.create_task(self.service.get_feature_status())
            pending.extend((second, status))
            await asyncio.sleep(0)
            self.assertEqual(self.conf.save_config.call_count, 1)
            self.assertFalse(status.done())
        finally:
            release.set()
            results = await asyncio.gather(*pending)
        self.assertTrue(results[0]["saved"])
        self.assertTrue(results[1]["saved"])
        self.assertFalse(results[2]["features"]["日常"])
        self.assertFalse(results[2]["features"]["开团"])
        self.assertEqual(self.plugin.apply_feature_settings.call_count, 2)
        disk = json.loads(self.path.read_text(encoding="utf-8"))["features"]
        self.assertFalse(disk["activity_calendar"]["日常"])
        self.assertFalse(disk["local_team_signup"]["开团"])


if __name__ == "__main__":
    unittest.main()
