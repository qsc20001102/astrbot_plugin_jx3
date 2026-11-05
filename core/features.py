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

# 功能分组顺序即管理页展示顺序。
FEATURE_ORDER: tuple[str, ...] = (
    "basic",
    "peizhuang",
    "fun",
    "daily",
    "rank",
    "misc",
    "team",
    "bilei",
    "event_push",
)

# 分组元信息：展示名、说明、令牌消耗提示、默认开关。
FEATURE_INFO: dict[str, dict[str, Any]] = {
    "basic": {
        "name": "基础查询",
        "description": "角色名片、属性装备、奇遇、成就、物价、沙盘、资讯等核心查询。",
        "cost": "消耗 JX3API 次数",
        "default": True,
    },
    "peizhuang": {
        "name": "配装查询",
        "description": "从 JX3BOX 配装站查询心法推荐配装。",
        "cost": "不消耗 JX3API 次数",
        "default": True,
    },
    "fun": {
        "name": "趣味互动",
        "description": "答案之书、毒鸡汤、疯狂星期四、骚话等本地娱乐指令。",
        "cost": "不消耗 JX3API 次数",
        "default": True,
    },
    "daily": {
        "name": "日常与活动",
        "description": "日常任务、赤兔、关隘、阵营奉献、烟花、科举等周期性活动查询。",
        "cost": "消耗 JX3API 次数",
        "default": True,
    },
    "rank": {
        "name": "排行榜",
        "description": "名剑、帮会、阵营、试炼、资历等各类排行榜。",
        "cost": "消耗 JX3API 次数",
        "default": True,
    },
    "misc": {
        "name": "其它查询",
        "description": "招募、骗子、掉落、宏、统战、拜师收徒等零散查询。",
        "cost": "部分消耗 JX3API 次数",
        "default": True,
    },
    "team": {
        "name": "团队管理",
        "description": "开团、报名、黑本、报名限制等按会话隔离的团队功能。",
        "cost": "不消耗 JX3API 次数",
        "default": True,
    },
    "bilei": {
        "name": "避雷记录",
        "description": "按会话隔离的避雷名单增删改查。",
        "cost": "不消耗 JX3API 次数",
        "default": True,
    },
    "event_push": {
        "name": "实时事件推送",
        "description": "通过事件通道推送奇遇、马驹、沙盘等实时事件。",
        "cost": "需事件推送令牌",
        "default": True,
    },
}

# 每个分组包含的指令名（不含元指令与会话设置）。
FEATURE_COMMANDS: dict[str, frozenset[str]] = {
    "basic": frozenset(
        {
            "资历",
            "阵营拍卖",
            "金价",
            "物价",
            "成本",
            "看号",
            "帮战",
            "沙盘",
            "名片",
            "全名片",
            "随机秀",
            "奇遇",
            "查询",
            "未出",
            "汇总",
            "近期",
            "统计",
            "攻略",
            "精耐",
            "百战",
            "成就",
            "角色",
            "属性",
            "装备",
            "阵眼",
            "技能",
            "奇穴",
            "小药",
            "花价",
            "装饰",
            "器物",
            "维护",
            "新闻",
            "贴吧物价",
            "区服",
            "开服",
            "技改",
            "交易行",
        }
    ),
    "peizhuang": frozenset({"配装"}),
    "fun": frozenset(
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
            "818",
        }
    ),
    "daily": frozenset(
        {
            "日常",
            "日常预测",
            "穹野卫",
            "披风会",
            "云从社",
            "楚天社",
            "关隘",
            "赤兔",
            "本周赤兔",
            "阵营奉献",
            "烟花",
            "刷马",
            "马场",
            "的卢",
            "诛恶",
            "科举",
        }
    ),
    "rank": frozenset(
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
            "其他排行",
            "试炼排行",
            "资历排行",
        }
    ),
    "misc": frozenset(
        {
            "发言",
            "统战",
            "骗子",
            "拜师",
            "收徒",
            "招募",
            "团长",
            "团牌",
            "解密",
            "掉落",
            "宏",
        }
    ),
    "team": frozenset(
        {
            "开团",
            "打开报名",
            "关闭报名",
            "关闭报警",
            "结束团队",
            "结束全部团队",
            "清空报名",
            "报名",
            "取消报名",
            "查看团队",
            "团队黑本",
            "修改报名",
            "交换位置",
            "查看限制",
            "添加限制",
            "修改限制",
            "删除限制",
            "恢复默认限制",
        }
    ),
    "bilei": frozenset(
        {
            "避雷添加",
            "避雷查看",
            "避雷查询",
            "避雷修改",
            "避雷删除",
        }
    ),
    "event_push": frozenset({"事件推送"}),
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
        commands = [
            {"name": command, "enabled": bool(resolved.get(command, True))}
            for command in sorted(FEATURE_COMMANDS[key])
        ]
        enabled_count = sum(1 for item in commands if item["enabled"])
        items.append(
            {
                "key": key,
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
