"""报告四大模块的章节锚点拆分 / 合并。"""

from __future__ import annotations

import re
from typing import Iterable

SECTION_KEYS = ("area", "track", "manager", "target")

SECTION_TITLES = {
    "area": "区域维度",
    "track": "赛道维度",
    "manager": "管理人维度",
    "target": "目标公司维度",
}

SECTION_HEADERS = {
    key: f"## 【{key}】{SECTION_TITLES[key]}" for key in SECTION_KEYS
}

# 允许标题后带额外说明，例如：## 【area】区域维度分析
_SECTION_HEADER_RE = re.compile(
    r"^##\s*【(?P<key>area|track|manager|target)】[^\n]*$",
    re.MULTILINE,
)

SECTION_TABLE_KEYS: dict[str, tuple[str, ...]] = {
    "area": ("area", "national_team"),
    "track": ("track",),
    "manager": ("manager",),
    "target": (
        "target_summary",
        "target_by_area",
        "target_by_track",
        "target_top_bottom",
        "manager",
    ),
}


def get_section_table_keys() -> dict[str, tuple[str, ...]]:
    """运行时从聚合登记表派生；失败时回退到上方常量。"""
    try:
        try:
            from .contracts import section_table_keys_from_registry
        except ImportError:
            from contracts import section_table_keys_from_registry

        return section_table_keys_from_registry()
    except Exception:
        return dict(SECTION_TABLE_KEYS)


def normalize_section_keys(sections: Iterable[str] | None) -> list[str]:
    if not sections:
        return []
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in sections:
        key = str(raw).strip().lower()
        if key not in SECTION_KEYS or key in seen:
            continue
        seen.add(key)
        ordered.append(key)
    return ordered


def section_header(key: str) -> str:
    if key not in SECTION_HEADERS:
        raise ValueError(f"未知章节键：{key}")
    return SECTION_HEADERS[key]


def split_sections(report_text: str) -> dict[str, str]:
    """
    按【area/track/manager/target】锚点拆分报告。
    返回 {section_key: 含标题的完整章节正文}；无法识别的前言放在 preamble。
    """
    text = report_text or ""
    matches = list(_SECTION_HEADER_RE.finditer(text))
    if not matches:
        return {"preamble": text.strip()}

    result: dict[str, str] = {}
    preamble = text[: matches[0].start()].strip()
    if preamble:
        result["preamble"] = preamble

    for idx, match in enumerate(matches):
        key = match.group("key")
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        # 同名章节以后出现的为准
        result[key] = body
    return result


def extract_section_bodies(report_text: str, section_keys: Iterable[str]) -> dict[str, str]:
    parts = split_sections(report_text)
    out: dict[str, str] = {}
    for key in normalize_section_keys(section_keys):
        if key in parts and parts[key].strip():
            out[key] = parts[key].strip()
        else:
            out[key] = section_header(key) + "\n\n（原报告缺失该章节，请按数据完整重写。）"
    return out


def merge_sections(
    base_report: str,
    updated_sections: dict[str, str],
    *,
    ensure_all_sections: bool = True,
) -> str:
    """
    用 updated_sections 覆盖 base_report 中对应章节，其余章节保留。
    若 ensure_all_sections=True，按固定顺序输出四大模块（缺失则补标题占位）。
    """
    parts = split_sections(base_report)
    for key, body in (updated_sections or {}).items():
        norm = str(key).strip().lower()
        if norm not in SECTION_KEYS:
            continue
        cleaned = (body or "").strip()
        if not cleaned:
            continue
        if not _SECTION_HEADER_RE.search(cleaned):
            cleaned = f"{section_header(norm)}\n\n{cleaned}"
        parts[norm] = cleaned

    blocks: list[str] = []
    preamble = parts.get("preamble", "").strip()
    if preamble:
        blocks.append(preamble)

    for key in SECTION_KEYS:
        body = parts.get(key, "").strip()
        if body:
            blocks.append(body)
        elif ensure_all_sections:
            blocks.append(section_header(key) + "\n\n（待补充）")

    return "\n\n".join(blocks).strip() + "\n"


def tables_for_sections(section_keys: Iterable[str]) -> list[str]:
    """按章节汇总需要对照的数据表键（去重、稳定顺序）。"""
    mapping = get_section_table_keys()
    ordered: list[str] = []
    seen: set[str] = set()
    for section in normalize_section_keys(section_keys):
        for table_key in mapping.get(section, ()):
            if table_key in seen:
                continue
            seen.add(table_key)
            ordered.append(table_key)
    return ordered
