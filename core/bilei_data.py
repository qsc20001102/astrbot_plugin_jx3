# pyright: reportArgumentType=false
# pyright: reportAttributeAccessIssue=false
# pyright: reportIndexIssue=false
# pyright: reportOptionalMemberAccess=false

from datetime import datetime
from typing import Dict, Any, Optional, List, Union

from astrbot.api import logger
from astrbot.api import AstrBotConfig

from .sqlite import AsyncSQLiteDB
from .fun_basic import load_template
class BiLeidata:
    def __init__(self,sqlite:AsyncSQLiteDB):
        # 引用sqlite
        self._sql_db = sqlite
        
    def _init_return_data(self) -> Dict[str, Any]:
        """初始化标准的返回数据结构"""
        return {
            "code": 0,
            "msg": "功能函数未执行",
            "data": {}
        }
    

    # --- 业务功能函数 ---
    async def add(self,name: str, text: str ,user: str) -> Dict[str, Any]:
        """避雷添加"""
        return_data = self._init_return_data()
        
        # 获取系统时间
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 添加数据
        try:
            await self._sql_db.insert(
                "bilei",
                {
                    "name": name,
                    "text": text,
                    "time": now,
                    "user": user,
                }
            )

        except FileNotFoundError as e:
            logger.error(f"添加避雷失败: {e}")
            return_data["msg"] = "添加避雷失败"
            return return_data

        return_data["data"] = (
            "避雷添加成功\n"
            f"避雷名称：{name}\n"
            f"避雷备注：{text}\n"
            f"添加时间：{now}\n"
            f"记录人：{user}\n"
        )  

        return_data["code"] = 200
   
        return return_data
    

    async def all(self) -> Dict[str, Any]:
        """避雷查看"""
        return_data = self._init_return_data()
        

        # 查询数据
        try:
            data = await self._sql_db.select_all("bilei")
        except FileNotFoundError as e:
            logger.error(f"查看避雷失败: {e}")
            return_data["msg"] = "查看避雷失败"
            return return_data

        if not data:
            return_data["msg"] = "未找到避雷数据"
            return return_data
        

        # 加载模板
        try:
            return_data["temp"] = await load_template("bilei.html")
        except FileNotFoundError as e:
            logger.error(f"加载模板失败: {e}")
            return_data["msg"] = "系统错误：模板文件不存在"
            return return_data
        
        # 数据处理
        return_data["data"]["lists"] = data
        
        return_data["code"] = 200
   
        return return_data
    

    async def select(self, name:str) -> Dict[str, Any]:
        """避雷查询 名称"""
        return_data = self._init_return_data()
        
        # 模糊拼接
        like_name = f"%{name}%"
        # 查询数据
        try:
            data = await self._sql_db.select_all(
                "bilei",
                "name LIKE ?",
                (like_name,)
            )
        except FileNotFoundError as e:
            logger.error(f"查询避雷失败: {e}")
            return_data["msg"] = "查询避雷失败"
            return return_data

        if not data:
            return_data["msg"] = "未查询到避雷数据"
            return return_data
        

        # 加载模板
        try:
            return_data["temp"] = await load_template("bilei.html")
        except FileNotFoundError as e:
            logger.error(f"加载模板失败: {e}")
            return_data["msg"] = "系统错误：模板文件不存在"
            return return_data
        
        # 数据处理
        return_data["data"]["lists"] = data
        
        return_data["code"] = 200
   
        return return_data
    

    async def update(self, id:int, name: str, text: str ,user: str) -> Dict[str, Any]:
        """避雷修改 ID 名称 备注"""
        return_data = self._init_return_data()
        
        data = await self._sql_db.select_one(
                "bilei",
                "id=?",
                (id,)
            )

        if not data:
            return_data["msg"] = "没有当前ID"
            return return_data
        
        # 获取系统时间
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 修改数据
        try:
            await self._sql_db.update(
                "bilei",
                {
                    "name": name,
                    "text": text,
                    "time": now,
                    "user": user,
                },
                "id=?",
                (id,)
            )

        except FileNotFoundError as e:
            logger.error(f"避雷修改失败: {e}")
            return_data["msg"] = "避雷修改失败"
            return return_data

        return_data["data"] = (
            "避雷修改成功\n"
            f"ID：{id}\n"
            f"避雷名称：{name}\n"
            f"避雷备注：{text}\n"
            f"修改时间：{now}\n"
            f"修改人：{user}\n"
        )  

        return_data["code"] = 200
   
        return return_data
    

    async def delete(self, id:int) -> Dict[str, Any]:
        """避雷删除 ID"""
        return_data = self._init_return_data()
        
        data = await self._sql_db.select_one(
                "bilei",
                "id=?",
                (id,)
            )

        if not data:
            return_data["msg"] = "没有当前ID"
            return return_data

        # 删除
        try:
            await self._sql_db.delete(
                "bilei",
                "id=?",
                (id,)
            )

        except FileNotFoundError as e:
            logger.error(f"避雷删除失败: {e}")
            return_data["msg"] = "避雷删除失败"
            return return_data

        return_data["data"] = f"避雷删除成功。ID：{id}"
 
        return_data["code"] = 200
   
        return return_data