from __future__ import annotations

import asyncio
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
    DEFAULT_MAX_MEMORY_ENTRIES = 256
    DEFAULT_MAX_IMAGE_BYTES = 512 * 1024 * 1024
    MAX_MEMORY_ENTRIES_LIMIT = 100_000
    MAX_IMAGE_MB_LIMIT = 10_240
    STALE_RETENTION_SECONDS = 7 * 24 * 60 * 60
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
        self.max_memory_entries = self.DEFAULT_MAX_MEMORY_ENTRIES
        self.max_image_bytes = self.DEFAULT_MAX_IMAGE_BYTES
        self._memory: OrderedDict[str, tuple[int, int, str]] = OrderedDict()
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
        parts: list[str] = []
        for root in roots:
            path = Path(root)
            if not path.exists():
                continue
            for item in sorted(
                candidate for candidate in path.rglob("*") if candidate.is_file()
            ):
                try:
                    stat = item.stat()
                except OSError:
                    continue
                parts.append(
                    f"{item.relative_to(path)}:{stat.st_size}:{stat.st_mtime_ns}"
                )
        return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()

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
            "CREATE INDEX IF NOT EXISTS idx_image_cache_name ON image_render_cache(cache_name)"
        )
        await self._load_settings()
        await self._load_limits()
        await self.cleanup_expired()
        self._enforce_memory_limit()
        await self._enforce_image_limit()

    async def _load_settings(self):
        rows = await self._sqlite.select_all("cache_settings")
        self._settings = {
            (str(row["cache_type"]), str(row["cache_name"])): int(row["ttl_seconds"])
            for row in rows
        }

    async def _load_limits(self):
        rows = await self._sqlite.select_all("cache_limits")
        limits = {str(row["limit_name"]): int(row["limit_value"]) for row in rows}
        self.max_memory_entries = self._validated_memory_limit(
            limits.get("api_memory_entries", self.DEFAULT_MAX_MEMORY_ENTRIES)
        )
        image_limit_mb = self._validated_image_limit_mb(
            limits.get("image_max_mb", self.DEFAULT_MAX_IMAGE_BYTES // 1024 // 1024)
        )
        self.max_image_bytes = image_limit_mb * 1024 * 1024

    @classmethod
    def _validated_memory_limit(cls, value: Any) -> int:
        if isinstance(value, bool):
            raise ValueError("接口内存缓存条数必须是整数")
        try:
            limit = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("接口内存缓存条数必须是整数") from exc
        if limit < 1 or limit > cls.MAX_MEMORY_ENTRIES_LIMIT:
            raise ValueError("接口内存缓存条数必须在 1 到 100000 之间")
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

    async def set_limits(self, api_memory_entries: Any, image_max_mb: Any):
        memory_limit = self._validated_memory_limit(api_memory_entries)
        image_limit_mb = self._validated_image_limit_mb(image_max_mb)
        for limit_name, limit_value in (
            ("api_memory_entries", memory_limit),
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
        self.max_memory_entries = memory_limit
        self.max_image_bytes = image_limit_mb * 1024 * 1024
        self._enforce_memory_limit()
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
        allow_expired: bool = False,
    ) -> tuple[Any | None, int | None, int | None]:
        now = int(time.time())
        ttl = self.get_ttl("api", endpoint)
        memory = self._memory.get(cache_key)
        if memory is not None:
            created_at, expires_at, payload = memory
            effective_expiry = min(expires_at, created_at + ttl)
            if allow_expired and effective_expiry <= now - self.STALE_RETENTION_SECONDS:
                self._memory.pop(cache_key, None)
            elif allow_expired or effective_expiry > now:
                self._memory.move_to_end(cache_key)
                try:
                    return json.loads(payload), effective_expiry, created_at
                except json.JSONDecodeError:
                    self._memory.pop(cache_key, None)

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
        expires_at = int(row["expires_at"])
        created_at = int(row["created_at"])
        effective_expiry = min(expires_at, created_at + ttl)
        if not allow_expired and effective_expiry <= now:
            return None, effective_expiry, created_at
        if allow_expired and effective_expiry <= now - self.STALE_RETENTION_SECONDS:
            await self._sqlite.delete("api_response_cache", "cache_key=?", (cache_key,))
            return None, effective_expiry, created_at
        try:
            data = json.loads(str(row["payload"]))
        except json.JSONDecodeError:
            await self._sqlite.delete("api_response_cache", "cache_key=?", (cache_key,))
            return None, None, None

        self._remember(cache_key, created_at, expires_at, str(row["payload"]))
        await self._sqlite.execute(
            "UPDATE api_response_cache SET last_accessed_at=? WHERE cache_key=?",
            (now, cache_key),
        )
        return data, effective_expiry, created_at

    def _remember(self, cache_key: str, created_at: int, expires_at: int, payload: str):
        self._memory[cache_key] = (created_at, expires_at, payload)
        self._memory.move_to_end(cache_key)
        self._enforce_memory_limit()

    def _enforce_memory_limit(self):
        while len(self._memory) > self.max_memory_entries:
            self._memory.popitem(last=False)

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
            (cache_key, endpoint, payload, now, expires_at, now),
        )
        self._remember(cache_key, now, expires_at, payload)
        return now

    async def request_api(
        self,
        endpoint: str,
        params: dict[str, Any],
        requester: Callable[[], Awaitable[Any]],
        is_cacheable: Callable[[Any], bool],
        force_refresh: bool = False,
        allow_stale: bool = True,
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
                cached, _, created_at = await self._read_api_payload(cache_key, endpoint)
                if cached is not None:
                    metadata["hit"] = True
                    metadata["created_at"] = created_at
                    metadata["data_hash"] = hashlib.sha256(
                        self._json(cached).encode("utf-8")
                    ).hexdigest()
                    return cached, metadata

            stale, _, stale_created_at = await self._read_api_payload(
                cache_key,
                endpoint,
                allow_expired=True,
            )
            data = await requester()
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
            if stale is not None and allow_stale:
                metadata["hit"] = True
                metadata["stale"] = True
                metadata["created_at"] = stale_created_at
                metadata["data_hash"] = hashlib.sha256(
                    self._json(stale).encode("utf-8")
                ).hexdigest()
                logger.warning(f"JX3API 请求失败，使用过期缓存：{endpoint}")
                return stale, metadata
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
                "image-request:v2",
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
        self._memory = OrderedDict(
            (key, value) for key, value in self._memory.items() if value[1] > now
        )
        await self._sqlite.delete(
            "api_response_cache",
            "expires_at<=?",
            (now - self.STALE_RETENTION_SECONDS,),
        )
        rows = await self._sqlite.fetch_all(
            "SELECT cache_key, file_name FROM image_render_cache WHERE expires_at<=?",
            (now,),
        )
        for row in rows:
            await self._delete_image_record(
                str(row["cache_key"]),
                self.image_dir / str(row["file_name"]),
            )

    async def clear(self, cache_type: str) -> dict[str, int]:
        if cache_type not in {"api", "image", "all"}:
            raise ValueError("清理类型仅支持 api、image 或 all")
        removed = {"api": 0, "image": 0}
        if cache_type in {"api", "all"}:
            row = await self._sqlite.fetch_one(
                "SELECT COUNT(*) AS count FROM api_response_cache"
            )
            removed["api"] = int((row or {}).get("count") or 0)
            await self._sqlite.execute("DELETE FROM api_response_cache")
            self._memory.clear()
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
                self._memory.pop(str(row["cache_key"]), None)
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
                "api_memory_entries": self.max_memory_entries,
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
                "api_memory_limit": self.max_memory_entries,
                "image_count": int((image_row or {}).get("count") or 0),
                "image_size_bytes": int((image_row or {}).get("size_bytes") or 0),
                "image_limit_bytes": self.max_image_bytes,
            },
        }
