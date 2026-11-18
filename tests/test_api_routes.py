"""JX3API 请求域名与接口路径回归测试。"""

import types
import unittest
from unittest.mock import AsyncMock, Mock, patch

host = types.ModuleType("astrbot")
host.logger = Mock()
api = types.ModuleType("astrbot.api")
api.logger = host.logger
api.AstrBotConfig = dict
with patch.dict(
    "sys.modules",
    {
        "astrbot": host,
        "astrbot.api": api,
        "astrbot.api.message_components": types.ModuleType(
            "astrbot.api.message_components"
        ),
    },
):
    from core.jx3api_data import JX3APIService, ROLE_RANK_NAMES
    from core.request import APIClient, APIErrorResponse
    from core.server_binding import ServerBindingService


class ApiRouteTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.service = JX3APIService({"jx3api_token": "test-token"}, None)
        self.api_get = AsyncMock(return_value={})
        self.service._api.get = self.api_get

    async def asyncTearDown(self):
        await self.service.close()

    def assert_request_path(self, expected: str):
        self.assertEqual(
            self.api_get.await_args.args, (f"https://www.jx3api.com{expected}",)
        )

    async def test_renamed_rank_endpoints(self):
        await self.service.kuafumingjian("梦江南", 1)
        self.assert_request_path("/rank/ladder")

        await self.service.wulinzhengba("梦江南", 1)
        self.assert_request_path("/rank/contest")

        await self.service.rank_statistical("名士五十强", "梦江南")
        self.assert_request_path("/rank/records")

        for name in ("浩气神兵宝甲五十强", "赛季恶人五十强", "上周浩气五十强"):
            with self.subTest(name=name):
                await self.service.rank_statistical(name, "梦江南")
                self.assert_request_path("/rank/guild")

    async def test_jianghu_ranks_share_new_endpoint(self):
        await self.service.bukairongyu("梦江南")
        self.assert_request_path("/rank/jianghu")
        self.assertEqual(
            self.api_get.await_args.kwargs["params"]["name"],
            "捕快荣誉榜",
        )

        await self.service.jianghulangke("梦江南")
        self.assert_request_path("/rank/jianghu")
        self.assertEqual(
            self.api_get.await_args.kwargs["params"]["name"],
            "江湖浪客榜",
        )

    async def test_trial_rank_uses_kungfu_parameter(self):
        await self.service.shilianpaixing("毒经·悟", "梦江南")
        self.assert_request_path("/rank/trials")
        params = self.api_get.await_args.kwargs["params"]
        self.assertEqual(params["kungfu"], "毒经·悟")
        self.assertNotIn("name", params)

    async def test_rank_label_field_is_used(self):
        self.api_get.return_value = {
            "label": "测试榜单",
            "data": [{"szCorpsName": "测试队伍", "nCorpsLevel": 2000}],
        }
        result = await self.service.kuafumingjian("梦江南", 1)
        self.assertEqual(result["data"]["name"], "跨服名剑 · 测试榜单")

        self.api_get.return_value = [
            {
                "label": "测试榜单",
                "server": "梦江南",
                "time": 1794920744,
                "data": [{"szName": "测试角色", "dwForceID": 1}],
            }
        ]
        result = await self.service.jianghulangke("梦江南")
        self.assertEqual(result["data"]["name"], "测试榜单")

        self.api_get.return_value = {
            "label": "测试榜单",
            "data": [{"1": "测试角色", "2": 10, "3": 30000, "4": 21000}],
        }
        result = await self.service.shilianpaixing("毒经·悟", "梦江南")
        self.assertEqual(result["data"]["name"], "测试榜单")

    async def test_personal_rank_selects_server_and_maps_fields(self):
        self.api_get.return_value = [
            {
                "data": [
                    {
                        "nLevel": 50,
                        "nScore": 214850,
                        "szCampName": "浩气盟",
                        "szForceName": "五毒",
                        "szName": "花骨容",
                        "szTongName": "国色",
                    }
                ],
                "label": "老江湖五十强",
                "server": "天鹅坪",
                "time": 1794919037,
                "zone": "双线区",
            },
            {
                "data": [],
                "label": "老江湖五十强",
                "server": "眉间雪",
                "time": 1794919157,
                "zone": "无界区",
            },
        ]
        result = await self.service.rank_statistical("老江湖五十强", "天鹅坪")
        self.assertEqual(result["code"], 200)
        self.assertEqual(result["data"]["server"], "天鹅坪")
        self.assertEqual(result["data"]["rank_name"], "老江湖五十强")
        self.assertEqual(len(result["data"]["items"]), 1)
        item = result["data"]["items"][0]
        self.assertEqual(item["name"], "花骨容")
        self.assertEqual(item["forceName"], "五毒")
        self.assertEqual(item["campName"], "浩气盟")
        self.assertEqual(item["tongName"], "国色")
        self.assertEqual(item["level"], 50)
        self.assertEqual(item["totalScore"], 214850)

    async def test_duel_rank_maps_short_fields(self):
        self.api_get.return_value = {
            "data": [
                {
                    "dwForceID": 6,
                    "dwMapID": 0,
                    "dwTongID": 0,
                    "nMoney": 3000,
                    "nRank": 1,
                    "nRoleType": 2,
                    "nTimeOut": 1795521837,
                    "szName": "芊苒",
                    "szPayerName": "",
                    "szTongName": "",
                },
                {
                    "dwForceID": 213,
                    "dwMapID": 108,
                    "dwTongID": 0,
                    "nMoney": 3000,
                    "nRank": 3,
                    "nRoleType": 1,
                    "nTimeOut": 1795178111,
                    "szName": "孤星",
                    "szPayerName": "某人",
                    "szTongName": "某帮",
                },
            ],
            "label": "公开",
            "server": "梦江南",
            "time": 1794920744,
            "zone": "电信区",
        }
        result = await self.service.juedoutiaozhan("梦江南", 1)
        self.assertEqual(result["code"], 200)
        self.assertEqual(result["data"]["name"], "决斗挑战榜")
        self.assertEqual(result["data"]["server"], "梦江南")
        self.assertEqual(result["data"]["mode_name"], "公开")
        self.assertEqual(result["data"]["items"][0]["name"], "芊苒")
        self.assertEqual(result["data"]["items"][0]["forceName"], "五毒")
        self.assertEqual(result["data"]["items"][0]["money"], 3000)
        self.assertEqual(result["data"]["items"][1]["forceName"], "刀宗")
        self.assertEqual(result["data"]["items"][1]["payerName"], "某人")

    async def test_jianghu_rank_maps_grouped_short_fields(self):
        self.api_get.return_value = [
            {
                "data": [
                    {
                        "dwCustomValue0": 0,
                        "dwForceID": 4,
                        "eCamp": 2,
                        "nRank": 1,
                        "nRoleType": 2,
                        "nScore": 65536,
                        "szName": "叶不约",
                        "szTongName": "",
                    },
                    {
                        "dwCustomValue0": 35,
                        "dwForceID": 10,
                        "eCamp": 2,
                        "nRank": 2,
                        "nRoleType": 1,
                        "nScore": 600,
                        "szName": "暗鲨",
                        "szTongName": "执念",
                    },
                ],
                "label": "江湖浪客榜",
                "server": "天鹅坪",
                "time": 1794921400,
                "zone": "双线区",
            }
        ]
        result = await self.service.jianghulangke("天鹅坪")
        self.assertEqual(result["code"], 200)
        self.assertEqual(result["data"]["name"], "江湖浪客榜")
        self.assertEqual(result["data"]["server"], "天鹅坪")
        first = result["data"]["items"][0]
        self.assertEqual(first["name"], "叶不约")
        self.assertEqual(first["forceName"], "纯阳")
        self.assertEqual(first["campName"], "恶人谷")
        self.assertEqual(first["score"], 65536)
        self.assertEqual(first["customValue0"], 0)
        second = result["data"]["items"][1]
        self.assertEqual(second["forceName"], "明教")
        self.assertEqual(second["tongName"], "执念")
        self.assertEqual(second["customValue0"], 35)

    async def test_contest_rank_maps_grouped_short_fields(self):
        def group(server: str, time: int) -> dict:
            return {
                "data": [
                    {
                        "dwCenterID": 14,
                        "dwTongID": 42431,
                        "eCamp": 1,
                        "nLastMatchTime": 975,
                        "nLose": 0,
                        "nRank": 1,
                        "nScore": 10,
                        "nWin": 2,
                        "szMasterName": "涟漪",
                        "szTongName": "檐月",
                    },
                    {
                        "dwCenterID": 24,
                        "dwTongID": 7437,
                        "eCamp": 1,
                        "nLastMatchTime": 1053,
                        "nLose": 1,
                        "nRank": 2,
                        "nScore": 8,
                        "nWin": 1,
                        "szMasterName": "哥哥",
                        "szTongName": "有匪",
                    },
                ],
                "label": "浩气盟排行榜",
                "server": server,
                "time": time,
                "zone": "电信区",
            }

        self.api_get.return_value = [
            group("乾坤一掷", 1794923474),
            group("唯我独尊", 1794923698),
        ]
        result = await self.service.wulinzhengba("唯我独尊", 1)
        self.assertEqual(result["code"], 200)
        self.assertEqual(result["data"]["name"], "浩气盟排行榜")
        self.assertEqual(result["data"]["server"], "唯我独尊")
        self.assertEqual(result["data"]["zone"], "电信区")

        first = result["data"]["items"][0]
        self.assertEqual(first["tongName"], "檐月")
        self.assertEqual(first["masterName"], "涟漪")
        self.assertEqual(first["serverName"], "唯我独尊")
        self.assertEqual(first["campName"], "浩气盟")
        self.assertEqual(first["winCount"], 2)
        self.assertEqual(first["loseCount"], 0)
        self.assertEqual(first["totalScore"], 10)
        self.assertEqual(first["lastMatchTimeText"], "16分15秒")

        second = result["data"]["items"][1]
        self.assertEqual(second["loseCount"], 1)
        self.assertEqual(second["totalScore"], 8)

    async def test_ladder_rank_maps_short_fields(self):
        self.api_get.return_value = {
            "data": [
                {
                    "dwCenterID": 0,
                    "dwCorpsID": 384011,
                    "dwMobileSeasonTotalCount": 0,
                    "dwMobileSeasonWinCount": 0,
                    "dwSeasonLoseCount": 7,
                    "dwSeasonTotalCount": 107,
                    "dwSeasonWinCount": 100,
                    "nCorpsLevel": 2669,
                    "nRank": 1,
                    "szCorpsName": "爱米休",
                },
                {
                    "dwCenterID": 0,
                    "dwCorpsID": 348722,
                    "dwMobileSeasonTotalCount": 75,
                    "dwMobileSeasonWinCount": 64,
                    "dwSeasonLoseCount": 11,
                    "dwSeasonTotalCount": 75,
                    "dwSeasonWinCount": 64,
                    "nCorpsLevel": 2372,
                    "nRank": 2,
                    "szCorpsName": "师门冲冲冲",
                },
            ],
            "label": "3v3排名",
            "server": "梦江南",
            "time": 1794924924,
            "zone": "电信区",
        }
        result = await self.service.kuafumingjian("梦江南", 1)
        self.assertEqual(result["code"], 200)
        self.assertEqual(result["data"]["name"], "跨服名剑 · 3v3排名")
        self.assertEqual(result["data"]["server"], "梦江南")
        self.assertEqual(result["data"]["zone"], "电信区")

        first = result["data"]["items"][0]
        self.assertEqual(first["corpsName"], "爱米休")
        self.assertEqual(first["corpsLevel"], 2669)
        self.assertEqual(first["seasonWinCount"], 100)
        self.assertEqual(first["seasonLoseCount"], 7)
        self.assertEqual(first["seasonTotalCount"], 107)

        second = result["data"]["items"][1]
        self.assertEqual(second["corpsName"], "师门冲冲冲")
        self.assertEqual(second["mobileSeasonWinCount"], 64)
        self.assertEqual(second["mobileSeasonTotalCount"], 75)

        self.api_get.return_value = {"label": "3v3排名", "data": []}
        result = await self.service.kuafumingjian("梦江南", 1)
        self.assertEqual(result["code"], 0)
        self.assertEqual(result["msg"], "未查询到榜单数据")
        self.assertEqual(result["data"], {})
        self.assertEqual(result["temp"], "")

    async def test_trial_rank_maps_positional_fields(self):
        self.api_get.return_value = [
            {
                "data": [
                    {"1": "柠檬七喜", "2": 10, "3": 32900, "4": 21413},
                    {"1": "懒羊羊@幽月轮", "2": 9, "3": 32050, "4": 22720},
                ],
                "label": "藏剑",
                "server": "梦江南",
                "time": 1794922487,
                "zone": "电信区",
            }
        ]
        result = await self.service.shilianpaixing("藏剑", "梦江南")
        self.assertEqual(result["code"], 200)
        self.assertEqual(result["data"]["name"], "藏剑")
        self.assertEqual(result["data"]["server"], "梦江南")
        self.assertEqual(result["data"]["zone"], "电信区")

        first = result["data"]["items"][0]
        self.assertEqual(first["roleName"], "柠檬七喜")
        self.assertEqual(first["maxLevel"], 10)
        self.assertEqual(first["totalScore"], 32900)
        self.assertEqual(first["equipScore"], 21413)
        self.assertEqual(result["data"]["items"][1]["maxLevel"], 9)

    async def test_castle_rank_maps_short_fields(self):
        def group(server: str, time: int) -> dict:
            return {
                "data": [
                    {
                        "byForceID": 215,
                        "byLevel": 50,
                        "nContribution": 109511,
                        "szName": "慕鸯",
                        "szTongName": "醉酒持剑",
                    },
                    {
                        "byForceID": 7,
                        "byLevel": 50,
                        "nContribution": 70,
                        "szName": "绝天风",
                        "szTongName": "南柯异梦",
                    },
                ],
                "label": "不空关",
                "server": server,
                "time": time,
                "zone": "电信区",
            }

        self.api_get.return_value = [
            group("乾坤一掷", 1794922554),
            group("梦江南", 1794922560),
        ]
        result = await self.service.judiangongxian("梦江南", "不空关")
        self.assert_request_path("/rank/castle")
        self.assertEqual(self.api_get.await_args.kwargs["params"]["name"], "不空关")
        self.assertEqual(result["code"], 200)
        self.assertEqual(result["data"]["name"], "不空关贡献榜")
        self.assertEqual(result["data"]["server"], "梦江南")

        first = result["data"]["items"][0]
        self.assertEqual(first["name"], "慕鸯")
        self.assertEqual(first["tongName"], "醉酒持剑")
        self.assertEqual(first["forceName"], "段氏")
        self.assertEqual(first["contribution"], 109511)
        self.assertEqual(result["data"]["items"][1]["forceName"], "唐门")

    async def test_battle_rank_maps_short_fields_and_limits_rows(self):
        items = [
            {
                "AVRG_EQUIP_SCORE": 21650,
                "BATTLE_ROUNDS": 30,
                "MATCH_LEVEL": 1855,
                "SUM_KILL_COUNT": 231,
                "TOP_COUNT": 27,
                "byForceID": 212,
                "nRank": index + 1,
                "szName": f"角色{index + 1}",
                "szTongName": "帮会",
            }
            for index in range(60)
        ]
        self.api_get.return_value = {
            "data": items,
            "label": "瀚海兵甲榜",
            "server": "梦江南",
            "time": 1794915114,
            "zone": "电信区",
        }
        result = await self.service.juejingzhanchang("梦江南", "瀚海兵甲榜")
        self.assert_request_path("/rank/battle")
        self.assertEqual(result["code"], 200)
        self.assertEqual(result["data"]["name"], "瀚海兵甲榜")
        self.assertEqual(len(result["data"]["items"]), 50)

        first = result["data"]["items"][0]
        self.assertEqual(first["name"], "角色1")
        self.assertEqual(first["forceName"], "药宗")
        self.assertEqual(first["matchLevel"], 1855)
        self.assertEqual(first["rounds"], 30)
        self.assertEqual(first["topCount"], 27)
        self.assertEqual(first["sumKill"], 231)
        self.assertEqual(first["avgEquipScore"], 21650)

    async def test_rank_menus_cover_every_option(self):
        self.assertEqual(
            set((await self.service.geren_rank_menu()).values()),
            set(ROLE_RANK_NAMES),
        )
        castle_menu = await self.service.judiangongxian_menu()
        self.assertEqual(len(castle_menu), 26)
        self.assertEqual(castle_menu["1"], "不空关")
        battle_menu = await self.service.juejingzhanchang_menu()
        self.assertEqual(len(battle_menu), 7)
        self.assertEqual(battle_menu["1"], "绝境名士录")

    async def test_rank_selects_reject_unknown_options(self):
        for select, label in (
            (self.service.rank_statistical_select, "排行榜"),
            (self.service.judiangongxian_select, "据点"),
            (self.service.juejingzhanchang_select, "榜单"),
        ):
            with self.subTest(label=label):
                result = await select("梦江南", {"1": "不存在的榜单"})
                self.assertEqual(result["code"], 0)
                self.assertEqual(result["msg"], f"无效{label}选项")

    async def test_rank_select_routes_every_menu_kind(self):
        cases = (
            ("浩气神兵宝甲五十强", "/rank/guild", {"szTongName": "测试帮会"}),
            ("赛季恶人五十强", "/rank/guild", {"szTongName": "测试帮会"}),
            ("本周恶人一百强", "/rank/records", {"szName": "测试角色"}),
        )
        for name, path, item in cases:
            with self.subTest(name=name):
                self.api_get.return_value = {
                    "label": name,
                    "server": "梦江南",
                    "data": [item],
                }
                result = await self.service.rank_statistical_select(
                    "梦江南", {"1": name}
                )
                self.assert_request_path(path)
                self.assertEqual(self.api_get.await_args.kwargs["params"]["name"], name)
                self.assertEqual(result["code"], 200)
                self.assertEqual(result["data"]["rank_name"], name)

    async def test_renamed_voice_and_choice_endpoints(self):
        await self.service.tongzhanyy("梦江南")
        self.assert_request_path("/voice/channels")

        await self.service.daanzhishu()
        self.assert_request_path("/choice/answer")

        await self.service.heshengme()
        self.assert_request_path("/choice/drink")

        await self.service.chishengme()
        self.assert_request_path("/choice/food")

    async def test_random_post_endpoint_is_unchanged(self):
        await self.service.bagua(818, "梦江南", 10)
        self.assert_request_path("/tieba/random")

    async def test_dunchong_uses_share_stay_endpoint(self):
        self.api_get.return_value = [
            {
                "name": "蟹相",
                "server": "梦江南",
                "time": 1794986614,
                "data": {
                    "map_name": "枫华谷",
                    "npc_name": "一本书",
                    "min_time": 2,
                    "max_time": 3,
                },
            }
        ]
        result = await self.service.dunchong("梦江南")
        self.assert_request_path("/share/stay")
        self.assertEqual(
            self.api_get.await_args.kwargs["params"],
            {"server": "梦江南", "token": "test-token"},
        )
        item = result["data"]["items"][0]
        self.assertEqual(item["name"], "蟹相")
        self.assertEqual(item["map_name"], "枫华谷")
        self.assertEqual(item["npc_name"], "一本书")
        self.assertTrue(item["time"])

    async def test_miaoshang_uses_trial_bosses_endpoint(self):
        self.api_get.return_value = {
            "season": "苍生铸世50级",
            "floor": 20,
            "hpGrowth": 0.101242,
            "bosses": [
                {
                    "boss": "雷神",
                    "group": "short",
                    "hp": 14230065,
                    "clearDps": 79056,
                    "perfectDps": 118584,
                    "note": None,
                }
            ],
        }
        result = await self.service.miaoshang(20)
        self.assert_request_path("/trial/bosses")
        self.assertEqual(
            self.api_get.await_args.kwargs["params"],
            {"floor": 20, "token": "test-token"},
        )
        data = result["data"]
        self.assertEqual(data["floor"], 20)
        self.assertEqual(data["hp_growth"], "10.12%")
        self.assertEqual(data["bosses"][0]["clear_dps"], "79,056")
        self.assertEqual(data["bosses"][0]["group"], "短轴")

    async def test_server_search_resolves_official_name(self):
        self.api_get.return_value = {"server": "乾坤一掷"}
        self.assertEqual(await self.service.server_search("华乾"), "乾坤一掷")
        self.assert_request_path("/server/search")
        self.assertEqual(
            self.api_get.await_args.kwargs["params"],
            {"server": "华乾", "token": "test-token"},
        )

    async def test_server_search_caches_missing_names(self):
        self.api_get.return_value = APIErrorResponse(400, "服务器名称不正确")
        self.assertIsNone(await self.service.server_search("不存在的区服"))
        self.assertIsNone(await self.service.server_search("不存在的区服"))
        self.api_get.assert_awaited_once()

    async def test_role_online_formats_standalone_result(self):
        self.service.ticket = "test-ticket"
        self.service._api.post = AsyncMock(
            return_value=[
                {
                    "serverName": "梦江南",
                    "roleName": "测试角色",
                    "onlineStatus": True,
                    "gameLogin": True,
                    "appLogin": False,
                }
            ]
        )

        result = await self.service.role_online("梦江南", "测试角色")

        self.assertEqual(result["code"], 200)
        self.assertIn("角色在线", result["data"])
        self.assertIn("区服：梦江南", result["data"])
        self.assertIn("在线状态：在线", result["data"])
        self.assertIn("游戏登录：已登录", result["data"])
        self.assertIn("推栏登录：未登录", result["data"])

    async def test_all_server_keywords_accept_quanqu_and_quanfu(self):
        binding = ServerBindingService(None)
        for keyword in ("全区", "全服"):
            with self.subTest(keyword=keyword):
                self.assertTrue(binding.is_all_servers_query(keyword))
        self.assertFalse(binding.is_all_servers_query("梦江南"))

    async def test_role_online_status_uses_post_with_header_token(self):
        self.service.ticket = "test-ticket"
        post = AsyncMock(
            return_value=[
                {
                    "onlineStatus": True,
                    "gameLogin": False,
                    "appLogin": True,
                }
            ]
        )
        self.service._api.post = post

        result = await self.service.role_online_status("梦江南", "测试角色")

        self.assertEqual(
            result,
            {"onlineStatus": True, "gameLogin": False, "appLogin": True},
        )
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
        self.assertEqual(post.await_args.kwargs["headers"], {"token": "test-token"})

    async def test_role_online_status_skips_without_ticket(self):
        post = AsyncMock()
        self.service._api.post = post

        self.assertIsNone(await self.service.role_online_status("梦江南", "测试角色"))
        post.assert_not_awaited()

    async def test_achievement_distribution_uses_role_achievement(self):
        await self.service.zili("梦江南", "测试角色", {"1": "总览"})
        self.assert_request_path("/role/achievement")
        params = self.api_get.await_args.kwargs["params"]
        self.assertNotIn("ticket", params)
        self.assertEqual(params["class"], 1)
        self.assertEqual(params["subclass"], "")

    async def test_school_queries_use_kungfu_parameter(self):
        queries = (
            (self.service.zhenyan, "/school/matrix"),
            (self.service.jineng, "/school/skills"),
            (self.service.qixue, "/school/talent"),
        )
        for method, path in queries:
            with self.subTest(method=method.__name__):
                await method("唐门")
                self.assert_request_path(path)
                params = self.api_get.await_args.kwargs["params"]
                self.assertEqual(params["kungfu"], "唐门")
                self.assertNotIn("name", params)
                self.assertNotIn("update", params)

    async def test_token_stats_uses_www_domain(self):
        post = AsyncMock(
            return_value={
                "valid": True,
                "level": 2,
                "used": 12,
                "remaining": 88,
            }
        )
        self.service._api.post = post
        result = await self.service.token_stats()
        self.assertEqual(
            post.await_args.args,
            ("https://www.jx3api.com/token/stats",),
        )
        self.assertEqual(
            result,
            {"level": 2, "used": 12, "remaining": 88, "valid": True},
        )

    async def test_token_stats_reports_business_error(self):
        self.service._api.post = AsyncMock(
            return_value=APIErrorResponse(code=401, message="token 无效")
        )
        self.assertIsNone(await self.service.token_stats())

    async def test_calendar_unwraps_status_detail_envelope(self):
        detail = {
            "date": "2026-11-19",
            "week": "四",
            "war": "大战！英雄大阳津",
            "battle": "西风古道",
            "orecar": "跨服·渝州",
            "school": "唐门·兄弟之争",
            "rescue": "万花·乱世",
            "lucky": ["饿饿", "瓜皮", "红绸"],
            "card": ["上阳宫·双曜亭", "上阳宫·观风殿", "英雄夕颜阁"],
            "weekly": {
                "conn": ["经首道源·越海珠贝", "侠客岛·雾岛寻丹"],
                "raid": ["洛阳之战", "敖龙岛", "一之窟"],
            },
        }

        class ExtractingClient:
            def __init__(self):
                self.client = APIClient()

            async def get(
                self,
                url,
                params=None,
                out_key=None,
                success_codes=None,
                return_error=False,
            ):
                return self.client._extract_data(
                    {"status": 200, "detail": detail},
                    out_key,
                    success_codes,
                    return_error,
                )

            async def close(self):
                await self.client.close()

        self.service._api = ExtractingClient()
        result = await self.service.richang("day", 0)
        self.assertEqual(result["code"], 200)
        self.assertIn("大战：大战！英雄大阳津", result["data"])
        self.assertIn("阵营：跨服·渝州", result["data"])
        self.assertIn("饿饿, 瓜皮, 红绸", result["data"])

    def test_extract_data_handles_status_envelope(self):
        client = APIClient()
        self.assertEqual(
            client._extract_data(
                {"status": 200, "detail": {"value": 1}},
                "data",
                (200, "200"),
            ),
            {"value": 1},
        )
        self.assertIsNone(
            client._extract_data(
                {"status": 500, "detail": "server error"},
                "data",
                (200, "200"),
            )
        )

    async def test_calendar_clamps_days_to_supported_range(self):
        await self.service.richang("day", 99)
        self.assertEqual(
            self.api_get.await_args.kwargs["params"],
            {"mode": "day", "num": 15},
        )
        await self.service.richang("list", -3)
        self.assertEqual(
            self.api_get.await_args.kwargs["params"],
            {"mode": "list", "num": 0},
        )


if __name__ == "__main__":
    unittest.main()
