"""聚合表插件注册：Excel 登记表加载 + 内置回退。

业务同学在 configs/聚合登记表.xlsx 新增行即可扩展标准 groupby 聚合；
计算仍走 data_calc.calc_aggregation，不在此实现新算法。
"""

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .aggregations import (
    AGGREGATION_SPECS,
    BUILTIN_AGGREGATION_SPECS,
    BUILTIN_TABLE_DESCRIPTIONS,
    EXTRA_TABLE_SPECS,
    AggregationSpec,
)
from .base_table import BaseCols

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_REGISTRY_PATH = PROJECT_ROOT / "configs" / "聚合登记表.xlsx"
SHEET_STANDARD = "标准聚合"
SHEET_HELP = "填写说明"

SECTION_CN_TO_KEY = {
    "区域": "area",
    "赛道": "track",
    "管理人": "manager",
    "目标公司": "target",
    "area": "area",
    "track": "track",
    "manager": "manager",
    "target": "target",
}

SECTION_KEY_TO_CN = {
    "area": "区域",
    "track": "赛道",
    "manager": "管理人",
    "target": "目标公司",
}

# 与现网 ANALYSIS_TABLE_ORDER 中目标公司段一致（不进 Excel 自助）
TARGET_AI_TABLE_ORDER: list[tuple[str, str, str]] = [
    ("target_summary", "目标公司总览", "target_summary"),
    ("target_by_area", "目标公司分区域", "target_by_area"),
    ("target_by_track", "目标公司分赛道", "target_by_track"),
    ("target_top_bottom", "目标公司增量/缩水梯队", "target_top_bottom"),
]

TARGET_SECTION_TABLES: tuple[str, ...] = (
    "target_summary",
    "target_by_area",
    "target_by_track",
    "target_top_bottom",
    "manager",
)

# 内置四表的 AI / 章节元数据（与现网顺序一致）
BUILTIN_PLUGIN_META: dict[str, dict[str, Any]] = {
    "area": {
        "ai_title": "区域ETF聚合数据",
        "ai_source_name": "area_agg",
        "ai_order": 10,
        "report_sections": ("area",),
        "enabled_by_default": True,
        "send_to_ai": True,
    },
    "track": {
        "ai_title": "赛道ETF聚合数据",
        "ai_source_name": "track_agg",
        "ai_order": 20,
        "report_sections": ("track",),
        "enabled_by_default": True,
        "send_to_ai": True,
    },
    "manager": {
        "ai_title": "管理人ETF排名数据",
        "ai_source_name": "manager_agg",
        "ai_order": 30,
        "report_sections": ("manager",),
        "enabled_by_default": True,
        "send_to_ai": True,
    },
    "national_team": {
        "ai_title": "国家队聚合数据",
        "ai_source_name": "national_team_agg",
        "ai_order": 40,
        "report_sections": ("area",),
        "enabled_by_default": True,
        "send_to_ai": True,
    },
}

REGISTRY_COLUMNS = [
    "代号",
    "中文表名",
    "说明",
    "分组列",
    "输出列名",
    "是否排名",
    "是否TOP产品",
    "TOP数量",
    "默认启用",
    "送给AI",
    "AI标题",
    "AI顺序",
    "报告章节",
    "是否内置",
]

_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")

_loaded = False
_load_source: str = "builtin"
_load_warnings: list[str] = []
_plugins: dict[str, "TablePlugin"] = {}


@dataclass(frozen=True)
class TablePlugin:
    name: str
    sheet_name: str
    csv_name: str
    description: str
    aggregation: AggregationSpec
    enabled_by_default: bool = True
    send_to_ai: bool = True
    ai_title: str | None = None
    ai_source_name: str | None = None
    ai_order: int = 100
    report_sections: tuple[str, ...] = ()
    is_builtin: bool = False
    source_row: int | None = None


def _parse_bool(value: Any, *, field: str, row: int) -> bool:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        raise ValueError(f"第 {row} 行「{field}」不能为空，请填写 是/否")
    text = str(value).strip().lower()
    if text in {"是", "y", "yes", "true", "1", "真"}:
        return True
    if text in {"否", "n", "no", "false", "0", "假"}:
        return False
    raise ValueError(f"第 {row} 行「{field}」只能填 是/否，当前为：{value}")


