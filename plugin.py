"""麦麦细说插件 (Detailed Explanation Plugin)。

MaiBot 1.x（maibot_sdk）适配版：用户需要长文解释时直连模型生成结构化长文，
再按段落智能切分、逐段发送，同时保留麦麦的人设与表达风格。
"""

from __future__ import annotations

from typing import Any, Literal

from maibot_sdk import CONFIG_RELOAD_SCOPE_SELF, Command, Field, HookHandler, MaiBotPlugin, PluginConfigBase, Tool
from maibot_sdk.types import HookMode, HookOrder, ToolParameterInfo, ToolParamType

import asyncio
import random
import re
import time

from .keyword_rules import match_keyword_prompt
from .segmentation import DEFAULT_SENTENCE_SEPARATORS, split_content_into_segments

DEFAULT_ACTIVATION_KEYWORDS: list[str] = [
    "详细",
    "科普",
    "解释",
    "说明",
    "原理",
    "深入",
    "具体",
    "详细说说",
    "展开讲讲",
    "多讲讲",
    "详细介绍",
    "深入分析",
    "详细阐述",
    "深度解析",
    "请详细",
    "请展开",
]

# 命中这些词时认为问题涉及时效或事实细节，auto 模式下才值得联网
SEARCH_AUTO_HINTS: list[str] = [
    "为什么",
    "怎么",
    "如何",
    "最新",
    "近期",
    "新闻",
    "更新",
    "发布",
    "爆料",
    "评测",
    "对比",
    "性能",
    "配置",
    "参数",
]

STRUCTURE_INSTRUCTION = (
    "请提供详细、完整的解释，不受字数限制。"
    "请按“概览 → 核心概念 → 工作原理或流程 → 关键要点与易错点 → 案例与对比 → 局限与常见误区 → 延伸阅读”的结构展开，"
    "每个小节都要给出充足的信息与示例，必要时使用小标题与列表。保持逻辑性和条理性，用中文输出。"
)

EXPAND_INSTRUCTION = (
    "在上文基础上继续详细展开，不要重复已经写过的内容。补充更多背景、细节、案例与类比，"
    "并加入“常见问题与解答”与“实践建议”两个小节。"
)

LOW_VALUE_REPLIES = {
    "嗯",
    "哦",
    "噢",
    "啊",
    "哈",
    "好",
    "好的",
    "行",
    "可以",
    "收到",
    "ok",
    "OK",
}


# ─── 配置模型 ────────────────────────────────────────────────────────


class PluginSectionConfig(PluginConfigBase):
    """插件自身开关与配置版本。"""

    __ui_label__ = "插件信息"
    __ui_icon__ = "extension"
    __ui_order__ = 0

    enabled: bool = Field(default=True, description="是否启用本插件")
    config_version: str = Field(default="2.0.0", description="配置文件版本，由插件维护")


class DetailedExplanationSection(PluginConfigBase):
    """长文生成与发送节奏。"""

    __ui_label__ = "长文生成"
    __ui_icon__ = "article"
    __ui_order__ = 1

    enable: bool = Field(default=True, description="是否启用详细解释功能")
    max_total_length: int = Field(default=3000, ge=200, description="长文最大字符数，超出部分截断")
    min_total_length: int = Field(default=200, ge=0, description="长文最小字符数，不足时自动扩写，最多两次")
    segment_length: int = Field(default=400, ge=50, description="单段目标字符数")
    min_segments: int = Field(default=1, ge=1, description="最少分段数，低于此值则整段发送")
    max_segments: int = Field(default=4, ge=1, description="最多分段数，超出的段会合并到最后一段")
    send_delay: float = Field(default=1.5, ge=0.0, description="分段之间发送间隔（秒）")
    show_progress: bool = Field(default=True, description="分段消息是否带 (1/3) 形式的进度前缀")
    show_start_hint: bool = Field(default=True, description="生成前是否先发一条开场提示")
    start_hint_message: str = Field(default="让我详细说明一下...", description="开场提示文案")


class ActivationSection(PluginConfigBase):
    """自动触发方式。"""

    __ui_label__ = "触发方式"
    __ui_icon__ = "touch_app"
    __ui_order__ = 2

    activation_mode: Literal["llm_judge", "keyword", "always", "random", "never"] = Field(
        default="llm_judge",
        description="llm_judge=由模型决定是否调用工具；keyword=命中关键词直接触发；always=每条消息触发；random=按概率触发；never=只保留手动命令",
    )
    activation_probability: float = Field(default=0.1, ge=0.0, le=1.0, description="random 模式的触发概率")
    strict_mode: bool = Field(default=False, description="关键词匹配是否区分大小写")
    custom_keywords: list[str] = Field(default_factory=list, description="追加的触发关键词")


