"""功能开关目录：定义可启用的功能分组、每个指令的归属，以及逐条指令开关。

这份目录同时服务三处：

1. ``main.py`` 的 ``ini_command_map``：按逐条指令开关决定注册哪些指令；
2. ``core/webui.py``：把目录与当前开关状态提供给管理页的「功能开关」页；
3. ``tests/test_features.py``：校验每个指令都有归属、分组之间不重叠。

新增指令时，除了在 ``ini_command_map`` 注册，也要把它加进下面某个分组
（或 ``ALWAYS_ON_COMMANDS``），否则 ``tests/test_features.py`` 会失败。
"""

from __future__ import annotations

from typing import Any, Mapping

# 始终注册的元指令与会话设置，不受功能开关影响。
ALWAYS_ON_COMMANDS: frozenset[str] = frozenset(
    {
        "功能",
        "绑定区服",
        "解绑区服",
    }
)

# 管理页按 JX3API 官方一级分类展示；本地能力单独放在最后。
FEATURE_SECTION_ORDER: tuple[str, ...] = (
    "activity",
    "ranking",
    "trade",
    "battle",
    "role",
    "community",
    "tools",
    "dungeon",
    "local",
)

FEATURE_SECTIONS: dict[str, dict[str, str]] = {
    "activity": {
        "name": "活动情报",
        "description": "活动日历、世界首领、赤兔、烟花与马场。",
    },
    "ranking": {
        "name": "排行榜单",
        "description": "名剑、综合榜单、试炼与资历。",
    },
    "trade": {
        "name": "物价交易",
        "description": "阵营竞拍、的卢拍卖与物品行情。",
    },
    "battle": {
        "name": "阵营战场",
        "description": "帮战记录、阵营沙盘与诛恶事件。",
    },
    "role": {
        "name": "角色查询",
        "description": "角色资料、名片、奇遇、百战与心法配装。",
    },
    "community": {
        "name": "游戏社区",
        "description": "聊天、家园、师徒、资讯、招募、骚话与贴吧。",
    },
    "tools": {
        "name": "系统工具",
        "description": "科举、大区状态与技改记录。",
    },
    "dungeon": {
        "name": "副本秘境",
        "description": "秘境方位与掉落统计。",
    },
    "local": {
        "name": "本地增强",
        "description": "团队管理、避雷记录和实时事件推送等插件自有能力。",
    },
}

# 功能分组顺序即管理页卡片展示顺序。单个分组保持在 12 条以内，
# 避免某张卡片过高导致页面失衡；官方大类过大时按子标签拆分。
FEATURE_ORDER: tuple[str, ...] = (
    "activity_calendar",
    "activity_field",
    "ranking_arena",
    "ranking_general",
    "ranking_history",
    "trade",
    "battle",
    "role_profile",
    "role_card",
    "role_event",
    "role_baizhan",
    "role_kungfu",
    "community_interaction",
    "community_home",
    "community_news",
    "community_saohua",
    "community_tieba",
    "tools",
    "dungeon",
    "local_team_signup",
    "local_team_rules",
    "local_assist",
)