def _parse_sections(value: Any, *, row: int) -> tuple[str, ...]:
    if value is None or (isinstance(value, float) and pd.isna(value)) or str(value).strip() == "":
        return ()
    parts = re.split(r"[、,，;/|]+", str(value).strip())
    keys: list[str] = []
    for part in parts:
        token = part.strip()
        if not token:
            continue
        key = SECTION_CN_TO_KEY.get(token) or SECTION_CN_TO_KEY.get(token.lower())
        if not key:
            allowed = "、".join(SECTION_KEY_TO_CN.values())
            raise ValueError(
                f"第 {row} 行「报告章节」无法识别「{token}」，请填写：{allowed}"
            )
        if key not in keys:
            keys.append(key)
    return tuple(keys)


def _truthy_empty(value: Any) -> bool:
    return value is None or (isinstance(value, float) and pd.isna(value)) or str(value).strip() == ""


def build_builtin_plugins() -> dict[str, TablePlugin]:
    plugins: dict[str, TablePlugin] = {}
    for name, spec in BUILTIN_AGGREGATION_SPECS.items():
        meta = BUILTIN_PLUGIN_META[name]
        plugins[name] = TablePlugin(
            name=name,
            sheet_name=spec.sheet_name,
            csv_name=spec.csv_name,
            description=BUILTIN_TABLE_DESCRIPTIONS.get(name, ""),
            aggregation=spec,
            enabled_by_default=bool(meta["enabled_by_default"]),
            send_to_ai=bool(meta["send_to_ai"]),
            ai_title=str(meta["ai_title"]),
            ai_source_name=str(meta["ai_source_name"]),
            ai_order=int(meta["ai_order"]),
            report_sections=tuple(meta["report_sections"]),
            is_builtin=True,
            source_row=None,
        )
    return plugins


def _spec_fingerprint(spec: AggregationSpec) -> tuple:
    return (
        spec.name,
        spec.sheet_name,
        spec.csv_name,
        tuple(spec.group_cols),
        tuple(sorted(spec.rename_map.items())),
        spec.include_rank,
        spec.include_top_products,
        spec.top_n,
    )


def _row_to_plugin(row: pd.Series, excel_row_number: int) -> TablePlugin:
    name = str(row.get("代号", "")).strip()
    if not name or not _NAME_RE.match(name):
        raise ValueError(
            f"第 {excel_row_number} 行「代号」须为字母开头的英文/数字/下划线，当前为：{name!r}"
        )

    sheet_name = str(row.get("中文表名", "")).strip()
    if not sheet_name:
        raise ValueError(f"第 {excel_row_number} 行「中文表名」不能为空")

    description = "" if _truthy_empty(row.get("说明")) else str(row.get("说明")).strip()
    group_col = str(row.get("分组列", "")).strip()
    if not group_col:
        raise ValueError(f"第 {excel_row_number} 行「分组列」不能为空（须是底表真实列名）")

    output_col = str(row.get("输出列名", "")).strip() or group_col
    include_rank = _parse_bool(row.get("是否排名"), field="是否排名", row=excel_row_number)
    include_top = _parse_bool(row.get("是否TOP产品"), field="是否TOP产品", row=excel_row_number)

    top_n_raw = row.get("TOP数量")
    if _truthy_empty(top_n_raw):
        top_n = 3
    else:
        try:
            top_n = int(top_n_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"第 {excel_row_number} 行「TOP数量」须为整数") from exc
        if top_n < 1:
            raise ValueError(f"第 {excel_row_number} 行「TOP数量」须 ≥ 1")

    enabled = _parse_bool(row.get("默认启用"), field="默认启用", row=excel_row_number)
    send_to_ai = _parse_bool(row.get("送给AI"), field="送给AI", row=excel_row_number)
    sections = _parse_sections(row.get("报告章节"), row=excel_row_number)
    is_builtin = _parse_bool(row.get("是否内置"), field="是否内置", row=excel_row_number)

    ai_title = None if _truthy_empty(row.get("AI标题")) else str(row.get("AI标题")).strip()
    if send_to_ai and not ai_title:
        ai_title = sheet_name

    ai_order_raw = row.get("AI顺序")
    if _truthy_empty(ai_order_raw):
        ai_order = 100
    else:
        try:
            ai_order = int(ai_order_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"第 {excel_row_number} 行「AI顺序」须为整数") from exc

    csv_name = f"{name}_agg.csv"
    spec = AggregationSpec(
        name=name,
        sheet_name=sheet_name[:31],
        csv_name=csv_name,
        group_cols=[group_col],
        rename_map={group_col: output_col},
        include_rank=include_rank,
        include_top_products=include_top,
        top_n=top_n,
        top_sort_col=BaseCols.DELTA,
    )

    return TablePlugin(
        name=name,
        sheet_name=spec.sheet_name,
        csv_name=csv_name,
        description=description,
        aggregation=spec,
        enabled_by_default=enabled,
        send_to_ai=send_to_ai,
        ai_title=ai_title,
        ai_source_name=f"{name}_agg",
        ai_order=ai_order,
        report_sections=sections,
        is_builtin=is_builtin,
        source_row=excel_row_number,
    )