class ContentGenerationSection(PluginConfigBase):
    """模型与联网增强。"""

    __ui_label__ = "内容生成"
    __ui_icon__ = "auto_awesome"
    __ui_order__ = 3

    model_task: str = Field(default="replyer", description="生成长文使用的模型任务名，对应 model_config.toml 的 model_task_config")
    extra_prompt: str = Field(default="", description="追加到结构化提示词末尾的额外要求")
    generation_timeout: float = Field(default=120.0, gt=0.0, description="单次生成的等待上限（秒），扩写同样适用")
    enable_search: bool = Field(default=False, description="是否通过其他插件公开的 API 做联网检索增强")
    search_mode: Literal["auto", "always", "never"] = Field(
        default="auto",
        description="auto=按时效性启发式触发；always=每次生成前都检索；never=从不检索",
    )
    search_api_names: list[str] = Field(
        default_factory=list,
        description="联网检索调用的插件 API 全名，按顺序尝试，例如 search_plugin.web_search；被调用的 API 需接受 query 参数",
    )
    search_timeout: float = Field(default=20.0, gt=0.0, description="单次联网检索的等待上限（秒）")


class SegmentationSection(PluginConfigBase):
    """分段算法。"""

    __ui_label__ = "分段算法"
    __ui_icon__ = "content_cut"
    __ui_order__ = 4

    algorithm: Literal["smart", "sentence", "length"] = Field(
        default="smart",
        description="smart=保持段落完整并超长段落按句切；sentence=按句装段；length=按字符数硬切",
    )
    sentence_separators: list[str] = Field(
        default_factory=lambda: list(DEFAULT_SENTENCE_SEPARATORS),
        description="句末标点集合",
    )
    keep_paragraph_integrity: bool = Field(default=True, description="分段时是否保持段落完整，不跨段切开")
    min_paragraph_length: int = Field(default=50, ge=0, description="段落合并阈值，低于该长度的段落并入后一段")


class KeywordPromptRule(PluginConfigBase):
    """单条关键词与领域 Prompt 的映射规则。"""

    keywords: list[str] = Field(default_factory=list, description="触发关键词，命中任意一个即匹配")
    prompt: str = Field(default="", description="命中后替换默认结构化要求的领域说明")
    priority: int = Field(default=0, description="优先级，数值越大越优先")


def _default_keyword_rules() -> list[KeywordPromptRule]:
    """返回预置的六个领域规则。"""

    return [
        KeywordPromptRule(
            keywords=["技术", "编程", "代码", "算法", "开发", "程序"],
            prompt=(
                "请以技术专家的角度做深入的技术解释。要求："
                "1) 讲清核心原理与实现机制；2) 给出代码示例或伪代码；3) 说明最佳实践与常见陷阱；"
                "4) 对比不同技术方案的优劣；5) 给出实际应用场景。"
            ),
            priority=10,
        ),
        KeywordPromptRule(
            keywords=["历史", "文化", "传统", "古代"],
            prompt=(
                "请从历史文化的角度详细阐述。要求："
                "1) 梳理发展脉络；2) 分析文化背景与社会影响；3) 引用相关史料或文献；"
                "4) 说明当代意义；5) 对比不同时期或地域的差异。"
            ),
            priority=8,
        ),
        KeywordPromptRule(
            keywords=["科学", "物理", "化学", "生物", "实验"],
            prompt=(
                "请以科学的角度做系统解释。要求："
                "1) 阐述科学原理与理论基础；2) 说明实验方法与观察到的现象；3) 引用相关研究与数据；"
                "4) 解释现实应用与影响；5) 指出未解之谜与研究前沿。"
            ),
            priority=9,
        ),
        KeywordPromptRule(
            keywords=["商业", "经济", "市场", "金融", "投资"],
            prompt=(
                "请从商业经济的角度做深入分析。要求："
                "1) 分析市场机制与经济规律；2) 说明商业模式与盈利逻辑；3) 引用行业数据与案例；"
                "4) 评估风险与机遇；5) 提供趋势判断。"
            ),
            priority=7,
        ),
        KeywordPromptRule(
            keywords=["医学", "健康", "疾病", "治疗", "药物"],
            prompt=(
                "请从医学健康的角度做专业解释。要求："
                "1) 说明生理机制与病理原理；2) 介绍诊断方法与治疗手段；3) 引用研究证据；"
                "4) 强调预防措施与注意事项；5) 提醒内容仅供参考，具体问题请咨询专业医生。"
            ),
            priority=9,
        ),
        KeywordPromptRule(
            keywords=["艺术", "设计", "美学", "创作"],
            prompt=(
                "请从艺术审美的角度做深入分析。要求："
                "1) 解读作品特征与表现手法；2) 分析美学理念与创作意图；3) 介绍历史发展与流派风格；"
                "4) 评价价值与影响；5) 启发审美思考。"
            ),
            priority=6,
        ),
    ]


