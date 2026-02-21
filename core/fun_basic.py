from pathlib import Path
from datetime import datetime,date
import aiofiles
import base64
import os

async def load_template(template_name: str) -> str:
    """
    异步加载模板内容（非阻塞）
    """
    plugin_dir = Path(__file__).parent.parent
    template_path = plugin_dir / "templates" / template_name

    if not template_path.exists():
        raise FileNotFoundError(f"模板文件不存在: {template_path}")

    async with aiofiles.open(template_path, "r", encoding="utf-8") as f:
        return await f.read()
    

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

        # 用原始文件名（系统实际存储的）打开文件
        filepath = os.path.join(icons_dir, filename)
        with open(filepath, "rb") as f:
            data = base64.b64encode(f.read()).decode()

        # 尝试修正显示用的 key（如果文件名是 GBK 乱码）
        display_name = name
        try:
            display_name = name.encode("latin-1").decode("gbk")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass  # 本来就是正确的 UTF-8

        if ext.lower() == ".svg":
            mime = "image/svg+xml"
        elif ext.lower() == ".jpg":
            mime = "image/jpeg"
        else:
            mime = f"image/{ext.lower().lstrip('.')}"

        icons[display_name] = f"data:{mime};base64,{data}"

    return icons