def _apply_plugins_to_aggregation_specs(plugins: dict[str, TablePlugin]) -> None:
    """用插件列表刷新全局 AGGREGATION_SPECS（原地更新，保持引用稳定）。"""
    AGGREGATION_SPECS.clear()
    for name, plugin in plugins.items():
        AGGREGATION_SPECS[name] = plugin.aggregation


def load_plugins_from_excel(
    path: Path | None = None,
) -> tuple[dict[str, TablePlugin], list[str], str]:
    registry_path = Path(path) if path else DEFAULT_REGISTRY_PATH
    warnings_acc: list[str] = []
    builtin = build_builtin_plugins()

    if not registry_path.exists():
        warnings_acc.append(
            f"未找到聚合登记表：{registry_path}。已回退到代码内置规格（与改造前行为一致）。"
        )
        return builtin, warnings_acc, "builtin"

    try:
        df = pd.read_excel(registry_path, sheet_name=SHEET_STANDARD, dtype=object)
    except Exception as exc:  # noqa: BLE001
        warnings_acc.append(
            f"读取聚合登记表失败（{registry_path}）：{exc}。已回退到代码内置规格。"
        )
        return builtin, warnings_acc, "builtin"

    missing_cols = [c for c in REGISTRY_COLUMNS if c not in df.columns]
    if missing_cols:
        warnings_acc.append(
            f"聚合登记表缺少列：{missing_cols}。已回退到代码内置规格。"
        )
        return builtin, warnings_acc, "builtin"

    plugins: dict[str, TablePlugin] = {}
    try:
        for idx, row in df.iterrows():
            excel_row = int(idx) + 2  # header is row 1
            if _truthy_empty(row.get("代号")):
                continue
            plugin = _row_to_plugin(row, excel_row)
            if plugin.name in plugins:
                raise ValueError(
                    f"第 {excel_row} 行代号「{plugin.name}」重复，请保证全局唯一"
                )

            if plugin.name in BUILTIN_AGGREGATION_SPECS:
                builtin_plugin = builtin[plugin.name]
                if _spec_fingerprint(plugin.aggregation) != _spec_fingerprint(
                    builtin_plugin.aggregation
                ):
                    warnings_acc.append(
                        f"第 {excel_row} 行内置代号「{plugin.name}」的计算参数与代码不一致，"
                        f"已强制使用代码内置参数（请勿修改内置四行的分组/排名/TOP 等字段）。"
                    )
                plugins[plugin.name] = TablePlugin(
                    name=builtin_plugin.name,
                    sheet_name=builtin_plugin.sheet_name,
                    csv_name=builtin_plugin.csv_name,
                    description=plugin.description or builtin_plugin.description,
                    aggregation=builtin_plugin.aggregation,
                    enabled_by_default=plugin.enabled_by_default,
                    send_to_ai=plugin.send_to_ai,
                    ai_title=plugin.ai_title or builtin_plugin.ai_title,
                    ai_source_name=builtin_plugin.ai_source_name,
                    ai_order=plugin.ai_order,
                    report_sections=plugin.report_sections or builtin_plugin.report_sections,
                    is_builtin=True,
                    source_row=excel_row,
                )
            else:
                if plugin.is_builtin:
                    raise ValueError(
                        f"第 {excel_row} 行「{plugin.name}」标记为内置，但代码中无此内置表；"
                        f"请将「是否内置」改为否"
                    )
                plugins[plugin.name] = plugin

        for name, builtin_plugin in builtin.items():
            if name not in plugins:
                warnings_acc.append(
                    f"登记表缺少内置表「{name}」，已自动补回代码内置规格。"
                )
                plugins[name] = builtin_plugin

    except ValueError as exc:
        warnings_acc.append(f"聚合登记表校验失败：{exc}。已回退到代码内置规格。")
        return builtin, warnings_acc, "builtin"

    return plugins, warnings_acc, str(registry_path)


