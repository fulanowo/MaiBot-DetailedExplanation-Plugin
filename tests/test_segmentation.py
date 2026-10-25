"""分段算法单元测试。

只依赖 segmentation.py 的纯函数，不需要插件运行时或 SDK。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from segmentation import split_content_into_segments


def _split(
    content,
    *,
    algorithm="smart",
    segment_length=25,
    min_segments=1,
    max_segments=10,
    keep_paragraph_integrity=True,
    min_paragraph_length=5,
):
    return split_content_into_segments(
        content,
        segment_length=segment_length,
        min_segments=min_segments,
        max_segments=max_segments,
        algorithm=algorithm,
        keep_paragraph_integrity=keep_paragraph_integrity,
        min_paragraph_length=min_paragraph_length,
        sentence_separators=["。", "！", "？", ".", "!", "?"],
    )


def test_segment_merge_preserves_newlines():
    content = "A" * 10 + "B" * 10 + "C" * 10
    segments = _split(
        content,
        algorithm="length",
        segment_length=10,
        max_segments=2,
        min_paragraph_length=50,
    )
    assert segments == ["A" * 10, "B" * 10 + "\n\n" + "C" * 10]


def test_paragraph_merging_smart():
    content = "A" * 3 + "\n\n" + "B" * 3 + "\n\n" + "C" * 20
    assert _split(content, algorithm="smart") == ["A" * 3 + "\n\n" + "B" * 3, "C" * 20]


def test_paragraph_merging_sentence():
    content = "A" * 3 + "\n\n" + "B" * 3 + "\n\n" + "C" * 20
    assert _split(content, algorithm="sentence") == ["A" * 3 + "\n\n" + "B" * 3, "C" * 20]


def test_paragraph_merging_length():
    content = "A" * 3 + "\n\n" + "B" * 3 + "\n\n" + "C" * 20
    assert _split(content, algorithm="length") == ["A" * 3 + "\n\n" + "B" * 3, "C" * 20]


def test_short_content_stays_whole():
    content = "很短的一段内容"
    assert _split(content, segment_length=400) == [content]


def test_empty_content_returns_empty_list():
    assert _split("   ") == []


def test_long_paragraph_split_by_sentences():
    content = "第一句话。" * 4 + "第二句话！" * 4
    segments = _split(content, algorithm="smart", segment_length=20)
    assert len(segments) > 1
    assert "".join(segment.replace("\n\n", "") for segment in segments) == content
