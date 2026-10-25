"""关键词规则单元测试。

只依赖 keyword_rules.py 的纯函数，不需要插件运行时或 SDK。
"""

from keyword_rules import match_keyword_prompt

RULES = [
    {"keywords": ["技术", "编程", "代码"], "prompt": "技术专家角度", "priority": 10},
    {"keywords": ["历史", "文化"], "prompt": "历史文化角度", "priority": 8},
    {"keywords": ["科学", "物理"], "prompt": "科学角度", "priority": 9},
    {"keywords": ["Python"], "prompt": "Python 角度", "priority": 4},
]


def _match(text, *, case_sensitive=False, strategy="highest"):
    return match_keyword_prompt(
        text,
        RULES,
        case_sensitive=case_sensitive,
        match_strategy=strategy,
    )


def test_tech_keyword():
    assert _match("详细解释一下编程的核心概念")[0] == "技术专家角度"


def test_history_keyword():
    assert _match("讲讲中国历史上的重要事件")[0] == "历史文化角度"


def test_science_keyword():
    assert _match("物理学中的量子力学原理")[0] == "科学角度"


def test_highest_priority_wins():
    prompt, keyword = _match("讲讲编程的历史发展")
    assert prompt == "技术专家角度"
    assert keyword == "编程"


def test_no_match_returns_empty():
    assert _match("今天天气怎么样") == ("", "")


def test_case_insensitive():
    assert _match("请解释PYTHON 是什么")[0] == "Python 角度"


def test_case_sensitive_still_matches_exact_case():
    assert _match("请解释Python 是什么", case_sensitive=True)[0] == "Python 角度"


def test_first_strategy_uses_declaration_order():
    assert _match("编程的历史", strategy="first")[0] == "技术专家角度"


def test_merge_strategy_joins_prompts():
    prompt, _ = _match("编程的历史", strategy="merge")
    assert "技术专家角度" in prompt and "历史文化角度" in prompt


def test_empty_rules_returns_empty():
    assert match_keyword_prompt("随便说点什么", [], case_sensitive=False, match_strategy="highest") == ("", "")