class KeywordPromptsSection(PluginConfigBase):
    """关键词命中的领域 Prompt 规则。"""

    __ui_label__ = "关键词-Prompt 规则"
    __ui_icon__ = "rule"
    __ui_order__ = 5

    enable: bool = Field(default=True, description="是否启用关键词规则")
    case_sensitive: bool = Field(default=False, description="关键词匹配是否区分大小写")
    match_strategy: Literal["first", "highest", "merge"] = Field(
        default="highest",
        description="first=取第一个命中；highest=取优先级最高；merge=合并全部命中的规则",
    )
    rules: list[KeywordPromptRule] = Field(
        default_factory=_default_keyword_rules,
        description="关键词与领域 Prompt 的映射规则列表",
    )


class ConversationContextSection(PluginConfigBase):
    """会话上下文注入。"""

    __ui_label__ = "会话上下文"
    __ui_icon__ = "forum"
    __ui_order__ = 6

    enable: bool = Field(default=True, description="生成前是否摘录最近的对话作为上下文")
    scope: Literal["chat", "user"] = Field(
        default="chat",
        description="chat=取整段会话；user=只取当前用户与机器人的消息，群聊里可减少噪声",
    )
    max_messages: int = Field(default=12, ge=0, description="最多带入的历史消息条数，0 表示不带上下文")
    time_window_seconds: int = Field(default=1800, ge=0, description="回看的时间窗口（秒）")
    max_chars: int = Field(default=1200, ge=200, description="上下文最大字符数")
    per_message_max_chars: int = Field(default=240, ge=50, description="单条历史消息最大字符数，超出截断")
    include_bot_messages: bool = Field(default=True, description="是否包含机器人自己的历史消息")


class DetailedExplanationConfig(PluginConfigBase):
    """麦麦细说插件完整配置。"""

    plugin: PluginSectionConfig = Field(default_factory=PluginSectionConfig)
    detailed_explanation: DetailedExplanationSection = Field(default_factory=DetailedExplanationSection)
    activation: ActivationSection = Field(default_factory=ActivationSection)
    content_generation: ContentGenerationSection = Field(default_factory=ContentGenerationSection)
    segmentation: SegmentationSection = Field(default_factory=SegmentationSection)
    keyword_prompts: KeywordPromptsSection = Field(default_factory=KeywordPromptsSection)
    conversation_context: ConversationContextSection = Field(default_factory=ConversationContextSection)


# ─── 纯函数工具 ──────────────────────────────────────────────────────


def _message_time(message: dict[str, Any]) -> float:
    """读取消息字典中的时间戳（秒）。"""

    try:
        return float(message.get("timestamp"))
    except (TypeError, ValueError):
        return time.time()


def _extract_tokens(text: str) -> set[str]:
    """提取用于相关性打分的词元。"""

    if not text:
        return set()
    return {token.lower() for token in re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}", text) if token}


def _is_low_value_message(text: str) -> bool:
    """判断一条历史消息是否不值得带进上下文。"""

    content = (text or "").strip()
    if not content or len(content) <= 1:
        return True
    if re.fullmatch(r"[\W_]+", content):
        return True
    return content in LOW_VALUE_REPLIES


def _needs_search(query: str) -> bool:
    """auto 模式下判断问题是否涉及时效或事实细节。"""

    return any(hint in query for hint in SEARCH_AUTO_HINTS) or len(query) >= 12


