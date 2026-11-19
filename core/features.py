"""功能开关目录：按 JX3API 官网一级分类划归指令，并提供逐条指令开关。

这份目录同时服务三处：

1. ``main.py`` 的 ``ini_command_map``：按逐条指令开关决定注册哪些指令；
2. ``core/webui.py``：把目录与当前开关状态提供给管理页的「功能开关」页；
3. ``tests/test_features.py``：校验每个指令都有归属、分类之间不重叠。

开关状态只在插件管理页配置，由 ``core/feature_settings.py`` 保存到本地 SQLite。
所有指令都归入下面的分类，并统一受功能开关控制；新增指令时除了在
``ini_command_map`` 注册，也要把它加进对应分类，否则
``tests/test_features.py`` 会失败。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# 分类顺序尽量与 JX3API 官网一致；“功能类”固定放在第一位。
FEATURE_SECTION_ORDER: tuple[str, ...] = (
    "functions",
    "activity",
    "ranking",
    "trade",
    "battle",
    "role",
    "community",
    "tools",
    "dungeon",
    "macro",
    "avoid",
    "team",
)

FEATURE_SECTIONS: dict[str, dict[str, str]] = {
    "functions": {
        "name": "功能类",
        "description": "功能帮助、区服绑定与事件推送等插件入口。",
    },
    "activity": {
        "name": "活动情报",
        "description": "活动日历、声望社、赤兔、马场与烟花。",
    },
    "ranking": {
        "name": "排行榜单",
        "description": "名剑战绩、跨服与个人/帮会榜单、试炼、资历、据点贡献与绝境战场。",
    },
    "trade": {
        "name": "物价交易",
        "description": "阵营竞拍、的卢拍卖、金币行情、物品物价、成本、万宝楼与交易行。",
    },
    "battle": {
        "name": "阵营战场",
        "description": "帮战记录、阵营沙盘与诛恶事件。",
    },
    "role": {
        "name": "角色查询",
        "description": "奇遇、角色详情、在线状态、属性与装备、阵眼、技能、奇穴、名片、百战与蹲宠。",
    },
    "macro": {
        "name": "魔盒功能",
        "description": "魔盒配装、奇遇攻略、魔盒宏与交易行。",
    },
    "community": {
        "name": "游戏社区",
        "description": "趣味选择、小药、语录、聊天、统战、家园、师徒、新闻、招募与贴吧。",
    },
    "tools": {
        "name": "系统工具",
        "description": "科举答案、大区状态、开服状态与技改记录。",
    },
    "dungeon": {
        "name": "副本秘境",
        "description": "秘境方位、物品掉落统计与试炼秒伤计算。",
    },
    "avoid": {
        "name": "避雷功能",
        "description": "按会话隔离的避雷记录增删改查。",
    },
    "team": {
        "name": "团队功能",
        "description": "开团、报名、成员调整、团队黑本与报名限制。",
    },
}

# 分类顺序即管理页卡片展示顺序。
FEATURE_ORDER: tuple[str, ...] = FEATURE_SECTION_ORDER

# 分类元信息：展示名、说明、令牌消耗提示、默认开关。
FEATURE_INFO: dict[str, dict[str, Any]] = {
    "functions": {
        "name": "功能类",
        "description": "功能帮助、区服绑定与事件推送等插件入口。",
        "cost": "不消耗 JX3API 次数",
        "default": True,
    },
    "activity": {
        "name": "活动情报",
        "description": "活动日历、声望社、赤兔、马场与烟花。",
        "cost": "消耗 JX3API 次数",
        "default": True,
    },
    "ranking": {
        "name": "排行榜单",
        "description": "名剑、跨服、个人/帮会榜单、试炼、资历、据点贡献与绝境战场。",
        "cost": "消耗 JX3API 次数",
        "default": True,
    },
    "trade": {
        "name": "物价交易",
        "description": "阵营竞拍、的卢、金币、物品物价、成本与万宝楼。",
        "cost": "含 JX3BOX 行情查询",
        "default": True,
    },
    "battle": {
        "name": "阵营战场",
        "description": "帮战记录、阵营沙盘与诛恶事件。",
        "cost": "消耗 JX3API 次数",
        "default": True,
    },
    "role": {
        "name": "角色查询",
        "description": "奇遇、角色详情、在线状态、属性与装备、阵眼、技能、奇穴、名片、百战与蹲宠。",
        "cost": "消耗 JX3API 次数",
        "default": True,
    },
    "macro": {
        "name": "魔盒功能",
        "description": "魔盒配装、奇遇攻略、魔盒宏与交易行。",
        "cost": "含 JX3BOX 配装、攻略、宏与交易行",
        "default": True,
    },
    "community": {
        "name": "游戏社区",
        "description": "趣味选择、小药、语录、聊天、统战、家园、师徒、新闻、招募与贴吧。",
        "cost": "含 JX3BOX 小药",
        "default": True,
    },
    "tools": {
        "name": "系统工具",
        "description": "科举答案、大区状态、开服状态与技改记录。",
        "cost": "消耗 JX3API 次数",
        "default": True,
    },
    "dungeon": {
        "name": "副本秘境",
        "description": "秘境方位、物品掉落统计与试炼秒伤计算。",
        "cost": "消耗 JX3API 次数",
        "default": True,
    },
    "avoid": {
        "name": "避雷功能",
        "description": "按会话隔离的避雷名单。",
        "cost": "不消耗 JX3API 次数",
        "default": True,
    },
    "team": {
        "name": "团队功能",
        "description": "开团、报名、成员调整、团队黑本与报名限制。",
        "cost": "不消耗 JX3API 次数",
        "default": True,
    },
}

# 每个分类直接包含的指令名（不含元指令与会话设置）。
FEATURE_COMMANDS: dict[str, frozenset[str]] = {
    "functions": frozenset(
        {
            "功能",
            "绑定区服",
            "解绑区服",
            "事件推送",
        }
    ),
    "activity": frozenset(
        {
            "日常",
            "日常预测",
            "穹野卫",
            "披风会",
            "云从社",
            "楚天社",
            "赤兔",
            "本周赤兔",
            "刷马",
            "马场",
            "烟花",
        }
    ),
    "ranking": frozenset(
        {
            "战绩",
            "名剑排行",
            "名剑统计",
            "跨服名剑",
            "武林争霸",
            "捕快荣誉",
            "江湖浪客",
            "决斗挑战",
            "帮会排行",
            "阵营排行",
            "个人排行",
            "据点贡献",
            "绝境战场",
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
        }
    ),
    "battle": frozenset(
        {
            "帮战",
            "沙盘",
            "诛恶",
        }
    ),
    "role": frozenset(
        {
            "奇遇",
            "查询",
            "汇总",
            "近期",
            "统计",
            "角色",
            "在线",
            "属性",
            "装备",
            "阵眼",
            "技能",
            "奇穴",
            "名片",
            "全名片",
            "随机秀",
            "精耐",
            "百战",
            "蹲宠",
        }
    ),
    "macro": frozenset(
        {
            "配装",
            "攻略",
            "宏",
            "交易行",
        }
    ),
    "community": frozenset(
        {
            "答案之书",
            "喝什么",
            "吃什么",
            "小药",
            "舔狗语录",
            "疯狂星期四",
            "彩虹屁",
            "毒鸡汤",
            "朋友圈",
            "骚话",
            "渣男语录",
            "发言",
            "统战",
            "骗子",
            "花价",
            "拜师",
            "收徒",
            "维护",
            "新闻",
            "招募",
            "团长",
            "团牌",
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
            "秒伤",
        }
    ),
    "avoid": frozenset(
        {
            "避雷添加",
            "避雷查看",
            "避雷查询",
            "避雷修改",
            "避雷删除",
        }
    ),
    "team": frozenset(
        {
            "开团",
            "打开报名",
            "关闭报名",
            "报名",
            "取消报名",
            "查看团队",
            "修改报名",
            "交换位置",
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
}

# 分类内固定展示顺序：优先按官网小类及其接口顺序排列。
COMMAND_ORDER: dict[str, tuple[str, ...]] = {
    "functions": ("功能", "绑定区服", "解绑区服", "事件推送"),
    "activity": (
        "日常",
        "日常预测",
        "穹野卫",
        "披风会",
        "云从社",
        "楚天社",
        "赤兔",
        "本周赤兔",
        "刷马",
        "马场",
        "烟花",
    ),
    "ranking": (
        "战绩",
        "名剑排行",
        "名剑统计",
        "绝境战场",
        "据点贡献",
        "帮会排行",
        "个人排行",
        "试炼排行",
        "武林争霸",
        "捕快荣誉",
        "江湖浪客",
        "跨服名剑",
        "决斗挑战",
        "资历",
        "资历排行",
    ),
    "trade": ("金价", "物价", "成本", "看号", "阵营拍卖", "的卢"),
    "battle": ("帮战", "沙盘", "诛恶"),
    "role": (
        "汇总",
        "近期",
        "奇遇",
        "查询",
        "统计",
        "角色",
        "在线",
        "属性",
        "装备",
        "阵眼",
        "技能",
        "奇穴",
        "名片",
        "随机秀",
        "全名片",
        "精耐",
        "百战",
        "蹲宠",
    ),
    "macro": ("配装", "攻略", "宏", "交易行"),
    "community": (
        "答案之书",
        "喝什么",
        "吃什么",
        "小药",
        "花价",
        "维护",
        "新闻",
        "舔狗语录",
        "朋友圈",
        "骚话",
        "渣男语录",
        "疯狂星期四",
        "彩虹屁",
        "毒鸡汤",
        "统战",
        "骗子",
        "拜师",
        "收徒",
        "招募",
        "团长",
        "团牌",
        "贴吧物价",
        "818",
        "发言",
    ),
    "tools": ("科举", "区服", "开服", "技改"),
    "dungeon": ("解密", "掉落", "秒伤"),
    "avoid": ("避雷添加", "避雷查看", "避雷查询", "避雷修改", "避雷删除"),
    "team": (
        "开团",
        "打开报名",
        "关闭报名",
        "结束团队",
        "结束全部团队",
        "清空报名",
        "修改报名",
        "交换位置",
        "查看限制",
        "添加限制",
        "修改限制",
        "删除限制",
        "恢复默认限制",
        "团队黑本",
        "报名",
        "取消报名",
        "查看团队",
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
    """把已保存的开关状态归一成「指令名 -> 是否启用」的完整状态。

    配置格式为扁平的 ``{指令名: bool}``；缺失或非布尔的指令回退到默认
    开启，保证新增指令或旧数据不会意外关闭功能。
    """
    resolved = command_defaults()
    if isinstance(config, Mapping):
        for command in resolved:
            value = config.get(command)
            if isinstance(value, bool):
                resolved[command] = value
    return resolved


def normalize_selection(payload: Any) -> dict[str, bool]:
    """从 WebUI 提交的数据中提取可识别的逐条指令开关。

    Args:
        payload: 可能为 ``{分类: {指令名: bool}}``、扁平 ``{指令名: bool}``
            或两者的混合结构。

    Returns:
        仅包含目录内指令的 ``{指令名: bool}``，未知键和非布尔值都会被忽略。
    """
    commands = command_defaults()
    selected: dict[str, bool] = {}
    pending = [payload]
    while pending:
        node = pending.pop()
        if not isinstance(node, Mapping):
            continue
        for key, value in node.items():
            if key in commands and isinstance(value, bool):
                selected[key] = value
            elif isinstance(value, Mapping):
                pending.append(value)
    return selected


def command_feature(command: str) -> str | None:
    """返回指令所属分类；元指令返回 ``None``。"""
    for key in FEATURE_ORDER:
        if command in FEATURE_COMMANDS[key]:
            return key
    return None


def command_enabled(command: str, enabled: Mapping[str, bool]) -> bool:
    """判断某条指令在当前开关下是否应注册。"""
    if command_feature(command) is None:
        # 未归类的指令按默认启用处理，避免误伤；test_features 会提醒补录。
        return True
    return bool(enabled.get(command, True))


def describe(enabled: Mapping[str, bool] | None = None) -> list[dict[str, Any]]:
    """输出供管理页渲染的分类列表（含每条指令的开关状态）。"""
    resolved = command_defaults()
    if isinstance(enabled, Mapping):
        for command in resolved:
            value = enabled.get(command)
            if isinstance(value, bool):
                resolved[command] = value
    items: list[dict[str, Any]] = []
    for key in FEATURE_ORDER:
        info = FEATURE_INFO[key]
        section = FEATURE_SECTIONS[key]
        order = COMMAND_ORDER.get(key, ())
        order_index = {name: index for index, name in enumerate(order)}
        commands = [
            {
                "name": command,
                "enabled": bool(resolved.get(command, True)),
            }
            for command in sorted(
                FEATURE_COMMANDS[key],
                key=lambda name: order_index.get(name, len(order)),
            )
        ]
        enabled_count = sum(1 for item in commands if item["enabled"])
        items.append(
            {
                "key": key,
                "section": key,
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
