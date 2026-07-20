"""聚合输出字段与 AggregationSpec 注册表。"""

from __future__ import annotations

from dataclasses import dataclass

from .base_table import BaseCols


class AggCols:
    """标准聚合表输出列名（单一事实来源）。"""

    START_SIZE = "期初规模"
    END_SIZE = "期末规模"
    NEW_ISSUE = "新发贡献"
    NAV_CONTRIB = "净值贡献"
    HOLDING_CONTRIB = "持营贡献"
    DELTA = "规模增量"
    GROWTH_RATE = "规模增速"
    HOLDING_GROWTH = "持营增速"
    AREA_TYPE = "区域类型"
    TRACK_TYPE = "赛道类型"
    MANAGER = "管理人"
    NATIONAL_TEAM = "是否国家队"
    RANK = "增量排名"


# 底表数值列 → 聚合表标准列
STANDARD_RENAME_MAP: dict[str, str] = {
    BaseCols.START_SIZE: AggCols.START_SIZE,
    BaseCols.END_SIZE: AggCols.END_SIZE,
    BaseCols.NEW_ISSUE: AggCols.NEW_ISSUE,
    BaseCols.NAV_CONTRIB: AggCols.NAV_CONTRIB,
    BaseCols.HOLDING_CONTRIB: AggCols.HOLDING_CONTRIB,
}

VALUE_AGG_COLUMNS: dict[str, str] = {
    BaseCols.START_SIZE: "sum",
    BaseCols.END_SIZE: "sum",
    BaseCols.NEW_ISSUE: "sum",
    BaseCols.NAV_CONTRIB: "sum",
    BaseCols.HOLDING_CONTRIB: "sum",
}

# 每张标准聚合表都必须具备的核心指标列
CORE_METRIC_COLUMNS: tuple[str, ...] = (
    AggCols.START_SIZE,
    AggCols.END_SIZE,
    AggCols.NEW_ISSUE,
    AggCols.NAV_CONTRIB,
    AggCols.HOLDING_CONTRIB,
    AggCols.DELTA,
    AggCols.GROWTH_RATE,
    AggCols.HOLDING_GROWTH,
)

SORTABLE_COLUMNS: tuple[str, ...] = (
    *STANDARD_RENAME_MAP.values(),
    AggCols.DELTA,
    AggCols.GROWTH_RATE,
    AggCols.HOLDING_GROWTH,
)


@dataclass(frozen=True)
class AggregationSpec:
    name: str
    sheet_name: str
    csv_name: str
    group_cols: list[str]
    rename_map: dict[str, str]
    sort_by: str = AggCols.DELTA
    ascending: bool = False
    include_rank: bool = False
    rank_col: str = AggCols.RANK
    include_top_products: bool = False
    top_n: int = 3
    top_sort_col: str = BaseCols.DELTA

    @property
    def output_group_cols(self) -> list[str]:
        return [self.rename_map[col] for col in self.group_cols]

    def required_output_columns(self) -> list[str]:
        cols = [*self.output_group_cols, *CORE_METRIC_COLUMNS]
        if self.include_rank:
            cols.append(self.rank_col)
        if self.include_top_products:
            for rank in range(1, self.top_n + 1):
                cols.extend(
                    [
                        f"TOP{rank}产品",
                        f"TOP{rank}代码",
                        f"TOP{rank}简称",
                        f"TOP{rank}增量",
                    ]
                )
        return cols


AGGREGATION_SPECS: dict[str, AggregationSpec] = {
    "area": AggregationSpec(
        name="area",
        sheet_name="区域ETF汇总",
        csv_name="area_agg.csv",
        group_cols=[BaseCols.AREA],
        rename_map={BaseCols.AREA: AggCols.AREA_TYPE},
    ),
    "track": AggregationSpec(
        name="track",
        sheet_name="赛道ETF汇总",
        csv_name="track_agg.csv",
        group_cols=[BaseCols.TRACK],
        rename_map={BaseCols.TRACK: AggCols.TRACK_TYPE},
        include_top_products=True,
    ),
    "manager": AggregationSpec(
        name="manager",
        sheet_name="管理人排名",
        csv_name="manager_agg.csv",
        group_cols=[BaseCols.MANAGER],
        rename_map={BaseCols.MANAGER: AggCols.MANAGER},
        include_rank=True,
        include_top_products=True,
    ),
    "national_team": AggregationSpec(
        name="national_team",
        sheet_name="国家队汇总",
        csv_name="national_team_agg.csv",
        group_cols=[BaseCols.NATIONAL_TEAM],
        rename_map={BaseCols.NATIONAL_TEAM: AggCols.NATIONAL_TEAM},
    ),
}