# 分组元信息：所属官方大类、展示名、说明、令牌消耗提示、默认开关。
FEATURE_INFO: dict[str, dict[str, Any]] = {
    "activity_calendar": {
        "section": "activity",
        "name": "日历与首领",
        "description": "活动日历、地图活动、世界首领与阵营事件。",
        "cost": "消耗 JX3API 次数",
        "default": True,
    },
    "activity_field": {
        "section": "activity",
        "name": "赤兔与马场",
        "description": "赤兔记录、烟花事件与马场动态。",
        "cost": "消耗 JX3API 次数",
        "default": True,
    },
    "ranking_arena": {
        "section": "ranking",
        "name": "名剑相关",
        "description": "名剑战绩、排行、统计与跨服榜单。",
        "cost": "消耗 JX3API 次数",
        "default": True,
    },
    "ranking_general": {
        "section": "ranking",
        "name": "综合榜单",
        "description": "武林争霸、捕快、江湖浪客、决斗与帮会阵营榜单。",
        "cost": "消耗 JX3API 次数",
        "default": True,
    },
    "ranking_history": {
        "section": "ranking",
        "name": "试炼与资历",
        "description": "试炼排行、资历分布与资历排行。",
        "cost": "消耗 JX3API 次数",
        "default": True,
    },
    "trade": {
        "section": "trade",
        "name": "拍卖与行情",
        "description": "阵营竞拍、的卢、金币、物品物价、成本与交易行。",
        "cost": "含 JX3BOX 行情查询",
        "default": True,
    },
    "battle": {
        "section": "battle",
        "name": "阵营战场",
        "description": "帮战记录、阵营沙盘与诛恶事件。",
        "cost": "消耗 JX3API 次数",
        "default": True,
    },
    "role_profile": {
        "section": "role",
        "name": "角色资料",
        "description": "角色详情、成就、属性面板与装备记录。",
        "cost": "消耗 JX3API 次数",
        "default": True,
    },
    "role_card": {
        "section": "role",
        "name": "角色名片",
        "description": "当前名片、全部名片与随机名片。",
        "cost": "消耗 JX3API 次数",
        "default": True,
    },
    "role_event": {
        "section": "role",
        "name": "奇遇相关",
        "description": "角色奇遇、未触发、汇总、近期、统计与攻略。",
        "cost": "含 JX3BOX 攻略",
        "default": True,
    },
    "role_baizhan": {
        "section": "role",
        "name": "百战记录",
        "description": "角色百战精耐与每周百战首领。",
        "cost": "消耗 JX3API 次数",
        "default": True,
    },
    "role_kungfu": {
        "section": "role",
        "name": "心法配装",
        "description": "阵眼、配装、技能、奇穴与宏。",
        "cost": "含 JX3BOX 配装与宏",
        "default": True,
    },
    "community_interaction": {
        "section": "community",
        "name": "互动与防骗",
        "description": "聊天记录、多玩语音、小吃小药与骗子查询。",
        "cost": "消耗 JX3API 次数",
        "default": True,
    },
    "community_home": {
        "section": "community",
        "name": "家园与师徒",
        "description": "家园鲜花、装饰、器物，以及拜师和收徒。",
        "cost": "消耗 JX3API 次数",
        "default": True,
    },
    "community_news": {
        "section": "community",
        "name": "资讯与招募",
        "description": "维护、新闻，以及团队招募、团长和团牌。",
        "cost": "消耗 JX3API 次数",
        "default": True,
    },
    "community_saohua": {
        "section": "community",
        "name": "骚话语录",
        "description": "答案之书、语录、吃喝选择与随机骚话。",
        "cost": "消耗 JX3API 次数",
        "default": True,
    },
    "community_tieba": {
        "section": "community",
        "name": "百度贴吧",
        "description": "贴吧物价与 818 随机内容。",
        "cost": "消耗 JX3API 次数",
        "default": True,
    },
    "tools": {
        "section": "tools",
        "name": "系统工具",
        "description": "科举答案、大区状态、开服状态与技改记录。",
        "cost": "消耗 JX3API 次数",
        "default": True,
    },
    "dungeon": {
        "section": "dungeon",
        "name": "副本秘境",
        "description": "秘境方位解密与物品掉落统计。",
        "cost": "消耗 JX3API 次数",
        "default": True,
    },
    "local_team_signup": {
        "section": "local",
        "name": "团队报名",
        "description": "开团、报名、成员调整与团队黑本。",
        "cost": "不消耗 JX3API 次数",
        "default": True,
    },
    "local_team_rules": {
        "section": "local",
        "name": "团队规则",
        "description": "团队收尾、团队黑本、清空报名以及报名限制规则。",
        "cost": "不消耗 JX3API 次数",
        "default": True,
    },
    "local_assist": {
        "section": "local",
        "name": "避雷与推送",
        "description": "按会话隔离的避雷名单，以及实时事件推送配置。",
        "cost": "避雷本地运行；推送需令牌",
        "default": True,
    },
}

