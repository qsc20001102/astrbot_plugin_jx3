from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from astrbot.api.event import AstrMessageEvent
    from astrbot.api.star import Context

logger = logging.getLogger(__name__)


class TeamBlacklistError(RuntimeError):
    """Raised when a team blacklist recommendation cannot be generated."""


class TeamBlacklistService:
    """Generate one team-member blacklist recommendation through AstrBot LLMs."""

    DEFAULT_PROMPT = (
        "你是剑网3团队管理助手。请从团队成员中选择一名加入团队黑本。"
        "必须且只能选择团队数据中真实存在的一个角色，并严格使用以下格式回复：\n"
        "角色名：角色名称\n"
        "理由：简短明确的理由\n"
        "理由需要结合该成员的心法、职责或老板标记，不要编造团队数据中不存在的信息，"
        "也不要输出其他内容。"
    )

    _ROLE_LABELS = {"T": "T", "HEALER": "奶", "DPS": "DPS"}

    def __init__(self, context: Context, config: dict[str, Any] | None = None):
        self.context = context
        self.config = config if isinstance(config, dict) else {}

    def _build_prompt(self, team: dict[str, Any]) -> str:
        configured_prompt = str(self.config.get("blacklist_prompt") or "").strip()
        instruction = configured_prompt or self.DEFAULT_PROMPT
        status = "报名中" if team["registration_open"] else "未开放报名"
        lines = [
            instruction,
            "",
            "以下为本次唯一可用的团队数据：",
            f"团队编号：{team['id']}",
            f"团队名称：{team['name']}",
            f"团队状态：{status}",
            f"团队人数：{team['member_count']}/{team['capacity']}",
            f"团队公告：{team.get('announcement') or '无'}",
            "团队成员：",
        ]
        for member in team["members"]:
            responsibility = (
                "老板"
                if member["is_boss"]
                else self._ROLE_LABELS.get(str(member.get("role_type")), "DPS")
            )
            lines.append(
                f"- 位置{member['slot_number']}；角色名={member['role_name']}；"
                f"心法={member['kungfu']}；职责={responsibility}"
            )
        return "\n".join(lines)

    def _resolve_provider(self, event: AstrMessageEvent):
        provider_id = str(self.config.get("blacklist_provider") or "").strip()
        if provider_id:
            provider = self.context.get_provider_by_id(provider_id)
            if provider is None:
                raise TeamBlacklistError(
                    "团队黑本配置的模型不存在，请在插件配置中重新选择。"
                )
            if not any(item is provider for item in self.context.get_all_providers()):
                raise TeamBlacklistError(
                    "团队黑本配置的模型不是对话模型，请在插件配置中重新选择。"
                )
            return provider

        provider = self.context.get_using_provider(event.unified_msg_origin)
        if provider is None:
            raise TeamBlacklistError(
                "当前会话没有可用的默认对话模型，请先在 AstrBot 中配置模型。"
            )
        return provider

    async def recommend(
        self,
        event: AstrMessageEvent,
        team: dict[str, Any],
    ) -> str:
        if not team["members"]:
            raise TeamBlacklistError("该团队暂无成员，无法生成团队黑本。")

        provider = self._resolve_provider(event)
        try:
            response = await provider.text_chat(prompt=self._build_prompt(team))
        except Exception as exc:
            logger.exception("团队黑本模型调用失败")
            raise TeamBlacklistError("团队黑本生成失败，请稍后再试。") from exc

        if str(response.role or "").lower() == "err":
            raise TeamBlacklistError("模型返回错误，团队黑本生成失败。")
        answer = str(response.completion_text or "").strip()
        if not answer:
            raise TeamBlacklistError("模型没有返回团队黑本结果，请稍后再试。")
        return answer
