# pyright: reportArgumentType=false
# pyright: reportAttributeAccessIssue=false
# pyright: reportIndexIssue=false
# pyright: reportOptionalMemberAccess=false

from datetime import datetime
from typing import Any, Dict

from astrbot.api import logger

from .sqlite import AsyncSQLiteDB
from .fun_basic import load_template


class BiLeidata:
    """按 AstrBot 会话隔离存储本地避雷记录。"""

    LEGACY_SESSION_ID = "__legacy_public__"

    def __init__(self, sqlite:AsyncSQLiteDB):
        # 引用sqlite
        self._sql_db = sqlite

    async def initialize(self):
        """创建避雷表，并把升级前的数据迁移到历史公共数据区。"""
        table = await self._sql_db.fetch_one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            ("bilei",),
        )
        if not table:
            await self._sql_db.execute(
                """
                CREATE TABLE bilei (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    name TEXT,
                    text TEXT,
                    time TEXT,
                    user TEXT
                )
                """
            )
        else:
            columns = await self._sql_db.fetch_all("PRAGMA table_info(bilei)")
            if "session_id" not in {str(column["name"]) for column in columns}:
                legacy_count_row = await self._sql_db.fetch_one(
                    "SELECT COUNT(*) AS count FROM bilei"
                )
                legacy_count = int((legacy_count_row or {}).get("count", 0))
                await self._sql_db.execute_transaction(
                    [
                        (
                            """
                            CREATE TABLE bilei_session_migration (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                session_id TEXT NOT NULL,
                                name TEXT,
                                text TEXT,
                                time TEXT,
                                user TEXT
                            )
                            """,
                            (),
                        ),
                        (
                            """
                            INSERT INTO bilei_session_migration (
                                id, session_id, name, text, time, user
                            )
                            SELECT id, ?, name, text, time, user FROM bilei
                            """,
                            (self.LEGACY_SESSION_ID,),
                        ),
                        ("DROP TABLE bilei", ()),
                        ("ALTER TABLE bilei_session_migration RENAME TO bilei", ()),
                    ]
                )
                logger.info(
                    f"已将 {legacy_count} 条旧避雷记录迁移到历史公共数据区"
                )

        await self._sql_db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_bilei_session_id_id
            ON bilei(session_id, id)
            """
        )

    @classmethod
    def _normalize_session_id(cls, session_id: Any) -> str:
        value = str(session_id or "").strip()
        if not value:
            raise ValueError("会话 ID 不能为空")
        if len(value) > 512:
            raise ValueError("会话 ID 不能超过 512 个字符")
        if value == cls.LEGACY_SESSION_ID:
            raise ValueError("历史公共数据区不能作为普通会话访问")
        return value

    async def list_legacy_records(self) -> list[Dict[str, Any]]:
        """列出等待从历史公共数据区迁出的旧版记录。"""
        return await self._sql_db.fetch_all(
            """
            SELECT id, name, text, time, user
            FROM bilei
            WHERE session_id=?
            ORDER BY id
            """,
            (self.LEGACY_SESSION_ID,),
        )

    async def migrate_legacy_record(
        self,
        record_id: Any,
        target_session_id: Any,
    ) -> None:
        """把一条历史记录原子地分配给指定的普通会话。"""
        if isinstance(record_id, bool):
            raise ValueError("避雷记录 ID 无效")
        try:
            normalized_record_id = int(str(record_id).strip())
        except (TypeError, ValueError):
            raise ValueError("避雷记录 ID 无效") from None
        if normalized_record_id <= 0:
            raise ValueError("避雷记录 ID 无效")

        session_id = self._normalize_session_id(target_session_id)
        affected = await self._sql_db.execute_affected(
            """
            UPDATE bilei
            SET session_id=?
            WHERE id=? AND session_id=?
            """,
            (session_id, normalized_record_id, self.LEGACY_SESSION_ID),
        )
        if affected != 1:
            raise ValueError("该历史避雷记录不存在或已完成迁移")
        
    def _init_return_data(self) -> Dict[str, Any]:
        """初始化标准的返回数据结构"""
        return {
            "code": 0,
            "msg": "功能函数未执行",
            "data": {}
        }
    

    # --- 业务功能函数 ---
    async def add(
        self,
        session_id: Any,
        name: str,
        text: str,
        user: str,
    ) -> Dict[str, Any]:
        """避雷添加"""
        return_data = self._init_return_data()
        session_id = self._normalize_session_id(session_id)
        
        # 获取系统时间
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 添加数据
        try:
            await self._sql_db.insert(
                "bilei",
                {
                    "session_id": session_id,
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
    

    async def all(self, session_id: Any) -> Dict[str, Any]:
        """避雷查看"""
        return_data = self._init_return_data()
        session_id = self._normalize_session_id(session_id)
        

        # 查询数据
        try:
            data = await self._sql_db.fetch_all(
                """
                SELECT id, name, text, time, user
                FROM bilei
                WHERE session_id=?
                ORDER BY id
                """,
                (session_id,),
            )
        except FileNotFoundError as e:
            logger.error(f"查看避雷失败: {e}")
            return_data["msg"] = "查看避雷失败"
            return return_data

        if not data:
            return_data["msg"] = "当前会话暂无避雷数据"
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
    

    async def select(self, session_id: Any, name: str) -> Dict[str, Any]:
        """避雷查询 名称"""
        return_data = self._init_return_data()
        session_id = self._normalize_session_id(session_id)
        
        # 模糊拼接
        like_name = f"%{name}%"
        # 查询数据
        try:
            data = await self._sql_db.fetch_all(
                """
                SELECT id, name, text, time, user
                FROM bilei
                WHERE session_id=? AND name LIKE ?
                ORDER BY id
                """,
                (session_id, like_name),
            )
        except FileNotFoundError as e:
            logger.error(f"查询避雷失败: {e}")
            return_data["msg"] = "查询避雷失败"
            return return_data

        if not data:
            return_data["msg"] = "当前会话未查询到避雷数据"
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
    

    async def update(
        self,
        session_id: Any,
        id: int,
        name: str,
        text: str,
        user: str,
    ) -> Dict[str, Any]:
        """避雷修改 ID 名称 备注"""
        return_data = self._init_return_data()
        session_id = self._normalize_session_id(session_id)
        
        data = await self._sql_db.select_one(
                "bilei",
                "session_id=? AND id=?",
                (session_id, id),
            )

        if not data:
            return_data["msg"] = "当前会话中不存在该避雷记录"
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
                "session_id=? AND id=?",
                (session_id, id),
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
    

    async def delete(self, session_id: Any, id: int) -> Dict[str, Any]:
        """避雷删除 ID"""
        return_data = self._init_return_data()
        session_id = self._normalize_session_id(session_id)
        
        data = await self._sql_db.select_one(
                "bilei",
                "session_id=? AND id=?",
                (session_id, id),
            )

        if not data:
            return_data["msg"] = "当前会话中不存在该避雷记录"
            return return_data

        # 删除
        try:
            await self._sql_db.delete(
                "bilei",
                "session_id=? AND id=?",
                (session_id, id),
            )

        except FileNotFoundError as e:
            logger.error(f"避雷删除失败: {e}")
            return_data["msg"] = "避雷删除失败"
            return return_data

        return_data["data"] = f"避雷删除成功。ID：{id}"
 
        return_data["code"] = 200
   
        return return_data