def _normalize_search_result(result: Any) -> str:
    """把联网检索返回值统一成一段文本。"""

    if not result:
        return ""
    if isinstance(result, str):
        return result.strip()
    if isinstance(result, dict):
        for key in ("content", "text", "result", "data", "answer", "summary"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return str(result).strip()
    if isinstance(result, list):
        parts = [_normalize_search_result(item) for item in result]
        return "\n".join(part for part in parts if part).strip()
    return str(result).strip()


def _format_context_block(
    messages: list[Any],
    *,
    max_messages: int,
    max_chars: int,
    per_message_max_chars: int,
    query_text: str,
    current_user_id: str,
    bot_id: str,
    scope: str,
    reply_to_message_id: str,
    exclude_message_id: str,
) -> str:
    """把历史消息摘录成一段紧凑的会话上下文文本。

    Args:
        messages: message.get_by_time_in_chat 返回的消息字典列表。
        max_messages: 最多保留的消息条数。
        max_chars: 上下文文本的字符上限。
        per_message_max_chars: 单条消息的字符上限。
        query_text: 当前问题，用于计算相关性。
        current_user_id: 当前提问用户 ID。
        bot_id: 机器人账号 ID。
        scope: chat 或 user。
        reply_to_message_id: 被引用的消息 ID，优先保留。
        exclude_message_id: 需要排除的当前消息 ID。

    Returns:
        str: 上下文文本；没有可用消息时返回空字符串。
    """

    query_tokens = _extract_tokens(query_text)
    cleaned: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for message in messages:
        if not isinstance(message, dict):
            continue
        if exclude_message_id and str(message.get("message_id") or "") == exclude_message_id:
            continue
        message_info = message.get("message_info") or {}
        user_info = message_info.get("user_info") or {}
        speaker = str(user_info.get("user_nickname") or user_info.get("user_id") or "").strip() or "unknown"
        content = str(message.get("processed_plain_text") or "").strip()
        if _is_low_value_message(content):
            continue
        content = re.sub(r"\s+", " ", content)
        if per_message_max_chars > 0 and len(content) > per_message_max_chars:
            content = content[:per_message_max_chars].rstrip() + "…"
        dedupe_key = (speaker, content)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        cleaned.append(
            {
                "speaker": speaker,
                "content": content,
                "time": _message_time(message),
                "message_id": str(message.get("message_id") or ""),
                "user_id": str(user_info.get("user_id") or ""),
            }
        )

    if not cleaned:
        return ""

    if scope == "user" and current_user_id:
        allowed = {current_user_id}
        if bot_id:
            allowed.add(bot_id)
        cleaned = [item for item in cleaned if item["user_id"] in allowed]
        if not cleaned:
            return ""

    cleaned.sort(key=lambda item: item["time"])

    baseline_tail = min(4, max_messages)
    tail_items = cleaned[-baseline_tail:] if baseline_tail else []
    tail_ids = {item["message_id"] for item in tail_items if item["message_id"]}
    start_time = cleaned[0]["time"]
    span = max(1.0, cleaned[-1]["time"] - start_time)

    for item in cleaned:
        overlap = len(query_tokens & _extract_tokens(item["content"])) if query_tokens else 0
        score = float(overlap) + 0.25 * ((item["time"] - start_time) / span)
        if current_user_id and item["user_id"] == current_user_id:
            score += 0.5
        if bot_id and item["user_id"] == bot_id:
            score += 0.3
        if reply_to_message_id and item["message_id"] == reply_to_message_id:
            score += 1000.0
        if item["message_id"] in tail_ids:
            score += 50.0
        item["score"] = score

    selected: list[dict[str, Any]] = list(tail_items)
    selected_ids = {item["message_id"] for item in tail_items if item["message_id"]}
    remaining = max_messages - len(selected)
    if remaining > 0:
        candidates = [item for item in cleaned if item["message_id"] not in selected_ids]
        candidates.sort(key=lambda item: item["score"], reverse=True)
        selected.extend(candidates[:remaining])
        selected_ids.update(item["message_id"] for item in candidates[:remaining] if item["message_id"])

    if reply_to_message_id and reply_to_message_id not in selected_ids:
        for item in cleaned:
            if item["message_id"] == reply_to_message_id:
                selected.append(item)
                break

    if not selected:
        return ""

    chosen: list[tuple[float, str]] = []
    total_chars = 0
    for item in sorted(selected, key=lambda entry: entry["score"], reverse=True):
        line = f"{item['speaker']}: {item['content']}"
        line_length = len(line) + 1
        if chosen and total_chars + line_length > max_chars:
            continue
        if not chosen and line_length > max_chars:
            line = line[: max(1, max_chars - 1)] + "…"
            line_length = len(line) + 1
        chosen.append((item["time"], line))
        total_chars += line_length

    if not chosen:
        return ""
    chosen.sort(key=lambda entry: entry[0])
    return "[会话上下文 - 最近对话摘录]\n" + "\n".join(line for _, line in chosen)


# ─── 插件主类 ────────────────────────────────────────────────────────


class DetailedExplanationPlugin(MaiBotPlugin):
    """麦麦细说插件。"""

    config_model = DetailedExplanationConfig

    def __init__(self) -> None:
        """初始化后台任务集合。"""

        super().__init__()
        self._background_tasks: set[asyncio.Task[Any]] = set()

    # ─── 生命周期 ───

    async def on_load(self) -> None:
        config = self.config
        self.ctx.logger.info(
            "麦麦细说插件已加载：触发方式=%s，模型任务=%s，分段算法=%s",
            config.activation.activation_mode,
            config.content_generation.model_task,
            config.segmentation.algorithm,
        )

    async def on_unload(self) -> None:
        tasks = list(self._background_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._background_tasks.clear()
        self.ctx.logger.info("麦麦细说插件已卸载")

    async def on_config_update(self, scope: str, config_data: dict[str, Any], version: str) -> None:
        if scope != CONFIG_RELOAD_SCOPE_SELF:
            return
        self.ctx.logger.info("麦麦细说插件配置已更新：version=%s", version)

    # ─── 组件：Tool ───

    @Tool(
        "detailed_explanation",
        brief_description="为用户生成结构化长文解释，并分段发送到当前聊天",
        detailed_description=(
            "当用户明确要求详细解释、科普、深入分析某个主题时调用。"
            "调用后插件会直接把多段长文发送到当前聊天，因此不要再用普通回复复述内容。"
        ),
        parameters=[
            ToolParameterInfo(
                name="topic",
                param_type=ToolParamType.STRING,
                description="要解释的主题或问题",
                required=True,
            ),
            ToolParameterInfo(
                name="context",
                param_type=ToolParamType.STRING,
                description="用户原话、追问方向或已检索到的资料",
                required=False,
            ),
        ],
        core_tool=True,
    )
    async def tool_detailed_explanation(self, topic: str = "", context: str = "", **kwargs: Any) -> dict[str, Any]:
        """生成长文解释并直接分段发送。"""

        stream_id = str(kwargs.get("stream_id") or kwargs.get("chat_id") or "").strip()
        if not stream_id:
            self.ctx.logger.error("调用详细解释工具时缺少 stream_id")
            return {"success": False, "content": "缺少 stream_id，无法发送长文解释"}

        success, segment_count = await self._explain_and_send(
            topic=topic,
            user_text="",
            stream_id=stream_id,
            planner_context=context,
            is_group=bool(kwargs.get("group_id")),
            current_user_id=str(kwargs.get("user_id") or ""),
        )
        if not success:
            return {"success": False, "content": "长文解释生成失败，请稍后重试"}
        return {
            "success": True,
            "content": f"已向当前聊天发送 {segment_count} 段长文解释。",
            "stop_after_execution": True,
        }

    # ─── 组件：Command ───

    @Command(
        "detailed_explanation",
        description="主动触发长文解释：/细说 <主题>",
        pattern=r"^[/／](?:细说|explain|详细|科普)\s*(?P<topic>.*)$",
    )
    async def command_detailed_explanation(self, **kwargs: Any) -> tuple[bool, str, int]:
        """处理 /细说 类命令。"""

        matched_groups = kwargs.get("matched_groups") or {}
        topic = str(matched_groups.get("topic") or "").strip()
        stream_id = str(kwargs.get("stream_id") or "").strip()

        if not self.config.detailed_explanation.enable:
            return True, "详细解释功能已关闭", 1
        if not stream_id:
            self.ctx.logger.error("处理细说命令时缺少 stream_id")
            return False, "缺少 stream_id", 1
        if not topic:
            await self.ctx.send.text("请告诉我你想了解什么，例如：/细说 量子计算", stream_id, set_reply=True)
            return True, "缺少主题", 1

        message = kwargs.get("message") or {}
        message_info = message.get("message_info") or {}
        user_info = message_info.get("user_info") or {}

        success, segment_count = await self._explain_and_send(
            topic=topic,
            user_text="",
            stream_id=stream_id,
            is_group=bool(kwargs.get("group_id")),
            message_time=_message_time(message),
            current_user_id=str(kwargs.get("user_id") or user_info.get("user_id") or ""),
            reply_to_message_id=str(message.get("reply_to") or ""),
            exclude_message_id=str(message.get("message_id") or ""),
        )
        if not success:
            return False, "生成失败", 1
        return True, f"已发送 {segment_count} 段解释", 1

    # ─── 组件：HookHandler ───

    @HookHandler(
        "chat.receive.after_process",
        name="detailed_explanation_auto",
        description="关键词或概率命中后，在后台生成并发送长文解释，并中止本轮消息链路",
        mode=HookMode.BLOCKING,
        order=HookOrder.LATE,
    )
    async def handle_auto_explain(self, **kwargs: Any) -> dict[str, Any]:
        """按 activation 配置决定是否自动触发长文解释。"""

        message = kwargs.get("message")
        if not isinstance(message, dict):
            return {"action": "continue"}
        if not self._auto_trigger_allowed():
            return {"action": "continue"}

        text = str(message.get("processed_plain_text") or "").strip()
        if not text or bool(message.get("is_command")) or text.startswith(("/", "／")):
            return {"action": "continue"}
        if not self._should_trigger(text):
            return {"action": "continue"}

        stream_id = str(message.get("session_id") or "").strip()
        if not stream_id:
            self.ctx.logger.warning("自动触发详细解释时缺少 session_id，已跳过")
            return {"action": "continue"}

        message_info = message.get("message_info") or {}
        user_info = message_info.get("user_info") or {}
        task = asyncio.create_task(
            self._run_auto_explain(
                topic=text,
                user_text=text,
                stream_id=stream_id,
                is_group=bool(message_info.get("group_info")),
                message_time=_message_time(message),
                current_user_id=str(user_info.get("user_id") or ""),
                reply_to_message_id=str(message.get("reply_to") or ""),
                exclude_message_id=str(message.get("message_id") or ""),
            )
        )
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        self.ctx.logger.info("已触发后台长文解释：stream_id=%s", stream_id)
        return {"action": "abort"}

    async def _run_auto_explain(self, **payload: Any) -> None:
        """后台执行自动触发的长文解释，异常只记录日志。"""

        try:
            await self._explain_and_send(**payload)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self.ctx.logger.error("后台长文解释失败：%s", error, exc_info=True)

    # ─── 触发判定 ───

    def _auto_trigger_allowed(self) -> bool:
        """判断自动触发链路是否启用。"""

        if not self.config.plugin.enabled or not self.config.detailed_explanation.enable:
            return False
        return self.config.activation.activation_mode in {"keyword", "always", "random"}

    def _should_trigger(self, text: str) -> bool:
        """按 activation 配置判断本条消息是否触发。"""

        activation = self.config.activation
        mode = activation.activation_mode
        if mode == "always":
            return True
        if mode == "random":
            return random.random() < activation.activation_probability
        if mode != "keyword":
            return False

        keywords = list(DEFAULT_ACTIVATION_KEYWORDS)
        keywords.extend(keyword for keyword in activation.custom_keywords if keyword.strip())
        probe = text if activation.strict_mode else text.lower()
        for keyword in keywords:
            needle = keyword if activation.strict_mode else keyword.lower()
            if needle and needle in probe:
                self.ctx.logger.info("消息命中触发关键词：%s", keyword)
                return True
        return False

    # ─── 生成与发送 ───

    async def _explain_and_send(
        self,
        *,
        topic: str,
        user_text: str,
        stream_id: str,
        planner_context: str = "",
        is_group: bool = False,
        message_time: float | None = None,
        current_user_id: str = "",
        reply_to_message_id: str = "",
        exclude_message_id: str = "",
    ) -> tuple[bool, int]:
        """生成一段长文解释并分段发送。

        Returns:
            tuple[bool, int]: (是否成功, 发送的段数)。
        """

        section = self.config.detailed_explanation
        if not section.enable:
            self.ctx.logger.info("详细解释功能已关闭，跳过生成")
            return False, 0
        if not stream_id:
            self.ctx.logger.error("缺少 stream_id，无法发送长文解释")
            return False, 0

        effective_topic = (topic or user_text or "").strip()
        if not effective_topic:
            self.ctx.logger.warning("没有可用于生成的主题文本，跳过生成")
            return False, 0

        if section.show_start_hint and section.start_hint_message.strip():
            await self.ctx.send.text(section.start_hint_message, stream_id, set_reply=True)
            await asyncio.sleep(0.5)

        content = await self._generate_article(
            topic=effective_topic,
            user_text=user_text,
            stream_id=stream_id,
            planner_context=planner_context,
            is_group=is_group,
            message_time=message_time if message_time is not None else time.time(),
            current_user_id=current_user_id,
            reply_to_message_id=reply_to_message_id,
            exclude_message_id=exclude_message_id,
        )
        if not content:
            await self.ctx.send.text("抱歉，生成详细解释时遇到了问题，请稍后再试", stream_id)
            return False, 0

        segmentation = self.config.segmentation
        segments = split_content_into_segments(
            content,
            segment_length=section.segment_length,
            min_segments=section.min_segments,
            max_segments=section.max_segments,
            algorithm=segmentation.algorithm,
            keep_paragraph_integrity=segmentation.keep_paragraph_integrity,
            min_paragraph_length=segmentation.min_paragraph_length,
            sentence_separators=segmentation.sentence_separators,
        )
        await self._send_segments(segments, stream_id, first_quotes_message=not section.show_start_hint)
        self.ctx.logger.info("长文解释已发送：共 %d 段，主题=%s", len(segments), effective_topic[:40])
        return True, len(segments)

    async def _send_segments(self, segments: list[str], stream_id: str, *, first_quotes_message: bool) -> None:
        """按配置逐段发送长文。"""

        section = self.config.detailed_explanation
        total = len(segments)
        for index, segment in enumerate(segments):
            text = f"({index + 1}/{total}) {segment}" if section.show_progress and total > 1 else segment
            sent = await self.ctx.send.text(
                text,
                stream_id,
                set_reply=first_quotes_message and index == 0,
                typing=index > 0,
            )
            if not sent:
                self.ctx.logger.warning("第 %d/%d 段发送失败", index + 1, total)
            if index < total - 1 and section.send_delay > 0:
                await asyncio.sleep(section.send_delay)

    async def _generate_article(
        self,
        *,
        topic: str,
        user_text: str,
        stream_id: str,
        planner_context: str,
        is_group: bool,
        message_time: float,
        current_user_id: str,
        reply_to_message_id: str,
        exclude_message_id: str,
    ) -> str:
        """组装提示词并生成完整长文，必要时扩写与截断。"""

        generation = self.config.content_generation
        task_name = await self._resolve_model_task(generation.model_task)
        if not task_name:
            return ""

        query_text = (topic or user_text or "").strip()
        instruction = self._build_instruction(query_text)
        style_block = await self._build_style_block()
        context_block = await self._build_context_block(
            stream_id=stream_id,
            message_time=message_time,
            current_user_id=current_user_id,
            reply_to_message_id=reply_to_message_id,
            exclude_message_id=exclude_message_id,
            query_text=query_text,
        )
        search_block = await self._build_search_block(query_text)
        prompt = self._compose_prompt(
            topic=topic,
            user_text=user_text,
            planner_context=planner_context,
            is_group=is_group,
            style_block=style_block,
            instruction=instruction,
            context_block=context_block,
            search_block=search_block,
        )

        timeout = float(generation.generation_timeout)
        content = await self._request_article(prompt, task_name, timeout=timeout)
        if not content:
            return ""

        min_length = max(0, self.config.detailed_explanation.min_total_length)
        retry = 0
        while len(content) < min_length and retry < 2:
            retry += 1
            self.ctx.logger.info("内容偏短（%d < %d），进行第 %d 次扩写", len(content), min_length, retry)
            expand_instruction = EXPAND_INSTRUCTION
            extra_prompt = generation.extra_prompt.strip()
            if extra_prompt:
                expand_instruction = f"{expand_instruction} {extra_prompt}"
            expanded = await self._request_article(
                f"基于以下已写内容继续扩写，不要重复。\n\n已写内容：\n{content}\n\n扩写指令：{expand_instruction}",
                task_name,
                timeout=timeout,
            )
            if not expanded:
                break
            content = f"{content}\n\n{expanded}".strip()

        max_length = max(1, self.config.detailed_explanation.max_total_length)
        if len(content) > max_length:
            self.ctx.logger.warning("长文长度 %d 超过上限 %d，已截断", len(content), max_length)
            content = content[:max_length] + "..."
        return content

    async def _request_article(self, prompt: str, task_name: str, *, timeout: float) -> str:
        """调用模型生成一次文本，失败或超时返回空字符串。"""

        try:
            result = await asyncio.wait_for(self.ctx.llm.generate(prompt, task_name=task_name), timeout=timeout)
        except asyncio.TimeoutError:
            self.ctx.logger.error("长文生成超时：%.0f 秒", timeout)
            return ""
        if not isinstance(result, dict) or not result.get("success"):
            error_text = str(result.get("response") or "") if isinstance(result, dict) else ""
            self.ctx.logger.error("长文生成失败：%s", error_text or "模型未返回内容")
            return ""
        return str(result.get("response") or "").strip()

    async def _resolve_model_task(self, configured: str) -> str:
        """校验配置的模型任务是否可用，不可用时返回空字符串。"""

        task_name = (configured or "").strip() or "replyer"
        available = await self.ctx.llm.get_available_models()
        if not available:
            self.ctx.logger.warning("未能读取可用模型任务列表，直接沿用配置值：%s", task_name)
            return task_name
        if task_name in available:
            return task_name
        self.ctx.logger.error(
            "配置的模型任务 %s 不在可用任务 %s 中，请检查 content_generation.model_task",
            task_name,
            available,
        )
        return ""

    # ─── 提示词组装 ───

    async def _build_style_block(self) -> str:
        """从全局 bot 配置中读取人设与表达风格。"""

        bot_name = str(await self.ctx.config.get("bot.nickname", "") or "").strip()
        alias_names = await self.ctx.config.get("bot.alias_names", [])
        alias_text = ""
        if isinstance(alias_names, list):
            cleaned_aliases = [str(name).strip() for name in alias_names if str(name).strip()]
            if cleaned_aliases:
                alias_text = "，也有人叫你" + "、".join(cleaned_aliases)
        persona = str(await self.ctx.config.get("personality.personality", "") or "").strip()
        reply_style = str(await self.ctx.config.get("personality.reply_style", "") or "").strip()
        plan_style = str(await self.ctx.config.get("personality.plan_style", "") or "").strip()

        lines: list[str] = []
        if bot_name:
            lines.append(f"你的名字是{bot_name}{alias_text}。")
        if persona:
            lines.append(f"身份与人设：{persona}")
        if reply_style:
            lines.append(f"表达风格：{reply_style}")
        if plan_style:
            lines.append(f"行为风格：{plan_style}")
        return "\n".join(lines)

    def _build_instruction(self, query_text: str) -> str:
        """按关键词规则挑选领域要求，并拼接额外要求。"""

        prompts_section = self.config.keyword_prompts
        instruction = STRUCTURE_INSTRUCTION
        if prompts_section.enable and prompts_section.rules:
            rules = [rule.model_dump() for rule in prompts_section.rules]
            custom_prompt, keyword = match_keyword_prompt(
                query_text,
                rules,
                case_sensitive=prompts_section.case_sensitive,
                match_strategy=prompts_section.match_strategy,
            )
            if custom_prompt:
                self.ctx.logger.info("命中关键词规则（%s），使用对应的领域要求", keyword)
                instruction = custom_prompt
        extra_prompt = self.config.content_generation.extra_prompt.strip()
        if extra_prompt:
            instruction = f"{instruction} {extra_prompt}"
        return instruction

    def _compose_prompt(
        self,
        *,
        topic: str,
        user_text: str,
        planner_context: str,
        is_group: bool,
        style_block: str,
        instruction: str,
        context_block: str,
        search_block: str,
    ) -> str:
        """把各个段落拼成最终提示词。"""

        parts: list[str] = [
            "你现在是一个专业的讲解员，负责为用户做深入、系统的科普与解释。",
            f"对话场景：{'群聊' if is_group else '私聊'}。",
            style_block,
            context_block,
        ]
        if planner_context:
            parts.append(f"[补充上下文]\n{planner_context}")
        if topic and topic != user_text:
            parts.append(f"用户想了解的主题：{topic}")
        parts.append(search_block)
        parts.append(f"用户消息：{user_text or topic}\n\n请基于用户的真实意图进行回答。{instruction}")
        return "\n\n".join(part for part in parts if part and part.strip())

    async def _build_context_block(
        self,
        *,
        stream_id: str,
        message_time: float,
        current_user_id: str,
        reply_to_message_id: str,
        exclude_message_id: str,
        query_text: str,
    ) -> str:
        """拉取并摘录最近的对话，作为生成时的上下文。"""

        section = self.config.conversation_context
        if not section.enable or not stream_id or section.max_messages <= 0:
            return ""

        window = max(0, section.time_window_seconds)
        start_time = max(0.0, message_time - window) if window else 0.0
        raw_messages = await self.ctx.message.get_by_time_in_chat(
            chat_id=stream_id,
            start_time=start_time,
            end_time=message_time,
            limit=max(1, section.max_messages * 4),
            limit_mode="latest",
            filter_mai=not section.include_bot_messages,
            filter_command=True,
        )
        if not isinstance(raw_messages, list) or not raw_messages:
            return ""

        bot_id = str(await self.ctx.config.get("bot.qq_account", "") or "").strip()
        return _format_context_block(
            raw_messages,
            max_messages=section.max_messages,
            max_chars=section.max_chars,
            per_message_max_chars=section.per_message_max_chars,
            query_text=query_text,
            current_user_id=current_user_id,
            bot_id=bot_id,
            scope=section.scope,
            reply_to_message_id=reply_to_message_id,
            exclude_message_id=exclude_message_id,
        )

    async def _build_search_block(self, query: str) -> str:
        """按配置调用其他插件公开的检索 API，拼出联网摘要。"""

        generation = self.config.content_generation
        if not generation.enable_search or not query:
            return ""
        if generation.search_mode == "never":
            return ""
        if generation.search_mode == "auto" and not _needs_search(query):
            return ""

        api_names = [name.strip() for name in generation.search_api_names if name and name.strip()]
        if not api_names:
            self.ctx.logger.warning("已开启联网增强但未配置 search_api_names，跳过检索")
            return ""

        for api_name in api_names:
            try:
                raw = await asyncio.wait_for(
                    self.ctx.api.call(api_name, query=query[:200]),
                    timeout=generation.search_timeout,
                )
            except asyncio.TimeoutError:
                self.ctx.logger.warning("联网 API %s 超时（%.0f 秒）", api_name, generation.search_timeout)
                continue
            except Exception as error:
                self.ctx.logger.warning("调用联网 API %s 失败：%s", api_name, error)
                continue
            content = _normalize_search_result(raw)
            if content:
                self.ctx.logger.info("已通过 %s 获取联网检索结果：%d 字", api_name, len(content))
                return (
                    f"[联网检索摘要]\n{content}\n\n"
                    "请在保证准确性的前提下吸收以上信息；与常识冲突时以检索结果为准，不要凭空推测。"
                )
        return ""


def create_plugin() -> DetailedExplanationPlugin:
    """Runner 加载插件时调用的工厂函数。"""

    return DetailedExplanationPlugin()
