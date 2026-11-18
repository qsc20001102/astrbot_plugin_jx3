"""Exercise the actual dispatch methods without starting AstrBot or its services."""

import ast
import inspect
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock


def load_dispatch_plugin(source_path: Path):
    # Compile the production methods, rather than reproducing their parser in
    # tests. This keeps the regression runnable with the Python standard library
    # and avoids registering a plugin or loading real credentials/databases.
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    plugin = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "Jx3ApiPlugin"
    )
    names = {
        "parse_message",
        "resolve_command",
        "on_all_message",
        "_prepare_server_args",
    }
    methods = [node for node in plugin.body if getattr(node, "name", "") in names]
    if {node.name for node in methods} != names:
        raise AssertionError("Production command dispatch methods are missing")
    for method in methods:
        method.decorator_list = []
    plugin.bases = []
    plugin.keywords = []
    plugin.decorator_list = []
    plugin.body = methods
    module = ast.Module(body=[plugin], type_ignores=[])
    namespace = {"AstrMessageEvent": object, "logger": Mock(), "inspect": inspect}
    exec(
        compile(ast.fix_missing_locations(module), str(source_path), "exec"), namespace
    )
    return namespace["Jx3ApiPlugin"]


class CommandRoutingTest(unittest.IsolatedAsyncioTestCase):
    plugin_class = load_dispatch_plugin(Path(__file__).resolve().parents[1] / "main.py")

    def setUp(self):
        self.plugin = self.plugin_class()
        self.plugin.prefix = {
            "follow_astrbot_wake": True,
            "enable": True,
            "text": "jx3",
        }
        self.handler = Mock()
        self.plugin.command_map = {"日常": self.handler}

    @staticmethod
    def event(processed, *, awake=True, original=None):
        return SimpleNamespace(
            is_at_or_wake_command=awake,
            message_str=processed,
            message_obj=SimpleNamespace(
                message_str=processed if original is None else original
            ),
            unified_msg_origin="test:GroupMessage:example",
            stop_event=Mock(),
            should_call_llm=Mock(),
            plain_result=lambda message: message,
        )

    def test_unawakened_bot_rejects_matching_plugin_command(self):
        event = self.event("jx3 日常", awake=False)
        self.assertIsNone(self.plugin.resolve_command(event))

    def test_host_wake_then_plugin_prefix_preserves_arguments(self):
        event = self.event("jx3 日常 梦江南", original="/jx3 日常 梦江南")
        self.assertEqual(
            self.plugin.resolve_command(event), ("日常", ["梦江南"], self.handler)
        )

    def test_awake_event_still_requires_enabled_plugin_prefix(self):
        self.assertIsNone(self.plugin.resolve_command(self.event("日常")))

    def test_raw_text_cannot_override_processed_text(self):
        event = self.event("普通聊天", original="jx3 日常")
        self.assertIsNone(self.plugin.resolve_command(event))

    def test_missing_wake_setting_defaults_to_legacy_mode(self):
        self.plugin.prefix.pop("follow_astrbot_wake")
        self.assertEqual(
            self.plugin.resolve_command(self.event("jx3 日常", awake=False)),
            ("日常", [], self.handler),
        )

    def test_legacy_mode_restores_original_text_fallback(self):
        self.plugin.prefix["follow_astrbot_wake"] = False
        event = self.event("日常 梦江南", awake=False, original="jx3 日常 梦江南")
        self.assertEqual(
            self.plugin.resolve_command(event), ("日常", ["梦江南"], self.handler)
        )

    def test_legacy_mode_prefers_matching_processed_text(self):
        self.plugin.prefix["follow_astrbot_wake"] = False
        event = self.event("jx3 日常 梦江南", original="jx3 日常 长安城")
        self.assertEqual(
            self.plugin.resolve_command(event), ("日常", ["梦江南"], self.handler)
        )

    def test_wake_gate_and_plugin_prefix_are_independent(self):
        for follow_wake in (False, True):
            for enable_prefix in (False, True):
                for awake in (False, True):
                    with self.subTest(
                        follow_wake=follow_wake,
                        enable_prefix=enable_prefix,
                        awake=awake,
                    ):
                        self.plugin.prefix["follow_astrbot_wake"] = follow_wake
                        self.plugin.prefix["enable"] = enable_prefix
                        text = "jx3 日常 梦江南" if enable_prefix else "日常 梦江南"
                        event = self.event(text, awake=awake)
                        expected = (
                            None
                            if follow_wake and not awake
                            else ("日常", ["梦江南"], self.handler)
                        )
                        self.assertEqual(self.plugin.resolve_command(event), expected)
                        if enable_prefix:
                            self.assertIsNone(
                                self.plugin.resolve_command(
                                    self.event("日常 梦江南", awake=awake)
                                )
                            )

    def test_disabled_prefix_does_not_disable_host_wake_gate(self):
        self.plugin.prefix["enable"] = False
        self.assertIsNone(self.plugin.resolve_command(self.event("日常", awake=False)))
        self.assertEqual(
            self.plugin.resolve_command(self.event("日常", original="/日常")),
            ("日常", [], self.handler),
        )

    def test_blank_plugin_prefix_retains_existing_behavior(self):
        self.plugin.prefix["text"] = "   "
        self.assertEqual(
            self.plugin.resolve_command(self.event("日常")),
            ("日常", [], self.handler),
        )
        self.assertIsNone(self.plugin.resolve_command(self.event("日常", awake=False)))

    def test_whitespace_empty_and_unrelated_messages(self):
        for text in ("", "  ", "jx3", "jx3 不存在", "普通聊天"):
            with self.subTest(text=text):
                self.assertIsNone(self.plugin.resolve_command(self.event(text)))
        self.assertEqual(
            self.plugin.resolve_command(self.event("  jx3  日常  ")),
            ("日常", [], self.handler),
        )

    async def test_prepare_server_args_resolves_official_name(self):
        async def handler(self, event, server, name):
            return server, name

        self.plugin.server_binding = SimpleNamespace(
            get_binding=AsyncMock(return_value=""),
            is_all_servers_query=Mock(return_value=False),
        )
        self.plugin.jx3api = SimpleNamespace(
            server_search=AsyncMock(return_value="梦江南")
        )
        event = self.event("查询 华乾 角色")

        self.assertEqual(
            await self.plugin._prepare_server_args(handler, event, ["华乾", "角色"]),
            ["梦江南", "角色"],
        )
        self.plugin.jx3api.server_search.assert_awaited_once_with("华乾")

    async def test_prepare_server_args_inserts_binding_when_lookup_fails(self):
        async def handler(self, event, server, name):
            return server, name

        self.plugin.server_binding = SimpleNamespace(
            get_binding=AsyncMock(return_value="梦江南"),
            is_all_servers_query=Mock(return_value=False),
        )
        self.plugin.jx3api = SimpleNamespace(server_search=AsyncMock(return_value=None))
        event = self.event("查询 角色")

        self.assertEqual(
            await self.plugin._prepare_server_args(handler, event, ["角色"]),
            ["梦江南", "角色"],
        )
        self.plugin.jx3api.server_search.assert_awaited_once_with("角色")

    async def test_prepare_server_args_supports_all_servers_and_explicit_alias(self):
        async def handler(self, event, server, name):
            return server, name

        self.plugin.server_binding = SimpleNamespace(
            get_binding=AsyncMock(return_value="梦江南"),
            is_all_servers_query=Mock(side_effect=lambda value: value == "全区"),
        )
        search = AsyncMock(return_value="乾坤一掷")
        self.plugin.jx3api = SimpleNamespace(server_search=search)
        event = self.event("查询 全区 角色")

        self.assertEqual(
            await self.plugin._prepare_server_args(handler, event, ["全区", "角色"]),
            ["", "角色"],
        )
        search.assert_not_awaited()

        self.assertEqual(
            await self.plugin._prepare_server_args(handler, event, ["华乾", "角色"]),
            ["乾坤一掷", "角色"],
        )
        search.assert_awaited_once_with("华乾")

    async def test_rejected_message_does_not_stop_other_plugins_or_llm(self):
        event = self.event("jx3 日常", awake=False)
        self.plugin.session_control = Mock()
        self.plugin._call_with_auto_args = AsyncMock()
        self.assertEqual(
            [result async for result in self.plugin.on_all_message(event)], []
        )
        event.stop_event.assert_not_called()
        event.should_call_llm.assert_not_called()
        self.plugin.session_control.is_allowed.assert_not_called()
        self.plugin._call_with_auto_args.assert_not_awaited()

    async def test_command_dispatches_once_in_both_wake_modes(self):
        for follow_wake in (False, True):
            with self.subTest(follow_wake=follow_wake):
                self.plugin.prefix["follow_astrbot_wake"] = follow_wake
                event = self.event(
                    "jx3 日常 梦江南", awake=follow_wake, original="/jx3 日常 梦江南"
                )
                self.plugin.session_control = SimpleNamespace(
                    is_allowed=Mock(return_value=True)
                )
                self.plugin._prepare_server_args = AsyncMock(return_value=["梦江南"])
                self.plugin._prepare_kungfu_args = Mock(
                    side_effect=lambda handler, args: args
                )
                self.plugin.cache = Mock()
                self.plugin._call_with_auto_args = AsyncMock(return_value="查询结果")

                self.assertEqual(
                    [result async for result in self.plugin.on_all_message(event)],
                    ["查询结果"],
                )
                event.stop_event.assert_called_once()
                self.plugin._call_with_auto_args.assert_awaited_once_with(
                    self.handler, event, ["梦江南"]
                )
                self.plugin.cache.leave_command.assert_called_once_with(
                    self.plugin.cache.enter_command.return_value
                )


if __name__ == "__main__":
    unittest.main()
