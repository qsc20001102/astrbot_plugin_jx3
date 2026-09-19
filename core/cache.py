from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import os
import shutil
import time
import weakref
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Iterable
from contextvars import ContextVar, Token
from pathlib import Path
from typing import Any

from astrbot.api import logger

from .sqlite import AsyncSQLiteDB

API_ENDPOINTS: tuple[str, ...] = (
    "/active/calendar",
    "/active/celebs",
    "/arena/awesome",
    "/arena/recent",
    "/arena/schools",
    "/auction/records",
    "/battle/records",
    "/card/cached",
    "/card/random",
    "/card/records",
    "/castle/status",
    "/chat/records",
    "/chitu/records",
    "/chitu/week/records",
    "/duowan/statistics",
    "/event/collect",
    "/event/missing",
    "/event/recent",
    "/event/records",
    "/event/statistics",
    "/exam/search",
    "/fenxian/records",
    "/firework/records",
    "/food/list",
    "/fraud/detail",
    "/home/flower",
    "/home/furniture",
    "/home/travel",
    "/mech/decrypt",
    "/mentor/search",
    "/monster/records",
    "/monster/weekly",
    "/news/announce",
    "/news/records",
    "/raid/records",
    "/ranch/chat",
    "/ranch/records",
    "/rank/arena",
    "/rank/championship",
    "/rank/constable",
    "/rank/outlaw",
    "/rank/statistics",
    "/rank/trials",
    "/rank/wanted",
    "/recruit/search",
    "/reward/statistics",
    "/role/achievement",
    "/role/detail",
    "/sand/records",
    "/saohua/answer",
    "/saohua/content",
    "/saohua/context",
    "/saohua/drink",
    "/saohua/eat",
    "/saohua/random",
    "/saohua/zhanan",
    "/school/matrix",
    "/school/seniority",
    "/school/skills",
    "/school/talent",
    "/server/status/check",
    "/skill/rework",
    "/steed/records",
    "/tieba/item/records",
    "/tieba/random",
    "/trade/demon",
    "/trade/manufacture",
    "/trade/records",
    "/trade/wanbaolou",
    "/tuilan/achievement",
    "/wicked/records",
)


