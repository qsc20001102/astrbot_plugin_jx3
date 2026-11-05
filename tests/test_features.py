"""功能开关目录与实际指令表的一致性测试。"""

import ast
import json
import sys
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from core import features

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
        node
        for node in plugin.body
        if getattr(node, "name", "") == "ini_command_map"
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
            self.assertIn(features.FEATURE_INFO[key]["section"], features.FEATURE_SECTIONS)
        self.assertEqual(
            {
                features.FEATURE_INFO[key]["section"]
                for key in features.FEATURE_ORDER
            },
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


if __name__ == "__main__":
    unittest.main()
