import json
import html
import re
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Union
from inspect import isawaitable
from typing import Any, Awaitable, Callable, Dict, Optional

from astrbot.api import logger
from astrbot.api import AstrBotConfig
import astrbot.api.message_components as Comp

from .request import APIClient
from .sqlite import AsyncSQLiteDB
from .fun_basic import load_template,gold_to_parts,week_to_num,compare_date_str,format_time,format_remaining

JX3BOX_API_BASE_URLS = {
    "node": "https://node.jx3box.com",
    "next2": "https://next2.jx3box.com",
    "cms": "https://cms.jx3box.com",
}


class JX3BOXService:
    def __init__(self, config: AstrBotConfig, sqlite: AsyncSQLiteDB, cache_sqlite: Optional[AsyncSQLiteDB] = None):
        # 实例化 API Client
        self._api: APIClient = APIClient()
        # 引用插件配置文件
        self._config = config
        # 引用sqlite
        self._sql_db = sqlite
        self._cache_db = cache_sqlite or sqlite

        self.token = self._config.get("jx3api_token", "")

    async def close(self):
        """释放底层 APIClient 资源"""
        if self._api:
            await self._api.close()


    def _init_return_data(self) -> Dict[str, Any]:
            """初始化标准的返回数据结构"""
            return {
                "code": 0,
                "msg": "功能函数未执行",
                "data": {},
                "temp": "",
                "icons": {}
            }


    async def _base_request(
        self,
        source: str,
        api_path: str,
        method: str = "GET",
        params: Optional[Dict[str, Any]] = None,
        out: Optional[str] = "data",
    ) -> Optional[Any]:
        """统一封装 JX3BOX Node、Next2 和 CMS 接口请求。"""
        try:
            if not self._api:
                logger.error("API client is not initialized")
                return None

            base_url = JX3BOX_API_BASE_URLS.get(source)
            if not base_url:
                logger.error(f"不支持的 JX3BOX 数据源: {source}")
                return None

            normalized_path = api_path if api_path.startswith("/") else f"/{api_path}"
            api_url = f"{base_url}{normalized_path}"
            request_method = method.upper()

            if request_method == "GET":
                data = await self._api.get(api_url, params=params, out_key=out)
            elif request_method == "POST":
                data = await self._api.post(api_url, data=params, out_key=out)
            else:
                logger.error(f"不支持的 JX3BOX 请求方法: {request_method}")
                return None

            if not data:
                logger.warning(f"获取接口信息失败或返回空数据: {api_url}")

            return data

        except Exception as e:
            logger.error(f"JX3BOX 基础请求调用出错 ({source}:{api_path}): {e}")
            return None


    async def qiyugonglue(self, name: str) -> Dict[str, Any]:
        """奇遇攻略"""
        return_data = self._init_return_data()
        
        # 1. 调用基础请求
        data = await self._base_request(
            "node",
            "/serendipities",
            params={"name": name},
            out="list",
        )
        if not data:
            return_data["msg"] = "未找到该奇遇"
            return return_data
        
        # 提取dwID
        dwID = data[0]["dwID"]
        data1 = await self._base_request(
            "node",
            f"/serendipity/{dwID}/achievement",
            out=None,
        )

        # 获取奇遇攻略
        data2 = await self._base_request(
            "cms",
            f"/api/cms/wiki/post/type/achievement/source/{data1['achievement_id']}",
        )
        if not data2:
            return_data["msg"] = "获取攻略数据异常"
            return return_data
        
        # 4. 处理数据
        try:
            return_data["data"] = {}
            content = data2["post"]["content"]
            return_data["temp"] = content
        except Exception as e:
            logger.exception("处理返回数据失败")
            return_data["msg"] = "处理返回数据失败"
            return return_data

        return_data["code"] = 200

        return return_data        


    async def peizhuang(self, name: str, tags: str) -> Dict[str, Any]:
        """配装"""
        return_data = self._init_return_data()
        
        # 数据库查询数据
        result = await self._sql_db.select_one(
                "kungfu",
                "name=? OR name1=? OR name2=? OR name3=? OR name4=? OR name5=?",
                (name, name, name, name, name, name)
            )
        logger.debug(result)
        if result is None:
            return_data["msg"] = "未找到该心法"
            return return_data
        
        mount = result.get("pzid", None)
        if not mount:
            return_data["msg"] = "未找到该心法"
            return return_data
        
        logger.debug(f"查询到数据：{mount}")

        # 1. 构造请求参数
        params = {
            "per": "10",
            "page": "1",
            "tags": tags,
            "client": "std",
            "global_level": "130",
            "mount": mount,
            "star": "1"
        }
        
        # 2. 调用基础请求
        data: Optional[Dict[str, Any]] = await self._base_request(
            "cms",
            "/api/cms/app/pz",
            params=params,
        )

        # 验证数据
        if not data:
            return_data["msg"] = "配装数据获取异常"
            return return_data
        
        # 3. 处理返回数据
        try:
            result_msg = f"{name}--配装\n"        
            for item in data["list"]:
                result_msg += f"【{item['zlp']}】--{item['title']}\n"
                result_msg += f"链接：https://www.jx3box.com/pz/view/{item['id']}\n\n"

            return_data["data"] = result_msg

        except Exception as e:
            logger.exception("处理返回数据失败:",e)
            return_data["msg"] = "处理返回数据失败"
            return return_data    

        return_data["code"] = 200
        
        return return_data


    async def _macro_posts(self, name: str) -> Optional[List[Dict[str, Any]]]:
        """按心法查询宏帖子，并保留接口热度排序。"""
        result = await self._sql_db.select_one(
                "kungfu",
                "name=? OR name1=? OR name2=? OR name3=? OR name4=? OR name5=?",
                (name, name, name, name, name, name)
            )

        if result is None:
            return None

        kungfu = result.get("name", None)
        if kungfu is None:
            return None
        
        logger.debug(f"查询到数据：{kungfu}")
        data: Optional[Dict[str, Any]] = await self._base_request(
            "cms",
            "/api/cms/posts",
            params={"subtype": kungfu},
        )
        if not isinstance(data, dict):
            return None

        return [
            item
            for item in data.get("list", [])
            if isinstance(item, dict) and item.get("ID")
        ]


    async def hong1(self, name: str) -> Dict[str, str]:
        """宏首轮：返回“序号 -> 显示内容”的选择数据。"""
        posts = await self._macro_posts(name)

        if not posts:
            raise ValueError("未找到该心法一键宏")
        
        try:
            options = {
                str(index): f"{post.get('author', '')}\t{post.get('post_title', '')}"
                for index, post in enumerate(posts, start=1)
            }

            if not options:
                raise ValueError("未找到该心法一键宏")

        except Exception as e:
            logger.exception("处理返回数据失败")
            if isinstance(e, ValueError):
                raise
            raise RuntimeError("处理返回数据失败") from e

        return options


    async def hong_select(self,name: str,selected: Dict[str, Any],) -> Dict[str, Any]:
        """宏次轮：根据单项选择数据重新定位帖子并查询详情。"""
        if not isinstance(selected, dict) or len(selected) != 1:
            return_data = self._init_return_data()
            return_data["msg"] = "宏选项数据格式异常"
            return return_data

        choice, label = next(iter(selected.items()))
        posts = await self._macro_posts(name)
        if not posts:
            return_data = self._init_return_data()
            return_data["msg"] = "未找到该心法一键宏"
            return return_data

        selected_post = next(
            (
                post
                for post in posts
                if f"{post.get('author', '')}\t{post.get('post_title', '')}"
                == str(label)
            ),
            None,
        )
        if selected_post is None:
            try:
                selected_post = posts[int(choice) - 1]
            except (TypeError, ValueError, IndexError):
                return_data = self._init_return_data()
                return_data["msg"] = "无效宏序号"
                return return_data

        pid = str(selected_post.get("ID") or "").strip()
        if not pid:
            return_data = self._init_return_data()
            return_data["msg"] = "宏帖子 ID 无效"
            return return_data

        return await self.hong2(pid)
    

    async def hong2(self, pid: str) -> Dict[str, Any]:
        """宏 心法"""
        return_data = self._init_return_data()

        data = await self._base_request("cms", f"/api/cms/post/{pid}")

        if not isinstance(data, dict):
            return_data["msg"] = "获取宏数据异常"
            return return_data

        try:
            # 文章正文
            return_data["temp"] = data.get("post_content", "")

            # 安全获取宏数据，避免 KeyError
            macro_list = data.get("post_meta", {}).get("data", [])

            msg = ""

            for m in macro_list:
                msg += f"【宏名称】\n{m.get('name', '')}\n"
                msg += f"【使用说明】\n{m.get('desc', '')}\n"
                msg += f"【宏脚本】\n{m.get('macro', '')}\n\n"

            # 没有宏数据时返回文章信息
            if not msg:
                msg = (
                    f"标题：{data.get('post_title', '')}\n"
                    f"作者：{data.get('author', '')}\n"
                    "该帖子没有宏数据"
                )

            return_data["data"] = msg
            return_data["code"] = 200

        except Exception:
            logger.exception("处理返回数据失败")
            return_data["msg"] = "处理返回数据失败"

        return return_data


    async def _load_trade_cache(self, key: str) -> tuple[Optional[Any], bool]:
        """读取交易行基础数据缓存，返回数据和是否已过期。"""
        try:
            row = await self._cache_db.select_one("trade_item_cache", "key=?", (key,))
        except Exception as e:
            logger.error(f"读取交易行缓存失败: {e}")
            return None, True

        if not row:
            return None, True

        try:
            payload = json.loads(row.get("content", "{}"))
            updated_at = datetime.strptime(row.get("updated_at", ""), "%Y-%m-%d %H:%M:%S")
            expired = datetime.now() - updated_at > timedelta(days=30)
            return payload, expired
        except Exception as e:
            logger.error(f"解析交易行缓存失败: {e}")
            return None, True


    async def _save_trade_cache(self, key: str, payload: Any):
        """写入交易行基础数据缓存。"""
        try:
            await self._cache_db.execute(
                """
                INSERT INTO trade_item_cache (key, content, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    content=excluded.content,
                    updated_at=excluded.updated_at
                """,
                (
                    key,
                    json.dumps(payload, ensure_ascii=False),
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
        except Exception as e:
            logger.error(f"写入交易行缓存失败: {e}")


    async def _get_trade_item_groups(self) -> Optional[List[Dict[str, Any]]]:
        """获取交易行物品库，优先使用未过期缓存"""
        cache_key = "trade_item_groups"
        cached, expired = await self._load_trade_cache(cache_key)
        if isinstance(cached, list) and not expired:
            return cached

        
        data = await self._base_request(
            "cms",
            "/api/cms/pvx/item/group",
            params={"client": "std"},
        )
        if isinstance(data, list) and data:
            await self._save_trade_cache(cache_key, data)
            return data

        if isinstance(cached, list) and cached:
            logger.warning("交易行物品库接口失败，使用旧缓存")
            return cached

        return None


    def _flatten_trade_items(self, groups: List[Dict[str, Any]]) -> list[Dict[str, Any]]:
        """从交易行物品分组中提取可查询物品"""
        items = []
        for group in groups:
            if not isinstance(group, dict):
                continue
            for item in group.get("items", []) or []:
                if not isinstance(item, dict):
                    continue
                item_id = item.get("item_id")
                label = item.get("label")
                if not item_id or not label:
                    continue
                items.append(
                    {
                        "item_id": str(item_id),
                        "label": str(label),
                        "icon": str(item.get("icon") or ""),
                    }
                )
        return items


    def _match_trade_items(self, items: list[Dict[str, Any]], keyword: str, limit: int = 50) -> list[Dict[str, Any]]:
        """按物品名模糊匹配交易行物品"""
        keyword = (keyword or "").strip()
        if not keyword:
            return []

        matched = []
        seen = set()
        for item in items:
            label = item.get("label", "")
            item_id = item.get("item_id", "")
            if keyword not in label or item_id in seen:
                continue
            seen.add(item_id)
            if label == keyword:
                rank = 0
            elif label.startswith(keyword):
                rank = 1
            else:
                rank = 2
            matched.append((rank, len(label), label, item))

        matched.sort(key=lambda row: (row[0], row[1], row[2]))
        return [row[3] for row in matched[:limit]]


    async def jiaoyihang(self, name: str , server: str) -> Dict[str, Any]:
        """区服交易行"""
        return_data = self._init_return_data()

        item_groups = await self._get_trade_item_groups()
        if not item_groups:
            return_data["msg"] = "交易行基础物品数据获取失败"
            return return_data

        trade_items = self._flatten_trade_items(item_groups)
        matched_items = self._match_trade_items(trade_items, name, 50)
        if not matched_items:
            return_data["msg"] = "未找到匹配的交易行物品"
            return return_data

        item_map = {item["item_id"]: item for item in matched_items}
        params = {
            "item_ids": list(item_map.keys()),
            "server": server,
            "aggregate_type": "hourly",
        }
        price_data: Optional[List[Dict[str, Any]]] = await self._base_request(
            "next2",
            "/api/auction/",
            method="POST",
            params=params,
            out="",
        )


        if not price_data or not isinstance(price_data, list):
            return_data["msg"] = "未查询到交易行价格数据"
            return return_data

        try:
            result = []
            for price_item in price_data:
                if not isinstance(price_item, dict):
                    continue

                item_id = str(price_item.get("item_id") or "")
                base_item = item_map.get(item_id)
                if not base_item:
                    continue

                timestamp = price_item.get("timestamp")
                try:
                    created = datetime.fromtimestamp(int(timestamp)).strftime("%Y-%m-%d %H:%M:%S")
                except (TypeError, ValueError, OSError):
                    created = ""

                result.append(
                    {
                        "item_id": item_id,
                        "name": base_item.get("label", ""),
                        "icon": f"https://icon.jx3box.com/icon/{base_item.get('icon', '')}.png",
                        "server": price_item.get("server", server),
                        "price": price_item.get("price", 0),
                        "price_parts": gold_to_parts(price_item.get("price", 0)),
                        "sample": price_item.get("sample", 0),
                        "created": created,
                    }
                )

            if not result:
                return_data["msg"] = "未查询到交易行价格数据"
                return return_data

            return_data["data"] = {
                "search_name": name,
                "server": server,
                "matched_count": len(matched_items),
                "result_count": len(result),
                "list": result,
                "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        except Exception as e:
            logger.error(f"处理交易行数据失败: {e}")
            return_data["msg"] = "处理交易行数据失败"
            return return_data

        # 5. 模板渲染
        try:
            return_data["temp"] = await load_template("jiaoyihang.html")
            return_data["code"] = 200
        except FileNotFoundError as e:
            logger.error(f"加载模板失败: {e}")
            return_data["msg"] = "系统错误：模板文件不存在"
            return return_data

        return return_data
