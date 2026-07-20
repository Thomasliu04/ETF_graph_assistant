"""报告阅读层处理：隐藏行内出处、百分比可读化、标点清理。

原始报告仍保留完整「来源：…」供审核与下载；网页阅读视图默认隐藏出处。
"""

from __future__ import annotations

import re

# 匹配「来源：xxx」至句读/空白/结尾（支持表名[条件].字段）
_CITATION_RE = re.compile(
    r"[（(]?\s*来源：\s*[^\s。；;）)\n]+(?:\.[^\s。；;）)\n]+)?\s*[）)]?"
)

# 增速/增长率等后的小数（无 %）→ 转为百分号展示
_RATE_WORD_RE = re.compile(
    r"(?P<prefix>(?:规模)?增速|(?:持营)?增速|增长率|增长幅度|涨幅|跌幅|"
    r"同比|环比|占比|比例)"
    r"(?P<mid>[^\d\-＋+]{0,12})"
    r"(?P<sign>[+\-＋−]?)"
    r"(?P<num>\d+\.\d+)"
    r"(?!\s*%)"
)


def normalize_report_punctuation(text: str) -> str:
    """合并重复句读，修复「双杀。。」这类问题。"""
    if not text:
        return text
    out = text
    out = re.sub(r"。{2,}", "。", out)
    out = re.sub(r"！{2,}", "！", out)
    out = re.sub(r"？{2,}", "？", out)
    out = re.sub(r"(?<!\.)\.{2}(?!\.)", ".", out)
    out = re.sub(r"!{2,}", "!", out)
    out = re.sub(r"\?{2,}", "?", out)
    out = re.sub(r"。\s+。", "。", out)
    out = re.sub(r"。\s*，", "。", out)
    out = re.sub(r"，\s*。", "。", out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out


def strip_inline_citations(text: str) -> tuple[str, list[str]]:
    """去掉正文中的「来源：…」，并收集出处列表（去重保序）。"""
    if not text:
        return "", []
    found: list[str] = []

    def _collect(match: re.Match) -> str:
        raw = match.group(0).strip()
        cleaned = raw.strip("（()）").strip()
        if cleaned and cleaned not in found:
            found.append(cleaned)
        return ""

    body = _CITATION_RE.sub(_collect, text)
    body = re.sub(r"[ \t]{2,}", " ", body)
    body = re.sub(r" *([，,。；;])", r"\1", body)
    body = normalize_report_punctuation(body)
    return body.strip(), found


def format_rates_as_percent(text: str) -> str:
    """
    将「增速 0.153」这类小数展示为「增速 15.3%」。
    仅处理带增速/增长率等关键词、且数值绝对值通常像比率（|x|<5）的情况。
    已带 % 的不改；绝对值≥5 的视为已是百分点写法，补上 %。
    """
    if not text:
        return text

    def _repl(match: re.Match) -> str:
        prefix = match.group("prefix")
        mid = match.group("mid")
        sign = match.group("sign").replace("＋", "+").replace("−", "-")
        num = float(match.group("num"))
        if abs(num) < 5:
            pct = num * 100.0
        else:
            pct = num
        pct_str = f"{pct:.2f}".rstrip("0").rstrip(".")
        return f"{prefix}{mid}{sign}{pct_str}%"

    return _RATE_WORD_RE.sub(_repl, text)


def prepare_report_for_reading(text: str) -> tuple[str, list[str]]:
    """阅读视图：隐藏出处 + 百分比可读化。返回 (正文, 出处列表)。"""
    body, citations = strip_inline_citations(text or "")
    body = format_rates_as_percent(body)
    body = normalize_report_punctuation(body)
    return body, citations
