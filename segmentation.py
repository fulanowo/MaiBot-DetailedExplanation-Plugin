"""长文分段算法。

纯函数实现，不依赖插件运行时与 SDK；plugin.py 从配置取值后调用。
"""

from __future__ import annotations

import re

DEFAULT_SENTENCE_SEPARATORS: list[str] = ["。", "！", "？", ".", "!", "?"]


def prepare_paragraphs(
    content: str,
    *,
    keep_paragraph_integrity: bool,
    min_paragraph_length: int,
) -> list[str]:
    """按空行切分段落，并在需要时合并过短段落。

    Args:
        content: 待切分的全文。
        keep_paragraph_integrity: 为 True 时把不足 min_paragraph_length 的段落并入后一段。
        min_paragraph_length: 段落合并阈值（字符数）。

    Returns:
        list[str]: 处理后的段落列表。
    """

    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", content) if paragraph.strip()]
    if not keep_paragraph_integrity:
        return paragraphs
    if min_paragraph_length <= 0:
        return paragraphs

    merged: list[str] = []
    buffer = ""
    for paragraph in paragraphs:
        buffer = f"{buffer}\n\n{paragraph}" if buffer else paragraph
        if len(buffer) >= min_paragraph_length:
            merged.append(buffer)
            buffer = ""
    if buffer:
        if merged:
            merged[-1] = f"{merged[-1]}\n\n{buffer}"
        else:
            merged.append(buffer)
    return merged


def split_by_sentences(text: str, separators: list[str]) -> list[str]:
    """按句末标点切句，标点保留在句子尾部。

    Args:
        text: 待切分文本。
        separators: 句末标点集合。

    Returns:
        list[str]: 句子列表。
    """

    effective_separators = [separator for separator in separators if separator] or DEFAULT_SENTENCE_SEPARATORS
    pattern = "([" + "".join(re.escape(separator) for separator in effective_separators) + "])"
    parts = re.split(pattern, text)

    sentences: list[str] = []
    for index in range(0, len(parts) - 1, 2):
        sentence = parts[index] + parts[index + 1]
        if sentence.strip():
            sentences.append(sentence)
    if len(parts) % 2 == 1 and parts[-1].strip():
        sentences.append(parts[-1])
    return sentences


def _pack_sentences(sentences: list[str], target_length: int) -> list[str]:
    """把句子依次装进不超过 target_length 的段落。"""

    segments: list[str] = []
    current = ""
    for sentence in sentences:
        if len(current + sentence) <= target_length:
            current += sentence
            continue
        if current:
            segments.append(current)
        current = sentence
    if current:
        segments.append(current)
    return segments


def smart_split(
    content: str,
    *,
    target_length: int,
    keep_paragraph_integrity: bool,
    min_paragraph_length: int,
    sentence_separators: list[str],
) -> list[str]:
    """优先保持段落完整，超长段落再按句子切开。"""

    paragraphs = prepare_paragraphs(
        content,
        keep_paragraph_integrity=keep_paragraph_integrity,
        min_paragraph_length=min_paragraph_length,
    )
    if not paragraphs:
        return [content]

    segments: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(current + paragraph) <= target_length:
            current = f"{current}\n\n{paragraph}" if current else paragraph
            continue
        if current:
            segments.append(current)
        if len(paragraph) > target_length:
            packed = _pack_sentences(split_by_sentences(paragraph, sentence_separators), target_length)
            if packed:
                segments.extend(packed[:-1])
                current = packed[-1]
            else:
                current = ""
        else:
            current = paragraph
    if current:
        segments.append(current)
    return segments


def sentence_split(
    content: str,
    *,
    target_length: int,
    keep_paragraph_integrity: bool,
    min_paragraph_length: int,
    sentence_separators: list[str],
) -> list[str]:
    """按句子装段；开启段落完整性时逐段处理，避免跨段粘连。"""

    if not keep_paragraph_integrity:
        return _pack_sentences(split_by_sentences(content, sentence_separators), target_length)

    segments: list[str] = []
    paragraphs = prepare_paragraphs(
        content,
        keep_paragraph_integrity=keep_paragraph_integrity,
        min_paragraph_length=min_paragraph_length,
    )
    for paragraph in paragraphs:
        segments.extend(_pack_sentences(split_by_sentences(paragraph, sentence_separators), target_length))
    return segments


def length_split(
    content: str,
    *,
    target_length: int,
    keep_paragraph_integrity: bool,
    min_paragraph_length: int,
) -> list[str]:
    """按字符数硬切；开启段落完整性时不跨段。"""

    if not keep_paragraph_integrity:
        return [content[index : index + target_length] for index in range(0, len(content), target_length)]

    paragraphs = prepare_paragraphs(
        content,
        keep_paragraph_integrity=keep_paragraph_integrity,
        min_paragraph_length=min_paragraph_length,
    )
    segments: list[str] = []
    for paragraph in paragraphs:
        segments.extend(paragraph[index : index + target_length] for index in range(0, len(paragraph), target_length))
    return segments


def split_content_into_segments(
    content: str,
    *,
    segment_length: int,
    min_segments: int,
    max_segments: int,
    algorithm: str,
    keep_paragraph_integrity: bool,
    min_paragraph_length: int,
    sentence_separators: list[str],
) -> list[str]:
    """按配置把长文切成若干段。

    Args:
        content: 全文。
        segment_length: 单段目标字符数。
        min_segments: 最少段数；不足时不分段。
        max_segments: 最多段数；超出部分合并到最后一段。
        algorithm: smart / sentence / length。
        keep_paragraph_integrity: 是否保持段落完整。
        min_paragraph_length: 段落合并阈值。
        sentence_separators: 句末标点集合。

    Returns:
        list[str]: 分段结果；内容为空时返回空列表。
    """

    text = (content or "").strip()
    if not text:
        return []
    if len(text) <= segment_length:
        return [text]

    if algorithm == "sentence":
        segments = sentence_split(
            text,
            target_length=segment_length,
            keep_paragraph_integrity=keep_paragraph_integrity,
            min_paragraph_length=min_paragraph_length,
            sentence_separators=sentence_separators,
        )
    elif algorithm == "length":
        segments = length_split(
            text,
            target_length=segment_length,
            keep_paragraph_integrity=keep_paragraph_integrity,
            min_paragraph_length=min_paragraph_length,
        )
    else:
        segments = smart_split(
            text,
            target_length=segment_length,
            keep_paragraph_integrity=keep_paragraph_integrity,
            min_paragraph_length=min_paragraph_length,
            sentence_separators=sentence_separators,
        )

    segments = [segment for segment in segments if segment.strip()]
    if not segments:
        return [text]
    if len(segments) < min_segments:
        return [text]
    if len(segments) > max_segments:
        tail = "\n\n".join(segments[max_segments - 1 :])
        segments = segments[: max_segments - 1] + [tail]
    return segments