def ensure_plugins_loaded(*, force: bool = False, path: Path | None = None) -> dict[str, TablePlugin]:
    global _loaded, _load_source, _load_warnings, _plugins
    if _loaded and not force and path is None:
        return _plugins

    plugins, warnings_acc, source = load_plugins_from_excel(path)
    _plugins = plugins
    _load_warnings = warnings_acc
    _load_source = source
    _apply_plugins_to_aggregation_specs(_plugins)
    _loaded = True

    for msg in warnings_acc:
        warnings.warn(msg, UserWarning, stacklevel=2)
    return _plugins


def get_plugins() -> dict[str, TablePlugin]:
    return ensure_plugins_loaded()


def get_load_info() -> dict[str, Any]:
    ensure_plugins_loaded()
    return {
        "source": _load_source,
        "warnings": list(_load_warnings),
        "plugin_count": len(_plugins),
    }


def default_agg_names() -> list[str]:
    plugins = ensure_plugins_loaded()
    # 内置顺序优先，再追加其他默认启用项（按 AI 顺序）
    names: list[str] = []
    for name in BUILTIN_AGGREGATION_SPECS:
        plugin = plugins.get(name)
        if plugin and plugin.enabled_by_default:
            names.append(name)
    extras = [
        p
        for name, p in plugins.items()
        if name not in BUILTIN_AGGREGATION_SPECS and p.enabled_by_default
    ]
    extras.sort(key=lambda p: (p.ai_order, p.name))
    names.extend(p.name for p in extras)
    return names


def analysis_table_order() -> list[tuple[str, str, str]]:
    """(key, title, source_name) — 标准表来自插件，目标公司段固定接在后面。"""
    plugins = ensure_plugins_loaded()
    rows = [
        p
        for p in plugins.values()
        if p.send_to_ai and p.ai_title
    ]
    rows.sort(key=lambda p: (p.ai_order, p.name))
    order = [(p.name, p.ai_title or p.sheet_name, p.ai_source_name or f"{p.name}_agg") for p in rows]
    # 避免重复插入 target
    existing = {k for k, _, _ in order}
    for key, title, source in TARGET_AI_TABLE_ORDER:
        if key not in existing:
            order.append((key, title, source))
    return order


def section_table_keys_from_registry() -> dict[str, tuple[str, ...]]:
    plugins = ensure_plugins_loaded()
    buckets: dict[str, list[str]] = {k: [] for k in ("area", "track", "manager", "target")}

    # 先按插件声明
    ordered_plugins = sorted(plugins.values(), key=lambda p: (p.ai_order, p.name))
    for plugin in ordered_plugins:
        for section in plugin.report_sections:
            if section in buckets and plugin.name not in buckets[section]:
                buckets[section].append(plugin.name)

    # 目标公司固定表（保持现网顺序）
    for key in TARGET_SECTION_TABLES:
        if key not in buckets["target"]:
            buckets["target"].append(key)

    # 若某章节为空，回退到旧默认，避免改写后局部改写裁剪空表
    fallback = {
        "area": ["area", "national_team"],
        "track": ["track"],
        "manager": ["manager"],
        "target": list(TARGET_SECTION_TABLES),
    }
    result: dict[str, tuple[str, ...]] = {}
    for section, keys in buckets.items():
        result[section] = tuple(keys if keys else fallback[section])
    return result


