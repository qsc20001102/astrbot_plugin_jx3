from datetime import datetime,date
from zoneinfo import ZoneInfo

import base64
import os
import re

from astrbot.api import logger

from .template import load_template
    

def gold_to_string(gold_amount):
    """
    将金钱数值转换为字符串表示形式

    Args:
        gold_amount (int): 金钱数值，单位为铜币

    Returns:
        str: 格式化后的金钱字符串，例如 "1金2银3铜"
    """
    if not gold_amount:
        return "无价格"

    parts = []
    started = False  # 标记是否已经遇到第一个非零位

    bricks = gold_amount // 100000000
    gold = (gold_amount % 100000000) // 10000
    silver = (gold_amount % 10000) // 100
    copper = gold_amount % 100

    for value, unit in [(bricks, "砖"), (gold, "金"), (silver, "银"), (copper, "铜")]:
        if value != 0:
            started = True
        if started:
            parts.append(f"{value}{unit}")

    return "".join(parts)


def gold_to_parts(gold_amount):
    """将铜钱数拆成模板可渲染的货币片段"""
    try:
        amount = int(gold_amount or 0)
    except (TypeError, ValueError):
        amount = 0

    if amount <= 0:
        return []

    bricks = amount // 100000000
    gold = (amount % 100000000) // 10000
    silver = (amount % 10000) // 100
    copper = amount % 100

    parts = []
    started = False
    for key, name, value in [
        ("zhuang", "砖", bricks),
        ("jin", "金", gold),
        ("yin", "银", silver),
        ("tong", "铜", copper),
    ]:
        if value != 0:
            started = True
        if started:
            parts.append({"key": key, "name": name, "value": value})

    return parts


def week_to_num(week :str):
    week_map = {
    "一": 0,
    "二": 1,
    "三": 2,
    "四": 3,
    "五": 4,
    "六": 5,
    "日": 6,  
    }
    return week_map.get(week,None)


def compare_date_str(date_str: str) -> str:
    """
    date_str 格式：YYYY-MM-DD
    """
    d = datetime.strptime(date_str, "%Y-%m-%d").date()
    today = date.today()

    if d < today:
        return "过去"
    elif d == today:
        return "今天"
    else:
        return "将来"


def load_as_base64(icons_dir: str) -> dict[str, str]:
    """
    将指定目录下的图标文件转换为 base64 字符串。
    返回 {"文件名（不含扩展名）": "data:image/xxx;base64,xxx"} 的字典。
    """
    supported_ext = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico"}
    icons = {}

    for filename in os.listdir(icons_dir):
        name, ext = os.path.splitext(filename)
        if ext.lower() not in supported_ext:
            continue

        filepath = os.path.join(icons_dir, filename)
        with open(filepath, "rb") as f:
            data = base64.b64encode(f.read()).decode()

        display_name = name
        try:
            display_name = name.encode("latin-1").decode("gbk")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass

        if ext.lower() == ".svg":
            mime = "image/svg+xml"
        elif ext.lower() == ".jpg":
            mime = "image/jpeg"
        else:
            mime = f"image/{ext.lower().lstrip('.')}"

        icons[display_name] = f"data:{mime};base64,{data}"

    return icons


def format_time(ts):
    try:
        return datetime.fromtimestamp(int(ts),
            tz=ZoneInfo("Asia/Shanghai")
            ).strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError, OSError):
        return ""

def format_remaining(ts):
    try:
        seconds = max(0, int(ts) - int(datetime.now().timestamp()))
        hours, seconds = divmod(seconds, 3600)
        minutes, seconds = divmod(seconds, 60)
        return f"{hours}时{minutes:02d}分{seconds:02d}秒"
    except (TypeError, ValueError):
        return ""


def format_duration(seconds):
    """把秒数格式化为“时/分/秒”，与到期时间戳区分开。"""
    try:
        total = max(0, int(seconds))
    except (TypeError, ValueError):
        return ""

    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}时{minutes:02d}分{secs:02d}秒"
    if minutes:
        return f"{minutes}分{secs:02d}秒"
    return f"{secs}秒"


# 剑网3 的技能/奇穴描述里会混入给客户端解析的占位标签，例如
# <SUB 17641 0>、<TALENT 16890 1 额外效果>、<BUFF 743 0 desc>。
# 其中 TALENT、BUFF_NOUN、EnchantID 的最后一段是可读文本，需要保留；
# 其余标签只用于取值，直接移除。
_JX3_INLINE_TEXT_PATTERN = re.compile(
    r"<(?:TALENT|BUFF_NOUN)\s+\d+\s+\d+\s*(.*?)>",
    re.DOTALL,
)
_JX3_ENCHANT_TEXT_PATTERN = re.compile(
    r"<EnchantID\s+\d+\s*(.*?)>",
    re.DOTALL,
)
_JX3_ANY_TAG_PATTERN = re.compile(r"<[^>]*>")


def clean_jx3_text(value):
    """把接口返回的剑网3富文本占位标签清理成可读文本。"""
    text = str(value or "")
    text = _JX3_INLINE_TEXT_PATTERN.sub(lambda match: match.group(1), text)
    text = _JX3_ENCHANT_TEXT_PATTERN.sub(lambda match: match.group(1), text)
    text = _JX3_ANY_TAG_PATTERN.sub("", text)
    text = text.replace("\\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()
