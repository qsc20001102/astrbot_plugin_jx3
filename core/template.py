import asyncio
import re
from pathlib import Path

import aiofiles


_TITLE_PATTERN = re.compile(
    r"\A\{# template-title: (.*?) #\}\r?\n",
)
_PAGE_COMPONENTS_PATTERN = re.compile(
    r"\A\{# template-components: ([a-z0-9 -]+) #\}\r?\n",
)
_COMPONENT_STYLE_PATTERN = re.compile(
    r"/\* @component (?P<name>[a-z0-9-]+) \*/\s*"
    r"(?P<css>.*?)\s*"
    r"/\* @endcomponent \*/",
    re.DOTALL,
)


def secure_render_template(template: str) -> str:
    """显式转义外部数据，不依赖远端截图服务的 Jinja 默认配置。"""
    return "{% autoescape true %}" + template + "{% endautoescape %}"


class TemplateRepository:
    """将公共布局、设计系统和页面片段组装为完整 Jinja 模板。"""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self._cache: dict[str, str] = {}
        self._shared_assets: tuple[str, str, str, str] | None = None
        self._lock = asyncio.Lock()

    async def _read(self, path: Path) -> str:
        async with aiofiles.open(path, "r", encoding="utf-8") as file:
            return await file.read()

    def _page_path(self, template_name: str) -> Path:
        name = Path(template_name)
        if name.name != template_name or name.suffix.lower() != ".html":
            raise ValueError(f"非法模板名称: {template_name}")
        return self.root / "pages" / name.name

    @staticmethod
    def _select_component_styles(source: str, requested: set[str]) -> str:
        """从单一组件样式表中挑选当前页面声明的组件块。"""
        matches = list(_COMPONENT_STYLE_PATTERN.finditer(source))
        available = [match.group("name") for match in matches]
        if len(available) != len(set(available)):
            raise ValueError("公共组件样式存在重复名称")

        unknown = requested.difference(available)
        if unknown:
            names = ", ".join(sorted(unknown))
            raise ValueError(f"页面声明了不存在的公共组件: {names}")

        return _COMPONENT_STYLE_PATTERN.sub(
            lambda match: match.group("css")
            if match.group("name") in requested
            else "",
            source,
        )

    async def get(self, template_name: str) -> str:
        """读取并缓存组装后的完整模板字符串。"""
        cached = self._cache.get(template_name)
        if cached is not None:
            return cached

        async with self._lock:
            cached = self._cache.get(template_name)
            if cached is not None:
                return cached

            page_path = self._page_path(template_name)
            if not page_path.exists():
                # 兼容迁移期间尚未拆分的旧模板。
                legacy_path = self.root / template_name
                if not legacy_path.exists():
                    raise FileNotFoundError(f"模板文件不存在: {page_path}")
                template = await self._read(legacy_path)
                self._cache[template_name] = template
                return template

            if self._shared_assets is None:
                self._shared_assets = tuple(
                    await asyncio.gather(
                        self._read(self.root / "layouts" / "base.html"),
                        self._read(self.root / "styles" / "tokens.css"),
                        self._read(self.root / "styles" / "base.css"),
                        self._read(self.root / "styles" / "components.css"),
                    )
                )

            base, tokens, base_css, component_source = self._shared_assets
            page_css_path = self.root / "styles" / "pages" / f"{page_path.stem}.css"
            if page_css_path.exists():
                page, page_css = await asyncio.gather(
                    self._read(page_path),
                    self._read(page_css_path),
                )
            else:
                page = await self._read(page_path)
                page_css = ""

            title_match = _TITLE_PATTERN.match(page)
            title = title_match.group(1).strip() if title_match else "剑网三数据查询"
            content = _TITLE_PATTERN.sub("", page, count=1)
            component_match = _PAGE_COMPONENTS_PATTERN.match(content)
            requested_components = (
                set(component_match.group(1).split()) if component_match else set()
            )
            content = _PAGE_COMPONENTS_PATTERN.sub("", content, count=1)
            components = self._select_component_styles(
                component_source,
                requested_components,
            )

            template = (
                base.replace("__PAGE_ID__", page_path.stem)
                .replace("<!--__PAGE_TITLE__-->", title)
                .replace("/*__TOKENS_CSS__*/", tokens)
                .replace("/*__BASE_CSS__*/", base_css)
                .replace("/*__PAGE_CSS__*/", page_css)
                .replace("/*__COMPONENTS_CSS__*/", components)
                .replace("<!--__PAGE_CONTENT__-->", content)
            )

            unresolved = (
                "__PAGE_ID__",
                "<!--__PAGE_TITLE__-->",
                "/*__TOKENS_CSS__*/",
                "/*__BASE_CSS__*/",
                "/*__PAGE_CSS__*/",
                "/*__COMPONENTS_CSS__*/",
                "<!--__PAGE_CONTENT__-->",
            )
            if any(marker in template for marker in unresolved):
                raise ValueError(f"模板组装失败，存在未替换标记: {template_name}")

            self._cache[template_name] = template
            return template

    def clear(self) -> None:
        """清理内存缓存，主要用于开发和测试。"""
        self._cache.clear()
        self._shared_assets = None


_TEMPLATE_ROOT = Path(__file__).parent.parent / "templates"
_TEMPLATE_REPOSITORY = TemplateRepository(_TEMPLATE_ROOT)


async def load_template(template_name: str) -> str:
    return await _TEMPLATE_REPOSITORY.get(template_name)