def plugin_catalog_rows() -> list[dict[str, Any]]:
    plugins = ensure_plugins_loaded()
    info = get_load_info()
    rows = []
    for name in default_agg_names() + [
        n for n in plugins if n not in set(default_agg_names())
    ]:
        p = plugins[name]
        rows.append(
            {
                "代号": p.name,
                "中文表名": p.sheet_name,
                "默认启用": "是" if p.enabled_by_default else "否",
                "送给AI": "是" if p.send_to_ai else "否",
                "报告章节": "、".join(SECTION_KEY_TO_CN.get(s, s) for s in p.report_sections),
                "类型": "内置" if p.is_builtin else "新增",
                "登记表行号": p.source_row if p.source_row is not None else "—",
                "加载来源": info["source"],
            }
        )
    return rows


def builtin_registry_dataframe() -> pd.DataFrame:
    """生成与现网一致的登记表内容（用于写 Excel / 文档）。"""
    rows = []
    for name, plugin in build_builtin_plugins().items():
        spec = plugin.aggregation
        group_col = spec.group_cols[0]
        output_col = spec.rename_map[group_col]
        rows.append(
            {
                "代号": name,
                "中文表名": spec.sheet_name,
                "说明": plugin.description,
                "分组列": group_col,
                "输出列名": output_col,
                "是否排名": "是" if spec.include_rank else "否",
                "是否TOP产品": "是" if spec.include_top_products else "否",
                "TOP数量": spec.top_n,
                "默认启用": "是" if plugin.enabled_by_default else "否",
                "送给AI": "是" if plugin.send_to_ai else "否",
                "AI标题": plugin.ai_title,
                "AI顺序": plugin.ai_order,
                "报告章节": "、".join(
                    SECTION_KEY_TO_CN.get(s, s) for s in plugin.report_sections
                ),
                "是否内置": "是",
            }
        )
    return pd.DataFrame(rows, columns=REGISTRY_COLUMNS)


HELP_SHEET_ROWS = [
    {"项目": "用途", "说明": "本表用于登记「标准聚合」：按底表某一列分组汇总。无需编写代码。"},
    {"项目": "如何新增", "说明": "不要改「是否内置=是」的四行；在表格下方复制一行，改「是否内置=否」后填写。"},
    {"项目": "代号", "说明": "英文唯一名，如 theme。只能字母开头，含字母数字下划线。"},
    {"项目": "中文表名", "说明": "导出 Excel 的 sheet 名（建议≤31字）。"},
    {"项目": "分组列", "说明": "必须是底表里真实存在的列名（与 CSV/Excel 表头一致）。"},
    {"项目": "输出列名", "说明": "聚合结果里分组列显示成什么名字。"},
    {"项目": "是否排名/TOP", "说明": "填 是/否。TOP 产品按规模增量取前 N。"},
    {"项目": "默认启用", "说明": "是=一键分析会自动计算这张表。"},
    {"项目": "送给AI", "说明": "是=分析/审核模型能看到这张表。"},
    {"项目": "报告章节", "说明": "填：区域 / 赛道 / 管理人 / 目标公司（可多个，用顿号分隔）。"},
    {"项目": "计算说明", "说明": "系统用已有通用汇总引擎计算（groupby+求和+增速），不会因加行而改旧表算法。"},
    {"项目": "复杂需求", "说明": "若不是简单按一列汇总（如目标公司切片），请找开发在 calculations/ 实现。"},
    {"项目": "出错时", "说明": "登记表损坏或校验失败时，系统会回退到代码内置四表，保证旧流程可跑。"},
]


def write_registry_excel(path: Path | None = None) -> Path:
    """写入/覆盖默认登记表（含内置四行 + 填写说明）。"""
    target = Path(path) if path else DEFAULT_REGISTRY_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    standard = builtin_registry_dataframe()
    help_df = pd.DataFrame(HELP_SHEET_ROWS)
    with pd.ExcelWriter(target, engine="openpyxl") as writer:
        standard.to_excel(writer, sheet_name=SHEET_STANDARD, index=False)
        help_df.to_excel(writer, sheet_name=SHEET_HELP, index=False)
    return target


def get_table_description_from_plugins(name: str) -> str:
    plugins = ensure_plugins_loaded()
    if name in plugins:
        return plugins[name].description
    if name in EXTRA_TABLE_SPECS:
        return EXTRA_TABLE_SPECS[name].description
    return BUILTIN_TABLE_DESCRIPTIONS.get(name, "")
