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
    from core.api_catalog import API_CATALOG, API_CATEGORY_ORDER
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
            "/raid/records",
        }
        self.assertFalse(removed & endpoints)

    async def test_api_catalog_entries_are_complete(self):
        self.assertTrue(API_CATALOG)
        for endpoint, (title, category) in API_CATALOG.items():
            with self.subTest(endpoint=endpoint):
                self.assertTrue(title.strip())
                self.assertIn(category, API_CATEGORY_ORDER)

    async def test_dashboard_exposes_api_name_and_category(self):
        dashboard = await self.cache.dashboard()
        items = {item["name"]: item for item in dashboard["api"]}
        calendar = items["/active/calendar"]
        self.assertEqual(calendar["title"], "活动日历")
        self.assertEqual(calendar["category"], "活动情报")
        self.assertEqual(items["/rank/battle"]["category"], "排行榜单")
        self.assertTrue(all(item["title"] for item in dashboard["api"]))
        categories = [item["name"] for item in dashboard["api_categories"]]
        self.assertEqual(categories[0], "活动情报")
        self.assertIn("排行榜单", categories)
        self.assertEqual(
            sum(item["count"] for item in dashboard["api_categories"]),
            len(dashboard["api"]),
        )
        activity = [
            item["name"]
            for item in dashboard["api"]
            if item["category"] == "活动情报"
        ]
        self.assertEqual(
            activity,
            [
                "/active/calendar",
                "/active/celebs",
                "/ranch/records",
                "/ranch/chat",
                "/chitu/records",
                "/chitu/week/records",
                "/firework/records",
            ],
        )
        # 官网把 /school/seniority 归在心法配装，也就是“角色查询”大分类。
        self.assertEqual(items["/school/seniority"]["category"], "角色查询")

    async def test_renamed_endpoint_ttl_migrates(self):
        await self.cache.set_ttl("api", "/saohua/answer", 1234)
        await self.cache.initialize()
        await self.cache.stop()
        self.assertEqual(self.cache.get_ttl("api", "/choice/answer"), 1234)
        self.assertIsNone(
            await self.db.fetch_one(
                "SELECT * FROM cache_settings WHERE cache_name=?",
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

    async def test_removed_endpoint_settings_are_cleaned(self):
        await self.cache.set_ttl("api", "/castle/status", 1234)
        await self.cache.initialize()
        await self.cache.stop()
        self.assertIsNone(
            await self.db.fetch_one(
                "SELECT * FROM cache_settings WHERE cache_name=?",
                ("/castle/status",),
            )
        )

    async def test_legacy_ttl_migrates(self):
        for ttl in (0, 1234):
            with self.subTest(ttl=ttl):
                await self.cache.set_ttl("api", "/card/record", inherit=True)
                await self.cache.set_ttl("api", "/card/cached", ttl)
                await self.cache.initialize()
                await self.cache.stop()
                self.assertEqual(self.cache.get_ttl("api", "/card/record"), ttl)
                self.assertIsNone(
                    await self.db.fetch_one(
                        "SELECT * FROM cache_settings WHERE cache_name=?",
                        ("/card/cached",),
                    )
                )
                await self.cache.initialize()
                await self.cache.stop()
                self.assertEqual(self.cache.get_ttl("api", "/card/record"), ttl)

    async def test_empty_cached_payload_is_treated_as_miss(self):
        params = {"mode": "day", "num": 0}
        cache_key = self.cache.build_api_key("/active/calendar", params)
        self.cache._save_api_payload(
            cache_key, "/active/calendar", {}, 300
        )
        fetcher = AsyncMock(return_value={"date": "2026-11-19"})
        data, metadata = await self.cache.request_api(
            "/active/calendar", params, fetcher, bool
        )
        self.assertEqual(data, {"date": "2026-11-19"})
        self.assertFalse(metadata["hit"])
        fetcher.assert_awaited_once()

    async def test_api_cache_is_memory_only(self):
        self.cache._save_api_payload(
            "memory-key", "/active/calendar", {"date": "2026-11-19"}, 300
        )
        self.assertEqual(len(self.cache._memory), 1)
        legacy = await self.db.fetch_one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            ("api_response_cache",),
        )
        self.assertIsNone(legacy)
        limit_names = {
            str(row["limit_name"])
            for row in await self.db.fetch_all("SELECT limit_name FROM cache_limits")
        }
        self.assertNotIn("api_max_entries", limit_names)

    async def test_legacy_sqlite_api_cache_is_removed(self):
        await self.db.execute(
            """
            CREATE TABLE api_response_cache(
                cache_key TEXT PRIMARY KEY,
                endpoint TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                last_accessed_at INTEGER NOT NULL
            )
            """
        )
        await self.db.execute(
            "INSERT INTO api_response_cache VALUES(?, ?, ?, ?, ?, ?)",
            ("legacy-key", "/active/calendar", "{}", 1, 2, 3),
        )
        await self.db.execute(
            "INSERT INTO cache_limits(limit_name, limit_value) VALUES(?, ?)",
            ("api_max_entries", 256),
        )
        await self.cache.initialize()
        table = await self.db.fetch_one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            ("api_response_cache",),
        )
        self.assertIsNone(table)
        limit = await self.db.fetch_one(
            "SELECT * FROM cache_limits WHERE limit_name=?",
            ("api_max_entries",),
        )
        self.assertIsNone(limit)

    async def test_stop_clears_memory_cache(self):
        self.cache._save_api_payload(
            "memory-key", "/active/calendar", {"date": "2026-11-19"}, 300
        )
        self.assertTrue(self.cache._memory)
        await self.cache.stop()
        self.assertFalse(self.cache._memory)
        self.assertEqual(self.cache._memory_size_bytes, 0)
        fetcher = AsyncMock(return_value={"date": "2026-11-20"})
        data, metadata = await self.cache.request_api(
            "/active/calendar", {"mode": "day"}, fetcher, bool
        )
        self.assertEqual(data, {"date": "2026-11-20"})
        self.assertFalse(metadata["hit"])

    async def test_clear_item_only_removes_matching_endpoint(self):
        self.cache._save_api_payload("a", "/active/calendar", {"a": 1}, 300)
        self.cache._save_api_payload("b", "/rank/battle", {"b": 2}, 300)
        removed = await self.cache.clear_item("api", "/active/calendar")
        self.assertEqual(removed, 1)
        self.assertNotIn("a", self.cache._memory)
        self.assertIn("b", self.cache._memory)

    async def test_dashboard_stats_are_memory_based(self):
        self.cache._save_api_payload(
            "memory-key", "/active/calendar", {"date": "2026-11-19"}, 300
        )
        dashboard = await self.cache.dashboard()
        self.assertEqual(dashboard["stats"]["api_count"], 1)
        self.assertGreater(dashboard["stats"]["api_size_bytes"], 0)
        self.assertNotIn("api_entry_limit", dashboard["stats"])
        self.assertNotIn("api_max_entries", dashboard["limits"])

    async def test_set_limits_persists_memory_and_image_only(self):
        await self.cache.set_limits(8, 256)
        await self.cache.initialize()
        self.assertEqual(self.cache.max_memory_bytes, 8 * 1024 * 1024)
        self.assertEqual(self.cache.max_image_bytes, 256 * 1024 * 1024)
        limit_names = {
            str(row["limit_name"])
            for row in await self.db.fetch_all("SELECT limit_name FROM cache_limits")
        }
        self.assertEqual(limit_names, {"api_memory_max_mb", "image_max_mb"})

    async def test_image_cache_groups_commands_by_feature(self):
        self.cache.register_image_commands(
            {"战绩": "ranking", "属性": "role", "查看团队": "team"}
        )
        dashboard = await self.cache.dashboard()
        items = {item["name"]: item for item in dashboard["images"]}
        self.assertEqual(items["战绩"]["category"], "排行榜单")
        self.assertEqual(items["属性"]["category"], "角色查询")
        self.assertEqual(items["查看团队"]["category"], "团队功能")
        self.assertEqual(items["查看团队"]["ttl_seconds"], 0)
        self.assertTrue(items["查看团队"]["safe_default"])
        categories = [
            category["name"] for category in dashboard["image_categories"]
        ]
        self.assertEqual(categories, ["排行榜单", "角色查询", "团队功能"])
        self.assertEqual(
            sum(category["count"] for category in dashboard["image_categories"]),
            3,
        )

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