class CacheService:
    """持久化接口 JSON 与 HTML 渲染图片，并提供 WebUI 配置。"""

    DEFAULT_API_TTL = 300
    DEFAULT_IMAGE_TTL = 600
    MAX_TTL_SECONDS = 30 * 24 * 60 * 60
    DEFAULT_MAX_MEMORY_BYTES = 16 * 1024 * 1024
    DEFAULT_MAX_API_ENTRIES = 256
    DEFAULT_MAX_IMAGE_BYTES = 512 * 1024 * 1024
    MAX_MEMORY_MB_LIMIT = 1024
    MAX_API_ENTRIES_LIMIT = 100_000
    MAX_IMAGE_MB_LIMIT = 10_240
    CLEANUP_INTERVAL_SECONDS = 60
    _SENSITIVE_KEYS = frozenset(
        {"token", "ticket", "authorization", "access_token", "jx3api_token"}
    )
    _NO_CACHE_API_DEFAULTS = frozenset(
        {
            "/card/random",
            "/saohua/answer",
            "/saohua/content",
            "/saohua/context",
            "/saohua/drink",
            "/saohua/eat",
            "/saohua/random",
            "/saohua/zhanan",
            "/tieba/random",
        }
    )

    def __init__(
        self,
        sqlite: AsyncSQLiteDB,
        image_dir: Path,
        asset_roots: Iterable[Path] = (),
    ):
        self._sqlite = sqlite
        self.image_dir = Path(image_dir)
        self._settings: dict[tuple[str, str], int] = {}
        self.max_memory_bytes = self.DEFAULT_MAX_MEMORY_BYTES
        self.max_api_entries = self.DEFAULT_MAX_API_ENTRIES
        self.max_image_bytes = self.DEFAULT_MAX_IMAGE_BYTES
        self._memory: OrderedDict[str, tuple[int, int, bytes, int]] = OrderedDict()
        self._memory_size_bytes = 0
        self._api_storage_lock = asyncio.Lock()
        self._cleanup_task: asyncio.Task | None = None
        self._api_locks: weakref.WeakValueDictionary[str, asyncio.Lock] = (
            weakref.WeakValueDictionary()
        )
        self._image_locks: weakref.WeakValueDictionary[str, asyncio.Lock] = (
            weakref.WeakValueDictionary()
        )
        self._command_context: ContextVar[tuple[str, str]] = ContextVar(
            "jx3_cache_command_context",
            default=("", ""),
        )
        self._image_names: set[str] = set()
        self._asset_signature = self._build_asset_signature(asset_roots)

    @staticmethod
    def _build_asset_signature(roots: Iterable[Path]) -> str:
        signature = hashlib.sha256()
        for root_index, root in enumerate(roots):
            path = Path(root)
            if not path.exists():
                continue
            for item in sorted(
                (candidate for candidate in path.rglob("*") if candidate.is_file()),
                key=lambda candidate: candidate.relative_to(path).as_posix(),
            ):
                try:
                    content_hash = hashlib.sha256()
                    with item.open("rb") as file:
                        while chunk := file.read(1024 * 1024):
                            content_hash.update(chunk)
                except OSError:
                    continue
                relative_path = item.relative_to(path).as_posix()
                signature.update(str(root_index).encode("ascii"))
                signature.update(b"\0")
                signature.update(relative_path.encode("utf-8"))
                signature.update(b"\0")
                signature.update(content_hash.digest())
        return signature.hexdigest()

    async def initialize(self):
        self.image_dir.mkdir(parents=True, exist_ok=True)
        await self._sqlite.execute(
            """
            CREATE TABLE IF NOT EXISTS cache_settings(
                cache_type TEXT NOT NULL,
                cache_name TEXT NOT NULL,
                ttl_seconds INTEGER NOT NULL,
                PRIMARY KEY(cache_type, cache_name)
            )
            """
        )
        await self._sqlite.execute(
            """
            CREATE TABLE IF NOT EXISTS cache_limits(
                limit_name TEXT PRIMARY KEY,
                limit_value INTEGER NOT NULL
            )
            """
        )
        await self._sqlite.execute(
            """
            CREATE TABLE IF NOT EXISTS api_response_cache(
                cache_key TEXT PRIMARY KEY,
                endpoint TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                last_accessed_at INTEGER NOT NULL
            )
            """
        )
        await self._sqlite.execute(
            """
            CREATE TABLE IF NOT EXISTS image_render_cache(
                cache_key TEXT PRIMARY KEY,
                cache_name TEXT NOT NULL,
                file_name TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                last_accessed_at INTEGER NOT NULL,
                message_text TEXT NOT NULL DEFAULT ''
            )
            """
        )
        image_columns = await self._sqlite.fetch_all(
            "PRAGMA table_info(image_render_cache)"
        )
        if "message_text" not in {str(row.get("name")) for row in image_columns}:
            await self._sqlite.execute(
                """
                ALTER TABLE image_render_cache
                ADD COLUMN message_text TEXT NOT NULL DEFAULT ''
                """
            )
        await self._sqlite.execute(
            "CREATE INDEX IF NOT EXISTS idx_api_cache_endpoint ON api_response_cache(endpoint)"
        )
        await self._sqlite.execute(
            "CREATE INDEX IF NOT EXISTS idx_api_cache_lru ON api_response_cache(last_accessed_at)"
        )
        await self._sqlite.execute(
            "CREATE INDEX IF NOT EXISTS idx_image_cache_name ON image_render_cache(cache_name)"
        )
        await self._load_settings()
        await self._load_limits()
        async with self._api_storage_lock:
            await self._enforce_api_limit()
        await self.cleanup_expired()
        await self._enforce_image_limit()
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(
                self._cleanup_loop(), name="jx3-cache-cleanup"
            )

    async def stop(self):
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._cleanup_task
            self._cleanup_task = None

    async def _cleanup_loop(self):
        while True:
            await asyncio.sleep(self.CLEANUP_INTERVAL_SECONDS)
            try:
                await self.cleanup_expired()
            except Exception as exc:
                logger.warning(f"自动清理查询缓存失败：{exc}")

    async def _load_settings(self):
        rows = await self._sqlite.select_all("cache_settings")
        self._settings = {
            (str(row["cache_type"]), str(row["cache_name"])): int(row["ttl_seconds"])
            for row in rows
        }

    async def _load_limits(self):
        rows = await self._sqlite.select_all("cache_limits")
        limits = {str(row["limit_name"]): int(row["limit_value"]) for row in rows}
        memory_limit_mb = self._validated_memory_limit_mb(
            limits.get(
                "api_memory_max_mb",
                self.DEFAULT_MAX_MEMORY_BYTES // 1024 // 1024,
            )
        )
        self.max_memory_bytes = memory_limit_mb * 1024 * 1024
        self.max_api_entries = self._validated_api_entry_limit(
            limits.get(
                "api_max_entries",
                limits.get("api_memory_entries", self.DEFAULT_MAX_API_ENTRIES),
            )
        )
        image_limit_mb = self._validated_image_limit_mb(
            limits.get("image_max_mb", self.DEFAULT_MAX_IMAGE_BYTES // 1024 // 1024)
        )
        self.max_image_bytes = image_limit_mb * 1024 * 1024

    @classmethod
    def _validated_memory_limit_mb(cls, value: Any) -> int:
        if isinstance(value, bool):
            raise ValueError("接口内存缓存容量必须是整数 MB")
        try:
            limit = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("接口内存缓存容量必须是整数 MB") from exc
        if limit < 1 or limit > cls.MAX_MEMORY_MB_LIMIT:
            raise ValueError("接口内存缓存容量必须在 1 到 1024 MB 之间")
        return limit

    @classmethod
    def _validated_api_entry_limit(cls, value: Any) -> int:
        if isinstance(value, bool):
            raise ValueError("SQLite 接口缓存条数必须是整数")
        try:
            limit = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("SQLite 接口缓存条数必须是整数") from exc
        if limit < 1 or limit > cls.MAX_API_ENTRIES_LIMIT:
            raise ValueError("SQLite 接口缓存条数必须在 1 到 100000 之间")
        return limit

    @classmethod
    def _validated_image_limit_mb(cls, value: Any) -> int:
        if isinstance(value, bool):
            raise ValueError("图片缓存容量必须是整数 MB")
        try:
            limit = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("图片缓存容量必须是整数 MB") from exc
        if limit < 1 or limit > cls.MAX_IMAGE_MB_LIMIT:
            raise ValueError("图片缓存容量必须在 1 到 10240 MB 之间")
        return limit

    async def set_limits(
        self,
        api_memory_max_mb: Any,
        api_max_entries: Any,
        image_max_mb: Any,
    ):
        memory_limit_mb = self._validated_memory_limit_mb(api_memory_max_mb)
        api_entry_limit = self._validated_api_entry_limit(api_max_entries)
        image_limit_mb = self._validated_image_limit_mb(image_max_mb)
        for limit_name, limit_value in (
            ("api_memory_max_mb", memory_limit_mb),
            ("api_max_entries", api_entry_limit),
            ("image_max_mb", image_limit_mb),
        ):
            await self._sqlite.execute(
                """
                INSERT INTO cache_limits(limit_name, limit_value)
                VALUES(?, ?)
                ON CONFLICT(limit_name) DO UPDATE SET
                    limit_value=excluded.limit_value
                """,
                (limit_name, limit_value),
            )
        self.max_image_bytes = image_limit_mb * 1024 * 1024
        async with self._api_storage_lock:
            self.max_memory_bytes = memory_limit_mb * 1024 * 1024
            self.max_api_entries = api_entry_limit
            await self._enforce_api_limit()
        await self._enforce_image_limit()

    def register_image_names(self, names: Iterable[str]):
        self._image_names.update(
            str(name).strip() for name in names if str(name).strip()
        )

    def enter_command(self, command_name: str, args: Iterable[Any] = ()) -> Token:
        argument_signature = hashlib.sha256(
            self._json(list(args)).encode("utf-8")
        ).hexdigest()
        return self._command_context.set(
            (str(command_name or "").strip(), argument_signature)
        )

    def leave_command(self, token: Token):
        self._command_context.reset(token)

    def current_command(self) -> str:
        return self._command_context.get()[0]

    def current_command_signature(self) -> str:
        return self._command_context.get()[1]

    def _base_ttl(self, cache_type: str, cache_name: str) -> int:
        if cache_type == "api" and cache_name in self._NO_CACHE_API_DEFAULTS:
            return 0
        # 会话避雷图片默认不缓存，避免修改记录后仍展示旧图；仍可在 WebUI 单独开启。
        if cache_type == "image" and cache_name in {"避雷查看", "避雷查询"}:
            return 0
        return self.DEFAULT_API_TTL if cache_type == "api" else self.DEFAULT_IMAGE_TTL

    def get_ttl(self, cache_type: str, cache_name: str) -> int:
        specific = self._settings.get((cache_type, cache_name))
        if specific is not None:
            return specific
        if cache_type == "api" and cache_name in self._NO_CACHE_API_DEFAULTS:
            return 0
        if cache_type == "image" and cache_name in {"避雷查看", "避雷查询"}:
            return 0
        default = self._settings.get((cache_type, "*"))
        if default is not None:
            return default
        return self._base_ttl(cache_type, cache_name)

    @classmethod
    def _validate_ttl(cls, value: Any) -> int:
        if isinstance(value, bool):
            raise ValueError("缓存时间必须是整数秒")
        try:
            ttl = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("缓存时间必须是整数秒") from exc
        if ttl < 0 or ttl > cls.MAX_TTL_SECONDS:
            raise ValueError("缓存时间必须在 0 到 2592000 秒之间")
        return ttl

    async def set_ttl(
        self,
        cache_type: str,
        cache_name: str,
        ttl_seconds: Any = None,
        inherit: bool = False,
    ):
        if cache_type not in {"api", "image"}:
            raise ValueError("缓存类型仅支持 api 或 image")
        cache_name = str(cache_name or "").strip()
        if not cache_name:
            raise ValueError("缓存项目不能为空")
        if cache_name == "*" and inherit:
            raise ValueError("默认缓存时间不能继承")

        if inherit:
            await self._sqlite.delete(
                "cache_settings",
                "cache_type=? AND cache_name=?",
                (cache_type, cache_name),
            )
            self._settings.pop((cache_type, cache_name), None)
            return

        ttl = self._validate_ttl(ttl_seconds)
        await self._sqlite.execute(
            """
            INSERT INTO cache_settings(cache_type, cache_name, ttl_seconds)
            VALUES(?, ?, ?)
            ON CONFLICT(cache_type, cache_name) DO UPDATE SET
                ttl_seconds=excluded.ttl_seconds
            """,
            (cache_type, cache_name, ttl),
        )
        self._settings[(cache_type, cache_name)] = ttl

    @classmethod
    def _normalized(cls, value: Any, strip_sensitive: bool = False) -> Any:
        if isinstance(value, dict):
            return {
                str(key): cls._normalized(item, strip_sensitive)
                for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
                if not strip_sensitive or str(key).lower() not in cls._SENSITIVE_KEYS
            }
        if isinstance(value, (list, tuple)):
            return [cls._normalized(item, strip_sensitive) for item in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    @classmethod
    def _json(cls, value: Any, strip_sensitive: bool = False) -> str:
        return json.dumps(
            cls._normalized(value, strip_sensitive),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @classmethod
    def build_api_key(cls, endpoint: str, params: dict[str, Any]) -> str:
        source = f"api:v1|{endpoint}|{cls._json(params, strip_sensitive=True)}"
        return hashlib.sha256(source.encode("utf-8")).hexdigest()

    async def _read_api_payload(
        self,
        cache_key: str,
        endpoint: str,
    ) -> tuple[Any | None, int | None, int | None]:
        async with self._api_storage_lock:
            now = time.time()
            ttl = self.get_ttl("api", endpoint)
            memory = self._memory.get(cache_key)
            if memory is not None:
                created_at, expires_at, payload, _ = memory
            else:
                row = await self._sqlite.fetch_one(
                    """
                    SELECT payload, created_at, expires_at
                    FROM api_response_cache
                    WHERE cache_key=? AND endpoint=?
                    """,
                    (cache_key, endpoint),
                )
                if not row:
                    return None, None, None
                created_at = int(row["created_at"])
                expires_at = int(row["expires_at"])
                payload = str(row["payload"])
            effective_expiry = min(expires_at, created_at + ttl)
            try:
                data = (
                    json.loads(payload) if ttl > 0 and effective_expiry > now else None
                )
            except json.JSONDecodeError:
                data = None
            if data is None:
                self._forget_memory(cache_key)
                await self._sqlite.delete(
                    "api_response_cache", "cache_key=?", (cache_key,)
                )
                return None, effective_expiry, created_at

            self._remember(cache_key, created_at, expires_at, payload)
            await self._sqlite.execute(
                "UPDATE api_response_cache SET last_accessed_at=? WHERE cache_key=?",
                (now, cache_key),
            )
            return data, effective_expiry, created_at

    def _remember(
        self,
        cache_key: str,
        created_at: int,
        expires_at: int,
        payload: str | bytes,
    ):
        self._forget_memory(cache_key)
        encoded = payload if isinstance(payload, bytes) else payload.encode("utf-8")
        size_bytes = len(encoded)
        if size_bytes > self.max_memory_bytes:
            return
        self._memory[cache_key] = (created_at, expires_at, encoded, size_bytes)
        self._memory_size_bytes += size_bytes
        self._memory.move_to_end(cache_key)
        self._enforce_memory_limit()

    def _forget_memory(self, cache_key: str):
        removed = self._memory.pop(cache_key, None)
        if removed is not None:
            self._memory_size_bytes -= removed[3]

    def _clear_memory(self):
        self._memory.clear()
        self._memory_size_bytes = 0

    def _retain_memory_keys(self, retained: set[str]):
        self._memory = OrderedDict(
            (key, value) for key, value in self._memory.items() if key in retained
        )
        self._memory_size_bytes = sum(value[3] for value in self._memory.values())

    def _enforce_memory_limit(self):
        while self._memory_size_bytes > self.max_memory_bytes and self._memory:
            _, removed = self._memory.popitem(last=False)
            self._memory_size_bytes -= removed[3]

    async def _enforce_api_limit(self):
        """Enforce memory bytes and SQLite entries while holding the storage lock."""
        self._enforce_memory_limit()
        row = await self._sqlite.fetch_one(
            "SELECT COUNT(*) AS count FROM api_response_cache"
        )
        if int((row or {}).get("count") or 0) <= self.max_api_entries:
            return
        await self._sqlite.execute(
            """
            DELETE FROM api_response_cache WHERE cache_key IN (
                SELECT cache_key FROM api_response_cache
                ORDER BY last_accessed_at DESC, rowid DESC
                LIMIT -1 OFFSET ?
            )
            """,
            (self.max_api_entries,),
        )
        remaining = await self._sqlite.fetch_all(
            "SELECT cache_key FROM api_response_cache"
        )
        retained = {row["cache_key"] for row in remaining}
        self._retain_memory_keys(retained)

    async def _save_api_payload(
        self,
        cache_key: str,
        endpoint: str,
        data: Any,
        ttl_seconds: int,
    ) -> int:
        payload = self._json(data)
        now = int(time.time())
        expires_at = now + ttl_seconds
        async with self._api_storage_lock:
            await self._sqlite.execute(
                """
            INSERT INTO api_response_cache(
                cache_key, endpoint, payload, created_at, expires_at, last_accessed_at
            ) VALUES(?, ?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                endpoint=excluded.endpoint,
                payload=excluded.payload,
                created_at=excluded.created_at,
                expires_at=excluded.expires_at,
                last_accessed_at=excluded.last_accessed_at
            """,
                (cache_key, endpoint, payload, now, expires_at, time.time()),
            )
            self._remember(cache_key, now, expires_at, payload)
            await self._enforce_api_limit()
        return now

    async def request_api(
        self,
        endpoint: str,
        params: dict[str, Any],
        requester: Callable[[], Awaitable[Any]],
        is_cacheable: Callable[[Any], bool],
        force_refresh: bool = False,
    ) -> tuple[Any, dict[str, Any]]:
        ttl = self.get_ttl("api", endpoint)
        cache_key = self.build_api_key(endpoint, params)
        metadata = {
            "endpoint": endpoint,
            "cache_key": cache_key,
            "hit": False,
            "stale": False,
            "ttl_seconds": ttl,
            "data_hash": "",
            "created_at": None,
        }
        if ttl <= 0:
            data = await requester()
            metadata["created_at"] = int(time.time())
            if is_cacheable(data):
                metadata["data_hash"] = hashlib.sha256(
                    self._json(data).encode("utf-8")
                ).hexdigest()
            return data, metadata

        if not force_refresh:
            cached, _, created_at = await self._read_api_payload(cache_key, endpoint)
            if cached is not None:
                metadata["hit"] = True
                metadata["created_at"] = created_at
                metadata["data_hash"] = hashlib.sha256(
                    self._json(cached).encode("utf-8")
                ).hexdigest()
                return cached, metadata

        lock = self._api_locks.setdefault(cache_key, asyncio.Lock())
        async with lock:
            if not force_refresh:
                cached, _, created_at = await self._read_api_payload(
                    cache_key, endpoint
                )
                if cached is not None:
                    metadata["hit"] = True
                    metadata["created_at"] = created_at
                    metadata["data_hash"] = hashlib.sha256(
                        self._json(cached).encode("utf-8")
                    ).hexdigest()
                    return cached, metadata

            data = None
            try:
                data = await requester()
            finally:
                if not is_cacheable(data):
                    async with self._api_storage_lock:
                        self._forget_memory(cache_key)
                        await self._sqlite.delete(
                            "api_response_cache", "cache_key=?", (cache_key,)
                        )
            if is_cacheable(data):
                metadata["data_hash"] = hashlib.sha256(
                    self._json(data).encode("utf-8")
                ).hexdigest()
                try:
                    metadata["created_at"] = await self._save_api_payload(
                        cache_key,
                        endpoint,
                        data,
                        ttl,
                    )
                except Exception as exc:
                    metadata["created_at"] = int(time.time())
                    logger.warning(f"写入接口缓存失败 endpoint={endpoint}: {exc}")
                return data, metadata
            return data, metadata

    def build_image_key(
        self,
        cache_name: str,
        template: str,
        data: dict[str, Any],
        render_options: dict[str, Any],
        source_signature: str = "",
        variant_signature: str = "",
    ) -> str:
        source = "|".join(
            (
                "image:v2",
                cache_name,
                hashlib.sha256(template.encode("utf-8")).hexdigest(),
                source_signature
                or hashlib.sha256(self._json(data).encode("utf-8")).hexdigest(),
                variant_signature,
                self._json(render_options),
                self._asset_signature,
            )
        )
        return hashlib.sha256(source.encode("utf-8")).hexdigest()

    @classmethod
    def value_signature(cls, value: Any) -> str:
        return hashlib.sha256(cls._json(value).encode("utf-8")).hexdigest()

    def build_image_request_key(
        self,
        cache_name: str,
        render_options: dict[str, Any],
        variant_signature: str,
        scope_signature: str = "",
    ) -> str:
        """生成可在请求接口前计算的最终图片缓存键。"""
        source = "|".join(
            (
                "image-request:v3",
                cache_name,
                variant_signature,
                scope_signature,
                self._json(render_options),
                self._asset_signature,
            )
        )
        return hashlib.sha256(source.encode("utf-8")).hexdigest()

    def image_lock(self, cache_key: str) -> asyncio.Lock:
        return self._image_locks.setdefault(cache_key, asyncio.Lock())

    async def get_image_entry(
        self,
        cache_key: str,
        cache_name: str,
    ) -> tuple[Path, str] | None:
        try:
            ttl = self.get_ttl("image", cache_name)
            if ttl <= 0:
                return None
            now = int(time.time())
            row = await self._sqlite.fetch_one(
                """
                SELECT file_name, created_at, expires_at, message_text
                FROM image_render_cache
                WHERE cache_key=? AND cache_name=?
                """,
                (cache_key, cache_name),
            )
            if not row:
                return None
            effective_expiry = min(int(row["expires_at"]), int(row["created_at"]) + ttl)
            path = self.image_dir / str(row["file_name"])
            if effective_expiry <= now or not path.is_file():
                await self._delete_image_record(cache_key, path)
                return None
            await self._sqlite.execute(
                "UPDATE image_render_cache SET last_accessed_at=? WHERE cache_key=?",
                (now, cache_key),
            )
            return path, str(row.get("message_text") or "")
        except Exception as exc:
            logger.warning(f"读取图片缓存失败 cache={cache_name}: {exc}")
            return None

    async def get_image(self, cache_key: str, cache_name: str) -> Path | None:
        entry = await self.get_image_entry(cache_key, cache_name)
        return entry[0] if entry else None

    async def save_image(
        self,
        cache_key: str,
        cache_name: str,
        source_path: str,
        image_format: str,
        message_text: str = "",
    ) -> Path | None:
        ttl = self.get_ttl("image", cache_name)
        source = Path(source_path)
        if ttl <= 0 or not source.is_file():
            return None
        extension = "jpg" if image_format == "jpeg" else "png"
        file_name = f"{cache_key}.{extension}"
        target = self.image_dir / file_name
        temporary = self.image_dir / f".{file_name}.tmp"
        try:
            await asyncio.to_thread(shutil.copy2, source, temporary)
            await asyncio.to_thread(os.replace, temporary, target)
            size_bytes = target.stat().st_size
            now = int(time.time())
            await self._sqlite.execute(
                """
                INSERT INTO image_render_cache(
                    cache_key, cache_name, file_name, size_bytes,
                    created_at, expires_at, last_accessed_at, message_text
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    cache_name=excluded.cache_name,
                    file_name=excluded.file_name,
                    size_bytes=excluded.size_bytes,
                    created_at=excluded.created_at,
                    expires_at=excluded.expires_at,
                    last_accessed_at=excluded.last_accessed_at,
                    message_text=excluded.message_text
                """,
                (
                    cache_key,
                    cache_name,
                    file_name,
                    size_bytes,
                    now,
                    now + ttl,
                    now,
                    str(message_text or ""),
                ),
            )
            await self._enforce_image_limit()
            return target
        except Exception as exc:
            logger.warning(f"保存图片缓存失败 cache={cache_name}: {exc}")
            for path in (temporary, target):
                try:
                    if path.exists():
                        path.unlink()
                except OSError:
                    pass
            return None

    async def _delete_image_record(self, cache_key: str, path: Path):
        await self._sqlite.delete("image_render_cache", "cache_key=?", (cache_key,))
        try:
            if path.is_file() and path.parent.resolve() == self.image_dir.resolve():
                path.unlink()
        except OSError:
            pass

    async def _enforce_image_limit(self):
        row = await self._sqlite.fetch_one(
            "SELECT COALESCE(SUM(size_bytes), 0) AS total FROM image_render_cache"
        )
        total = int((row or {}).get("total") or 0)
        if total <= self.max_image_bytes:
            return
        rows = await self._sqlite.fetch_all(
            """
            SELECT cache_key, file_name, size_bytes
            FROM image_render_cache
            ORDER BY last_accessed_at ASC
            """
        )
        for item in rows:
            if total <= self.max_image_bytes:
                break
            await self._delete_image_record(
                str(item["cache_key"]),
                self.image_dir / str(item["file_name"]),
            )
            total -= int(item["size_bytes"])

    async def cleanup_expired(self):
        now = int(time.time())
        async with self._api_storage_lock:
            uncached_defaults = sorted(self._NO_CACHE_API_DEFAULTS)
            placeholders = ",".join("?" for _ in uncached_defaults)
            await self._sqlite.execute(
                f"""
                DELETE FROM api_response_cache
                WHERE expires_at<=? OR created_at + COALESCE(
                    (SELECT ttl_seconds FROM cache_settings
                     WHERE cache_type='api' AND cache_name=api_response_cache.endpoint),
                    CASE WHEN endpoint IN ({placeholders}) THEN 0 ELSE ? END
                )<=?
                """,
                (now, *uncached_defaults, self.get_ttl("api", "*"), now),
            )
            remaining = await self._sqlite.fetch_all(
                "SELECT cache_key FROM api_response_cache"
            )
            retained = {row["cache_key"] for row in remaining}
            self._retain_memory_keys(retained)
        rows = await self._sqlite.fetch_all(
            "SELECT cache_key, file_name FROM image_render_cache WHERE expires_at<=?",
            (now,),
        )
        for row in rows:
            cache_key = str(row["cache_key"])
            async with self.image_lock(cache_key):
                expired = await self._sqlite.fetch_one(
                    """
                    SELECT file_name FROM image_render_cache
                    WHERE cache_key=? AND expires_at<=?
                    """,
                    (cache_key, now),
                )
                if expired:
                    await self._delete_image_record(
                        cache_key, self.image_dir / str(expired["file_name"])
                    )

    async def clear(self, cache_type: str) -> dict[str, int]:
        if cache_type not in {"api", "image", "all"}:
            raise ValueError("清理类型仅支持 api、image 或 all")
        removed = {"api": 0, "image": 0}
        if cache_type in {"api", "all"}:
            async with self._api_storage_lock:
                row = await self._sqlite.fetch_one(
                    "SELECT COUNT(*) AS count FROM api_response_cache"
                )
                removed["api"] = int((row or {}).get("count") or 0)
                await self._sqlite.execute("DELETE FROM api_response_cache")
                self._clear_memory()
        if cache_type in {"image", "all"}:
            rows = await self._sqlite.fetch_all(
                "SELECT cache_key, file_name FROM image_render_cache"
            )
            removed["image"] = len(rows)
            for row in rows:
                await self._delete_image_record(
                    str(row["cache_key"]),
                    self.image_dir / str(row["file_name"]),
                )
        return removed

    async def clear_item(self, cache_type: str, cache_name: str) -> int:
        if cache_type not in {"api", "image"}:
            raise ValueError("缓存类型仅支持 api 或 image")
        cache_name = str(cache_name or "").strip()
        if not cache_name:
            raise ValueError("缓存项目不能为空")

        if cache_type == "api":
            async with self._api_storage_lock:
                rows = await self._sqlite.fetch_all(
                    "SELECT cache_key FROM api_response_cache WHERE endpoint=?",
                    (cache_name,),
                )
                await self._sqlite.delete(
                    "api_response_cache",
                    "endpoint=?",
                    (cache_name,),
                )
                for row in rows:
                    self._forget_memory(str(row["cache_key"]))
                return len(rows)

        rows = await self._sqlite.fetch_all(
            """
            SELECT cache_key, file_name
            FROM image_render_cache
            WHERE cache_name=?
            """,
            (cache_name,),
        )
        for row in rows:
            await self._delete_image_record(
                str(row["cache_key"]),
                self.image_dir / str(row["file_name"]),
            )
        return len(rows)

    def _setting_item(self, cache_type: str, cache_name: str) -> dict[str, Any]:
        return {
            "name": cache_name,
            "ttl_seconds": self.get_ttl(cache_type, cache_name),
            "overridden": (cache_type, cache_name) in self._settings,
            "safe_default": (
                (
                    (cache_type == "api" and cache_name in self._NO_CACHE_API_DEFAULTS)
                    or (
                        cache_type == "image" and cache_name in {"避雷查看", "避雷查询"}
                    )
                )
                and (cache_type, cache_name) not in self._settings
            ),
        }

    async def dashboard(self) -> dict[str, Any]:
        await self.cleanup_expired()
        api_row = await self._sqlite.fetch_one(
            """
            SELECT COUNT(*) AS count,
                   COALESCE(SUM(LENGTH(CAST(payload AS BLOB))), 0) AS size_bytes
            FROM api_response_cache
            """
        )
        image_row = await self._sqlite.fetch_one(
            """
            SELECT COUNT(*) AS count,
                   COALESCE(SUM(size_bytes), 0) AS size_bytes
            FROM image_render_cache
            """
        )
        known_api_names = set(API_ENDPOINTS)
        known_api_names.update(
            name
            for cache_type, name in self._settings
            if cache_type == "api" and name != "*"
        )
        known_image_names = set(self._image_names)
        known_image_names.update(
            name
            for cache_type, name in self._settings
            if cache_type == "image" and name != "*"
        )
        return {
            "defaults": {
                "api": self.get_ttl("api", "*"),
                "image": self.get_ttl("image", "*"),
            },
            "limits": {
                "api_memory_max_mb": self.max_memory_bytes // 1024 // 1024,
                "api_max_entries": self.max_api_entries,
                "image_max_mb": self.max_image_bytes // 1024 // 1024,
            },
            "api": [
                self._setting_item("api", name) for name in sorted(known_api_names)
            ],
            "images": [
                self._setting_item("image", name)
                for name in sorted(
                    known_image_names, key=lambda value: value.encode("utf-8")
                )
            ],
            "stats": {
                "api_count": int((api_row or {}).get("count") or 0),
                "api_size_bytes": int((api_row or {}).get("size_bytes") or 0),
                "api_memory_count": len(self._memory),
                "api_memory_size_bytes": self._memory_size_bytes,
                "api_memory_limit_bytes": self.max_memory_bytes,
                "api_entry_limit": self.max_api_entries,
                "image_count": int((image_row or {}).get("count") or 0),
                "image_size_bytes": int((image_row or {}).get("size_bytes") or 0),
                "image_limit_bytes": self.max_image_bytes,
            },
        }
