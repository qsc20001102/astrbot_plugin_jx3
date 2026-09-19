# pyright: reportOptionalMemberAccess=false

import asyncio
from contextlib import asynccontextmanager

import aiosqlite
from typing import Any, Dict, List, Optional, Tuple


class AsyncSQLiteDB:
    def __init__(self, db_path: str = "data.db"):
        self.db_path = db_path
        self.conn: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()
        self._owner = None
        self._transaction_depth = 0
        

    # ======================
    # 生命周期
    # ======================
    
    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

    async def connect(self):
        async with self._serialized():
            if self.conn is None:
                self.conn = await aiosqlite.connect(self.db_path)
                self.conn.row_factory = aiosqlite.Row

    async def close(self):
        async with self._serialized():
            if self.conn:
                await self.conn.close()
                self.conn = None

    @asynccontextmanager
    async def _serialized(self):
        """同一任务可重入，其他任务必须等待整个事务结束（包括读取）。"""
        task = asyncio.current_task()
        if self._owner is task:
            yield
            return
        async with self._lock:
            self._owner = task
            try:
                yield
            finally:
                self._owner = None

    @asynccontextmanager
    async def transaction(self):
        """连接级事务；嵌套调用使用保存点，取消任务时也回滚。"""
        async with self._serialized():
            nested = self._transaction_depth > 0
            savepoint = f"nested_{self._transaction_depth}"
            self._transaction_depth += 1
            try:
                async with self.conn.execute(
                    f"SAVEPOINT {savepoint}" if nested else "BEGIN IMMEDIATE"
                ):
                    pass
                yield
                if nested:
                    async with self.conn.execute(f"RELEASE SAVEPOINT {savepoint}"):
                        pass
                else:
                    await self.conn.commit()
            except BaseException:
                if nested:
                    async with self.conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}"):
                        pass
                    async with self.conn.execute(f"RELEASE SAVEPOINT {savepoint}"):
                        pass
                else:
                    await self.conn.rollback()
                raise
            finally:
                self._transaction_depth -= 1

    # ======================
    # 基础执行
    # ======================

    async def execute(self, sql: str, params: Tuple = ()):
        await self.execute_affected(sql, params)

    async def execute_affected(self, sql: str, params: Tuple = ()) -> int:
        """执行写入语句并返回受影响的行数。"""
        async with self.transaction():
            async with self.conn.execute(sql, params) as cursor:
                return cursor.rowcount

    async def execute_insert(self, sql: str, params: Tuple = ()) -> int:
        """执行插入并返回 ID，游标和提交由数据库层统一管理。"""
        async with self.transaction():
            async with self.conn.execute(sql, params) as cursor:
                return cursor.lastrowid

    async def execute_transaction(
        self,
        statements: List[Tuple[str, Tuple[Any, ...]]],
    ):
        """在同一事务内顺序执行多条参数化 SQL。"""
        async with self.transaction():
            for sql, params in statements:
                async with self.conn.execute(sql, params):
                    pass

    async def fetch_one(self, sql: str, params: Tuple = ()) -> Optional[Dict[str, Any]]:
        async with self._serialized(), self.conn.execute(sql, params) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def fetch_all(self, sql: str, params: Tuple = ()) -> List[Dict[str, Any]]:
        async with self._serialized(), self.conn.execute(sql, params) as cursor:
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
