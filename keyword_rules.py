"""关键词到追加 Prompt 的匹配规则。

纯函数实现，不依赖插件运行时；plugin.py 从配置取值后调用。
"""

from __future__ import annotations

from typing import Any


def match_keyword_prompt(
    text: str,
    rules: list[dict[str, Any]],
    *,
    case_sensitive: bool,
    match_strategy: str,
) -> tuple[str, str]:
    """按关键词规则挑选要追加的领域 Prompt。

    Args:
        text: 待匹配的用户文本。
        rules: 规则列表，每项含 keywords、prompt、priority。
        case_sensitive: 是否区分大小写。
        match_strategy: first 取第一个命中，highest 取优先级最高，merge 合并全部命中。

    Returns:
        tuple[str, str]: (追加 Prompt, 命中的关键词)；没有命中时返回 ("", "")。
    """

    content = (text or "").strip()
    if not content or not rules:
        return "", ""

    probe = content if case_sensitive else content.lower()
    matched: list[dict[str, Any]] = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        prompt = str(rule.get("prompt") or "").strip()
        keywords = rule.get("keywords")
        if not prompt or not isinstance(keywords, list):
            continue
        for keyword in keywords:
            if not isinstance(keyword, str) or not keyword.strip():
                continue
            needle = keyword if case_sensitive else keyword.lower()
            if needle in probe:
                matched.append(
                    {
                        "prompt": prompt,
                        "priority": int(rule.get("priority") or 0),
                        "keyword": keyword,
                    }
                )
                break

    if not matched:
        return "", ""

    if match_strategy == "first":
        return matched[0]["prompt"], matched[0]["keyword"]

    matched.sort(key=lambda item: item["priority"], reverse=True)
    if match_strategy == "merge":
        prompts: list[str] = []
        for item in matched:
            if item["prompt"] not in prompts:
                prompts.append(item["prompt"])
        return " ".join(prompts), matched[0]["keyword"]

    return matched[0]["prompt"], matched[0]["keyword"]