# 冻结快照：Excel 损坏时回退；内置行参数以此为准
BUILTIN_AGGREGATION_SPECS: dict[str, AggregationSpec] = {
    name: AggregationSpec(
        name=spec.name,
        sheet_name=spec.sheet_name,
        csv_name=spec.csv_name,
        group_cols=list(spec.group_cols),
        rename_map=dict(spec.rename_map),
        sort_by=spec.sort_by,
        ascending=spec.ascending,
        include_rank=spec.include_rank,
        rank_col=spec.rank_col,
        include_top_products=spec.include_top_products,
        top_n=spec.top_n,
        top_sort_col=spec.top_sort_col,
    )
    for name, spec in AGGREGATION_SPECS.items()
}


@dataclass(frozen=True)
class TableExportSpec:
    """非 AggregationSpec 计算表的导出元数据（如目标公司切片）。"""

    name: str
    sheet_name: str
    csv_name: str
    description: str = ""


# 目标公司切片等自定义表：只用于导出/AI，不走标准 groupby 注册计算
EXTRA_TABLE_SPECS: dict[str, TableExportSpec] = {
    "target_summary": TableExportSpec(
        name="target_summary",
        sheet_name="目标公司总览",
        csv_name="target_summary.csv",
        description="目标公司整体规模与排名",
    ),
    "target_by_area": TableExportSpec(
        name="target_by_area",
        sheet_name="目标公司区域",
        csv_name="target_by_area.csv",
        description="目标公司按区域聚合",
    ),
    "target_by_track": TableExportSpec(
        name="target_by_track",
        sheet_name="目标公司赛道",
        csv_name="target_by_track.csv",
        description="目标公司按赛道聚合",
    ),
    "target_products": TableExportSpec(
        name="target_products",
        sheet_name="目标公司产品",
        csv_name="target_products.csv",
        description="目标公司全部产品明细",
    ),
    "target_top_bottom": TableExportSpec(
        name="target_top_bottom",
        sheet_name="目标公司梯队",
        csv_name="target_top_bottom.csv",
        description="目标公司增量TOP与缩水TOP产品",
    ),
}


def register_aggregation_spec(spec: AggregationSpec) -> None:
    AGGREGATION_SPECS[spec.name] = spec


STANDARD_TABLE_DESCRIPTIONS: dict[str, str] = {
    "area": "全市场按 A股/港股/其他跨境 聚合",
    "track": "全市场按赛道聚合，含增量 TOP3 产品",
    "manager": "全市场按管理人聚合排名，含增量 TOP3 产品",
    "national_team": "全市场按是否国家队持仓聚合",
}

BUILTIN_TABLE_DESCRIPTIONS: dict[str, str] = dict(STANDARD_TABLE_DESCRIPTIONS)


def get_table_export_meta(name: str) -> tuple[str, str]:
    """返回 (sheet_name, csv_name)。"""
    if name in AGGREGATION_SPECS:
        spec = AGGREGATION_SPECS[name]
        return spec.sheet_name, spec.csv_name
    if name in EXTRA_TABLE_SPECS:
        spec = EXTRA_TABLE_SPECS[name]
        return spec.sheet_name, spec.csv_name
    # 兜底：允许导出未注册临时表
    return name[:31], f"{name}.csv"


def get_table_description(name: str) -> str:
    try:
        from .table_plugins import get_table_description_from_plugins

        return get_table_description_from_plugins(name)
    except Exception:
        if name in EXTRA_TABLE_SPECS:
            return EXTRA_TABLE_SPECS[name].description
        return STANDARD_TABLE_DESCRIPTIONS.get(name, "")


def validate_agg_schema(name: str, df) -> list[str]:
    """校验标准聚合结果是否具备契约声明的列；返回缺失列列表。"""
    if name not in AGGREGATION_SPECS:
        raise KeyError(f"未注册的聚合规格：{name}")
    required = AGGREGATION_SPECS[name].required_output_columns()
    return [col for col in required if col not in df.columns]
