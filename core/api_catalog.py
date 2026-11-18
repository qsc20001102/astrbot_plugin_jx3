"""JX3API 接口目录：接口名称与大分类。

接口名称取自 JX3API 官方文档（https://www.jx3api.com/）的接口摘要；
大分类沿用插件功能分类（``core/features.py`` 的 ``FEATURE_SECTIONS``），
与「功能开关」页保持同一套分类，便于对照。

这里只维护 JX3API 的 HTTP 接口；JX3BOX、本地数据等其他数据源
不经过 ``CacheService`` 的接口缓存，因此不在此登记。
"""

from __future__ import annotations

from .features import FEATURE_SECTIONS

# 大分类顺序：与功能开关页的分类顺序一致，只保留有 JX3API 接口的分类。
API_CATEGORY_ORDER: tuple[str, ...] = (
    "activity",
    "ranking",
    "trade",
    "battle",
    "role",
    "community",
    "tools",
    "dungeon",
)

# endpoint -> (接口名称, 大分类 key)
API_CATALOG: dict[str, tuple[str, str]] = {
    # 活动情报
    # 活动日历
    "/active/calendar": ("活动日历", "activity"),
    "/active/celebs": ("地图活动", "activity"),
    # 马场查询
    "/ranch/records": ("马场事件", "activity"),
    "/ranch/chat": ("马场预告", "activity"),
    # 赤兔查询
    "/chitu/records": ("今日赤兔", "activity"),
    "/chitu/week/records": ("本周赤兔", "activity"),
    # 烟花事件
    "/firework/records": ("烟花记录", "activity"),
    # 排行榜单
    # 名剑相关
    "/arena/awesome": ("名剑排行", "ranking"),
    "/arena/recent": ("名剑战绩", "ranking"),
    "/arena/schools": ("名剑统计", "ranking"),
    # 排行榜单
    "/rank/battle": ("绝境战场", "ranking"),
    "/rank/castle": ("据点贡献", "ranking"),
    "/rank/guild": ("帮会排行", "ranking"),
    "/rank/records": ("个人排行", "ranking"),
    "/rank/trials": ("试炼之地", "ranking"),
    "/rank/contest": ("武林争霸", "ranking"),
    "/rank/jianghu": ("江湖排行", "ranking"),
    "/rank/ladder": ("跨服名剑", "ranking"),
    "/rank/wanted": ("决斗挑战", "ranking"),
    # 资历分布
    "/role/achievement": ("资历分布", "ranking"),
    # 物价交易
    # 物价交易
    "/trade/demon": ("金价行情", "trade"),
    "/trade/records": ("物品价格", "trade"),
    "/trade/manufacture": ("成本计算", "trade"),
    "/trade/wanbaolou": ("编号搜索", "trade"),
    # 阵营竞拍
    "/auction/records": ("阵营拍卖", "trade"),
    # 的卢拍卖
    "/steed/records": ("的卢拍卖", "trade"),
    # 阵营战场
    # 帮战记录
    "/battle/records": ("帮战记录", "battle"),
    # 阵营沙盘
    "/sand/records": ("沙盘据点", "battle"),
    # 诛恶事件
    "/wicked/records": ("诛恶事件", "battle"),
    # 角色查询
    # 角色奇遇
    "/event/collect": ("奇遇汇总", "role"),
    "/event/recent": ("近期奇遇", "role"),
    "/event/records": ("奇遇记录", "role"),
    "/event/statistics": ("奇遇统计", "role"),
    # 角色信息
    "/role/detail": ("角色详情", "role"),
    "/role/online/status": ("角色在线状态", "role"),
    # 心法配装
    "/school/matrix": ("阵法列表", "role"),
    "/school/seniority": ("资历榜单", "role"),
    "/school/skills": ("技能列表", "role"),
    "/school/talent": ("奇穴列表", "role"),
    # 角色属性
    "/calcd/attribute": ("装备属性", "role"),
    "/calcd/detail": ("装备详情", "role"),
    "/calcd/records": ("装备历史", "role"),
    # 角色名片
    "/card/random": ("随机名片", "role"),
    "/card/record": ("名片记录", "role"),
    "/card/records": ("名片历史", "role"),
    # 百战记录
    "/monster/records": ("角色百战", "role"),
    "/monster/weekly": ("百战首领", "role"),
    # 蹲宠查询
    "/share/stay": ("蹲宠查询", "role"),
    # 游戏社区
    # 趣味选择
    "/choice/answer": ("答案之书", "community"),
    "/choice/drink": ("喝什么", "community"),
    "/choice/food": ("吃什么", "community"),
    # 小吃小药
    "/food/list": ("小吃小药", "community"),
    # 家园相关
    "/home/flower": ("家园鲜花", "community"),
    # 新闻公告
    "/news/announce": ("维护公告", "community"),
    "/news/records": ("新闻资讯", "community"),
    # 骚话语录
    "/saohua/content": ("舔狗日志", "community"),
    "/saohua/random": ("随机骚话", "community"),
    "/saohua/zhanan": ("渣男语录", "community"),
    "/saohua/context": ("分类语录", "community"),
    # 语音频道
    "/voice/channels": ("统战语音", "community"),
    # 骗子查询
    "/fraud/detail": ("骗子查询", "community"),
    # 师徒相关
    "/mentor/search": ("师徒列表", "community"),
    # 团队招募
    "/recruit/search": ("团队招募", "community"),
    # 百度贴吧
    "/tieba/item/records": ("外观记录", "community"),
    "/tieba/random": ("随机帖子", "community"),
    # 聊天记录
    "/chat/records": ("角色聊天", "community"),
    # 系统工具
    # 科举搜索
    "/exam/search": ("科举答案", "tools"),
    # 大区状态
    "/server/search": ("服务器搜索", "tools"),
    "/server/status/check": ("大区状态", "tools"),
    # 急速计算
    "/skill/rework": ("技改记录", "tools"),
    # 副本秘境
    # 秘境方位
    "/mech/decrypt": ("秘境方位", "dungeon"),
    # 掉落统计
    "/reward/statistics": ("掉落统计", "dungeon"),
    # 试炼之地
    "/trial/bosses": ("秒伤计算", "dungeon"),
}


def category_name(category_key: str) -> str:
    """返回大分类的展示名称；未知分类回退到 key。"""
    section = FEATURE_SECTIONS.get(category_key)
    return str(section.get("name") if section else category_key)