# 每个分组包含的指令名（不含元指令与会话设置）。
FEATURE_COMMANDS: dict[str, frozenset[str]] = {
    "activity_calendar": frozenset(
        {
            "日常",
            "日常预测",
            "穹野卫",
            "披风会",
            "云从社",
            "楚天社",
            "关隘",
            "阵营奉献",
        }
    ),
    "activity_field": frozenset(
        {
            "赤兔",
            "本周赤兔",
            "烟花",
            "刷马",
            "马场",
        }
    ),
    "ranking_arena": frozenset(
        {
            "战绩",
            "名剑排行",
            "名剑统计",
            "跨服名剑",
        }
    ),
    "ranking_general": frozenset(
        {
            "武林争霸",
            "捕快荣誉",
            "江湖浪客",
            "决斗挑战",
            "帮会排行",
            "阵营排行",
            "其他排行",
        }
    ),
    "ranking_history": frozenset(
        {
            "试炼排行",
            "资历",
            "资历排行",
        }
    ),
    "trade": frozenset(
        {
            "阵营拍卖",
            "的卢",
            "金价",
            "物价",
            "成本",
            "看号",
            "交易行",
        }
    ),
    "battle": frozenset(
        {
            "帮战",
            "沙盘",
            "诛恶",
        }
    ),
    "role_profile": frozenset(
        {
            "角色",
            "成就",
            "属性",
            "装备",
        }
    ),
    "role_card": frozenset(
        {
            "名片",
            "全名片",
            "随机秀",
        }
    ),
    "role_event": frozenset(
        {
            "奇遇",
            "查询",
            "未出",
            "汇总",
            "近期",
            "统计",
            "攻略",
        }
    ),
    "role_baizhan": frozenset(
        {
            "精耐",
            "百战",
        }
    ),
    "role_kungfu": frozenset(
        {
            "阵眼",
            "配装",
            "技能",
            "奇穴",
            "宏",
        }
    ),
    "community_interaction": frozenset(
        {
            "发言",
            "统战",
            "小药",
            "骗子",
        }
    ),
    "community_home": frozenset(
        {
            "花价",
            "装饰",
            "器物",
            "拜师",
            "收徒",
        }
    ),
    "community_news": frozenset(
        {
            "维护",
            "新闻",
            "招募",
            "团长",
            "团牌",
        }
    ),
    "community_saohua": frozenset(
        {
            "答案之书",
            "舔狗语录",
            "疯狂星期四",
            "彩虹屁",
            "毒鸡汤",
            "朋友圈",
            "喝什么",
            "吃什么",
            "骚话",
            "渣男语录",
        }
    ),
    "community_tieba": frozenset(
        {
            "贴吧物价",
            "818",
        }
    ),
    "tools": frozenset(
        {
            "科举",
            "区服",
            "开服",
            "技改",
        }
    ),
    "dungeon": frozenset(
        {
            "解密",
            "掉落",
        }
    ),
    "local_team_signup": frozenset(
        {
            "开团",
            "打开报名",
            "关闭报名",
            "关闭报警",
            "报名",
            "取消报名",
            "查看团队",
            "修改报名",
            "交换位置",
        }
    ),
    "local_team_rules": frozenset(
        {
            "结束团队",
            "结束全部团队",
            "清空报名",
            "团队黑本",
            "查看限制",
            "添加限制",
            "修改限制",
            "删除限制",
            "恢复默认限制",
        }
    ),
    "local_assist": frozenset(
        {
            "避雷添加",
            "避雷查看",
            "避雷查询",
            "避雷修改",
            "避雷删除",
            "事件推送",
        }
    ),
}


def command_defaults() -> dict[str, bool]:
    """返回每条指令的默认开关状态（全部开启）。"""
    return {
        command: True
        for key in FEATURE_ORDER
        for command in FEATURE_COMMANDS[key]
    }


def resolve_enabled(config: Mapping[str, Any] | None) -> dict[str, bool]:
    """把用户配置归一成「指令名 -> 是否启用」的完整状态。

    配置格式为 ``{分组: {指令名: bool}}``；缺失或非布尔的分组 / 指令
    回退到默认开启，保证升级旧配置后行为稳定。
    """
    resolved = command_defaults()
    if isinstance(config, Mapping):
        # 兼容按旧分组保存的配置：先按指令名迁移，再让新分组值覆盖。
        for key, group in config.items():
            if key in FEATURE_ORDER or not isinstance(group, Mapping):
                continue
            for command in resolved:
                value = group.get(command)
                if isinstance(value, bool):
                    resolved[command] = value
        for key in FEATURE_ORDER:
            group = config.get(key)
            if not isinstance(group, Mapping):
                continue
            for command in FEATURE_COMMANDS[key]:
                value = group.get(command)
                if isinstance(value, bool):
                    resolved[command] = value
    return resolved


def command_feature(command: str) -> str | None:
    """返回指令所属分组；元指令返回 ``None``。"""
    for key in FEATURE_ORDER:
        if command in FEATURE_COMMANDS[key]:
            return key
    return None


def command_enabled(command: str, enabled: Mapping[str, bool]) -> bool:
    """判断某条指令在当前开关下是否应注册。"""
    if command in ALWAYS_ON_COMMANDS:
        return True
    if command_feature(command) is None:
        # 未归类的指令按始终启用处理，避免误伤；test_features 会提醒补录。
        return True
    return bool(enabled.get(command, True))


def describe(enabled: Mapping[str, bool] | None = None) -> list[dict[str, Any]]:
    """输出供管理页渲染的分组列表（含每条指令的开关状态）。"""
    resolved = command_defaults()
    if isinstance(enabled, Mapping):
        for command in resolved:
            value = enabled.get(command)
            if isinstance(value, bool):
                resolved[command] = value
    items: list[dict[str, Any]] = []
    for key in FEATURE_ORDER:
        info = FEATURE_INFO[key]
        section_key = info["section"]
        section = FEATURE_SECTIONS[section_key]
        commands = [
            {"name": command, "enabled": bool(resolved.get(command, True))}
            for command in sorted(FEATURE_COMMANDS[key])
        ]
        enabled_count = sum(1 for item in commands if item["enabled"])
        items.append(
            {
                "key": key,
                "section": section_key,
                "section_name": section["name"],
                "section_description": section["description"],
                "name": info["name"],
                "description": info["description"],
                "cost": info["cost"],
                "default": bool(info["default"]),
                "commands": commands,
                "enabled_count": enabled_count,
                "total_count": len(commands),
            }
        )
    return items
