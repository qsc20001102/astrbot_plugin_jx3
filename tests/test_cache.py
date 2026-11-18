import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from core.sqlite import AsyncSQLiteDB

with patch.dict(
    "sys.modules",
    {
        "astrbot": types.ModuleType("astrbot"),
        "astrbot.api": types.SimpleNamespace(logger=Mock()),
    },
):
    from core.cache import CacheService


class CardCacheTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = AsyncSQLiteDB(":memory:")
        await self.db.connect()
        self.cache = CacheService(self.db, Path(self.temp_dir.name) / "images")
        await self.cache.initialize()
        await self.cache.stop()

    async def asyncTearDown(self):
        await self.cache.stop()
        await self.db.close()
        self.temp_dir.cleanup()

    async def test_dashboard_lists_current_card_endpoints(self):
        dashboard = await self.cache.dashboard()
        endpoints = {item["name"] for item in dashboard["api"]}
        self.assertIn("/card/record", endpoints)
        self.assertIn("/card/records", endpoints)
        self.assertIn("/card/random", endpoints)
        self.assertIn("/role/online/status", endpoints)
        self.assertIn("/server/search", endpoints)
        self.assertIn("/share/stay", endpoints)
        self.assertIn("/trial/bosses", endpoints)
        self.assertEqual(self.cache.get_ttl("api", "/share/stay"), 300)
        self.assertEqual(self.cache.get_ttl("api", "/trial/bosses"), 300)
        self.assertNotIn("/card/cached", endpoints)
        self.assertEqual(self.cache.get_ttl("api", "/card/random"), 0)
        self.assertEqual(self.cache.get_ttl("api", "/role/online/status"), 300)
        self.assertEqual(self.cache.get_ttl("api", "/server/search"), 300)
        self.assertEqual(self.cache.get_ttl("image", "属性"), 0)
        self.assertEqual(self.cache.get_ttl("image", "装备"), 0)

    async def test_dashboard_lists_renamed_endpoints_only(self):
        dashboard = await self.cache.dashboard()
        endpoints = {item["name"] for item in dashboard["api"]}
        renamed = {
            "/voice/channels",
            "/rank/ladder",
            "/rank/contest",
            "/rank/guild",
            "/rank/jianghu",
            "/rank/records",
            "/choice/answer",
            "/choice/drink",
            "/choice/food",
            "/role/achievement",
        }
        retired = {
            "/duowan/statistics",
            "/rank/arena",
            "/rank/championship",
            "/rank/statistics",
            "/rank/constable",
            "/rank/outlaw",
            "/saohua/answer",
            "/saohua/drink",
            "/saohua/eat",
            "/tuilan/achievement",
        }
        self.assertTrue(renamed <= endpoints)
        self.assertFalse(retired & endpoints)
        removed = {
            "/castle/status",
            "/event/missing",
            "/fenxian/records",
            "/home/furniture",
            "/home/travel",
        }
        self.assertFalse(removed & endpoints)

    async def test_renamed_endpoint_ttl_and_payload_migrate(self):
        await self.cache.set_ttl("api", "/saohua/answer", 1234)
        await self.cache._save_api_payload(
            "old-choice", "/saohua/answer", {"answer": "old"}, 300
        )
        await self.cache.initialize()
        await self.cache.stop()
        self.assertEqual(self.cache.get_ttl("api", "/choice/answer"), 1234)
        self.assertIsNone(
            await self.db.fetch_one(
                "SELECT * FROM cache_settings WHERE cache_name=?",
                ("/saohua/answer",),
            )
        )
        self.assertIsNone(
            await self.db.fetch_one(
                "SELECT * FROM api_response_cache WHERE endpoint=?",
                ("/saohua/answer",),
            )
        )

    async def test_rank_jianghu_endpoint_ttl_migrates(self):
        for old_path in ("/rank/constable", "/rank/outlaw"):
            with self.subTest(old_path=old_path):
                await self.cache.set_ttl("api", old_path, 1234)
                await self.cache.initialize()
                await self.cache.stop()
                self.assertEqual(self.cache.get_ttl("api", "/rank/jianghu"), 1234)
                self.assertIsNone(
                    await self.db.fetch_one(
                        "SELECT * FROM cache_settings WHERE cache_name=?",
                        (old_path,),
                    )
                )

    async def test_achievement_endpoint_ttl_migrates(self):
        await self.cache.set_ttl("api", "/tuilan/achievement", 1234)
        await self.cache.initialize()
        await self.cache.stop()
        self.assertEqual(self.cache.get_ttl("api", "/role/achievement"), 1234)
        self.assertIsNone(
            await self.db.fetch_one(
                "SELECT * FROM cache_settings WHERE cache_name=?",
                ("/tuilan/achievement",),
            )
        )

    async def test_removed_endpoint_settings_and_cache_are_cleaned(self):
        await self.cache.set_ttl("api", "/castle/status", 1234)
        await self.cache._save_api_payload(
            "old-castle", "/castle/status", {"status": "old"}, 300
        )
        await self.cache.initialize()
        await self.cache.stop()
        self.assertIsNone(
            await self.db.fetch_one(
                "SELECT * FROM cache_settings WHERE cache_name=?",
                ("/castle/status",),
            )
        )
        self.assertIsNone(
            await self.db.fetch_one(
                "SELECT * FROM api_response_cache WHERE endpoint=?",
                ("/castle/status",),
            )
        )

    async def test_legacy_ttl_migrates_and_old_payload_is_discarded(self):
        for ttl in (0, 1234):
            with self.subTest(ttl=ttl):
                await self.cache.set_ttl("api", "/card/record", inherit=True)
                await self.cache.set_ttl("api", "/card/cached", ttl)
                await self.cache._save_api_payload(
                    "old-card", "/card/cached", {"showAvatar": "old-image"}, 300
                )
                await self.cache.initialize()
                await self.cache.stop()
                self.assertEqual(self.cache.get_ttl("api", "/card/record"), ttl)
                self.assertIsNone(
                    await self.db.fetch_one(
                        "SELECT * FROM cache_settings WHERE cache_name=?",
                        ("/card/cached",),
                    )
                )
                self.assertIsNone(
                    await self.db.fetch_one(
                        "SELECT * FROM api_response_cache WHERE endpoint=?",
                        ("/card/cached",),
                    )
                )
                await self.cache.initialize()
                await self.cache.stop()
                self.assertEqual(self.cache.get_ttl("api", "/card/record"), ttl)

    async def test_empty_cached_payload_is_treated_as_miss(self):
        params = {"mode": "day", "num": 0}
        cache_key = self.cache.build_api_key("/active/calendar", params)
        await self.cache._save_api_payload(
            cache_key, "/active/calendar", {}, 300
        )
        fetcher = AsyncMock(return_value={"date": "2026-11-19"})
        data, metadata = await self.cache.request_api(
            "/active/calendar", params, fetcher, bool
        )
        self.assertEqual(data, {"date": "2026-11-19"})
        self.assertFalse(metadata["hit"])
        fetcher.assert_awaited_once()

    async def test_explicit_new_ttl_wins_and_other_settings_survive(self):
        await self.cache.set_ttl("api", "/card/cached", 100)
        await self.cache.set_ttl("api", "/card/record", 200)
        await self.cache.set_ttl("api", "/card/records", 400)
        await self.cache.set_ttl("api", "*", 500)
        await self.cache.set_ttl("image", "/card/cached", 600)
        await self.cache.initialize()
        self.assertEqual(self.cache.get_ttl("api", "/card/record"), 200)
        self.assertEqual(self.cache.get_ttl("api", "/card/records"), 400)
        self.assertEqual(self.cache.get_ttl("api", "*"), 500)
        self.assertEqual(self.cache.get_ttl("image", "/card/cached"), 600)

    async def test_new_endpoint_hits_cache_then_respects_disabled_ttl(self):
        await self.cache.set_ttl("api", "/card/cached", 1200)
        await self.cache.initialize()
        fetcher = AsyncMock(return_value={"showAvatar": "new-image"})
        params = {"server": "test-server", "name": "test-role"}
        first, miss = await self.cache.request_api(
            "/card/record", params, fetcher, bool
        )
        second, hit = await self.cache.request_api(
            "/card/record", params, fetcher, bool
        )
        self.assertEqual(first, second)
        self.assertFalse(miss["hit"])
        self.assertTrue(hit["hit"])
        self.assertEqual(hit["ttl_seconds"], 1200)
        fetcher.assert_awaited_once()
        await self.cache.set_ttl("api", "/card/record", 0)
        for _ in range(2):
            _, metadata = await self.cache.request_api(
                "/card/record", params, fetcher, bool
            )
            self.assertFalse(metadata["hit"])
            self.assertEqual(metadata["ttl_seconds"], 0)
        self.assertEqual(fetcher.await_count, 3)


if __name__ == "__main__":
    unittest.main()
