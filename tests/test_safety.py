import asyncio
import logging
import sqlite3
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from aiohttp import web
from jinja2 import Environment

from core.sqlite import AsyncSQLiteDB
from core.template import TemplateRepository, secure_render_template

# 请求层只使用宿主的 logger；单元测试不需要启动 AstrBot。
with patch.dict("sys.modules", {
    "astrbot": types.ModuleType("astrbot"),
    "astrbot.api": types.SimpleNamespace(logger=logging.getLogger("request-test")),
}):
    from core.request import APIClient


class DatabaseSafetyTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = AsyncSQLiteDB(":memory:")
        await self.db.connect()
        await self.db.execute("CREATE TABLE records (value TEXT UNIQUE)")

    async def asyncTearDown(self):
        await self.db.close()

    async def test_other_writer_cannot_commit_failed_transaction(self):
        entered, release, waiting = asyncio.Event(), asyncio.Event(), asyncio.Event()

        async def failing_writer():
            with self.assertRaises(ValueError):
                async with self.db.transaction():
                    await self.db.execute("INSERT INTO records VALUES ('rollback')")
                    entered.set()
                    await release.wait()
                    raise ValueError("rollback")

        async def other_writer():
            waiting.set()
            await self.db.execute("INSERT INTO records VALUES ('keep')")

        first = asyncio.create_task(failing_writer())
        await entered.wait()
        second = asyncio.create_task(other_writer())
        await waiting.wait()
        self.assertFalse(second.done())
        release.set()
        await asyncio.wait_for(asyncio.gather(first, second), 3)
        self.assertEqual(await self.db.fetch_all("SELECT * FROM records"), [{"value": "keep"}])

    async def test_reader_cannot_observe_uncommitted_data(self):
        entered, release = asyncio.Event(), asyncio.Event()

        async def writer():
            async with self.db.transaction():
                await self.db.execute("INSERT INTO records VALUES ('hidden')")
                entered.set()
                await release.wait()

        task = asyncio.create_task(writer())
        await entered.wait()
        reader = asyncio.create_task(self.db.fetch_all("SELECT * FROM records"))
        await asyncio.sleep(0)
        self.assertFalse(reader.done())
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(await asyncio.wait_for(reader, 3), [])
        await self.db.execute("INSERT INTO records VALUES ('after cancellation')")

    async def test_nested_failure_rolls_back_only_savepoint(self):
        async with self.db.transaction():
            await self.db.execute("INSERT INTO records VALUES ('outer')")
            with self.assertRaises(ValueError):
                async with self.db.transaction():
                    await self.db.execute("INSERT INTO records VALUES ('inner')")
                    raise ValueError("nested")
        self.assertEqual(await self.db.fetch_all("SELECT * FROM records"), [{"value": "outer"}])

    async def test_batch_failure_is_atomic(self):
        with self.assertRaises(sqlite3.IntegrityError):
            await self.db.execute_transaction([
                ("INSERT INTO records VALUES (?)", ("duplicate",)),
                ("INSERT INTO records VALUES (?)", ("duplicate",)),
            ])
        self.assertEqual(await self.db.fetch_all("SELECT * FROM records"), [])


class RequestSafetyTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        async def handler(request):
            if request.path == "/large":
                return web.Response(body=b"x" * 1025)
            if request.path == "/bad":
                return web.Response(text="secret-token", status=500)
            if request.path == "/invalid":
                return web.Response(text="secret-token")
            return web.json_response({"code": 200, "data": {"token": "secret-token"}})

        app = web.Application()
        app.router.add_route("*", "/{path:.*}", handler)
        self.runner = web.AppRunner(app, access_log=None)
        await self.runner.setup()
        server = await asyncio.get_running_loop().create_server(
            self.runner.server, "127.0.0.1", 0,
        )
        self.server = server
        self.url = f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}"
        self.client = APIClient(max_response_bytes=1024)

    async def asyncTearDown(self):
        await self.client.close()
        self.server.close()
        await self.server.wait_closed()
        await self.runner.cleanup()

    async def test_success_and_failures_do_not_log_credentials(self):
        with self.assertLogs("request-test", level="DEBUG") as logs:
            result = await self.client.post(self.url + "/?token=secret-token", {"ticket": "secret-ticket"}, out_key="data")
            self.assertEqual(result, {"token": "secret-token"})
            for path in ("bad", "invalid"):
                self.assertIsNone(await self.client.get(self.url + f"/{path}?token=secret-token"))
        self.assertNotIn("secret-token", str(logs.output))
        self.assertNotIn("secret-ticket", str(logs.output))

    async def test_oversized_response_rejected_and_session_reusable(self):
        with self.assertLogs("request-test", level="ERROR"):
            self.assertIsNone(await self.client.get(self.url + "/large"))
        self.assertIsNotNone(await self.client.get(self.url + "/ok"))


class TemplateSafetyTest(unittest.IsolatedAsyncioTestCase):
    async def test_escaping_independent_of_renderer_defaults(self):
        template = secure_render_template('<div title="{{ name }}">{{ name }}</div>')
        output = Environment(autoescape=False).from_string(template).render(name='"><script>alert(1)</script>')
        self.assertNotIn("<script>", output)
        self.assertIn("&lt;script&gt;", output)

    async def test_market_empty_and_legacy_sale_groups(self):
        repo = TemplateRepository(Path(__file__).parents[1] / "templates")
        template = Environment().from_string(secure_render_template(await repo.get("wujia.html")))
        empty = template.render(name="测试", list=[])
        self.assertEqual(empty.count('colspan="4"'), 6)
        self.assertEqual(empty.count("<th>状态</th>"), 6)
        self.assertNotIn("<th>区服</th>", empty)
        full = template.render(name="测试", list=[{"name": "出售期", "list": [
            {"date": "2026-09-19", "server": "唯我独尊", "value": 999, "zone": "不能出现"},
        ]}])
        self.assertIn("999 元", full)
        self.assertNotIn("不能出现", full)


if __name__ == "__main__":
    unittest.main()
