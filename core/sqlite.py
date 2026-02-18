# pyright: reportOptionalMemberAccess=false

import aiosqlite
from typing import Any, Dict, List, Optional, Tuple


class AsyncSQLiteDB:
    def __init__(self, db_path: str = "data.db"):
        self.db_path = db_path
        self.conn: Optional[aiosqlite.Connection] = None
        

    # ======================
    # 生命周期
    # ======================
    
    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

    async def connect(self):
        self.conn = await aiosqlite.connect(self.db_path)
        self.conn.row_factory = aiosqlite.Row

    async def close(self):
        if self.conn:
            await self.conn.close()

    # ======================
    # 基础执行
    # ======================

    async def execute(self, sql: str, params: Tuple = ()):
        async with self.conn.execute(sql, params):
            await self.conn.commit()

    async def fetch_one(self, sql: str, params: Tuple = ()) -> Optional[Dict[str, Any]]:
        async with self.conn.execute(sql, params) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def fetch_all(self, sql: str, params: Tuple = ()) -> List[Dict[str, Any]]:
        async with self.conn.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    # ======================
    # CRUD
    # ======================

    async def insert(self, table: str, data: Dict[str, Any]):
        keys = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        sql = f"INSERT INTO {table} ({keys}) VALUES ({placeholders})"
        await self.execute(sql, tuple(data.values()))

    async def update(self, table: str, data: Dict[str, Any], where: str, params: Tuple):
        set_clause = ", ".join([f"{k}=?" for k in data.keys()])
        sql = f"UPDATE {table} SET {set_clause} WHERE {where}"
        await self.execute(sql, tuple(data.values()) + params)

    async def delete(self, table: str, where: str, params: Tuple):
        sql = f"DELETE FROM {table} WHERE {where}"
        await self.execute(sql, params)

    async def select_one(self, table: str, where: str = "", params: Tuple = ()):
        sql = f"SELECT * FROM {table}"
        if where:
            sql += f" WHERE {where}"
        return await self.fetch_one(sql, params)

    async def select_all(self, table: str, where: str = "", params: Tuple = ()):
        sql = f"SELECT * FROM {table}"
        if where:
            sql += f" WHERE {where}"
        return await self.fetch_all(sql, params)
