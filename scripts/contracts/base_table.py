"""底表字段字典、别名、数值列与行级校验规则。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd

from .meta import META


class BaseCols:
    """底表规范化后的标准列名（单一事实来源）。"""

    CODE_6 = "前6位代码"
    CODE_FULL = "基金代码_全量"
    FUND_NAME = "基金简称"
    MANAGER = "基金公司"
    START_SIZE = "25Q4"
    END_SIZE = "26Q2"
    DELTA = "增量26H1"
    GROWTH_RATE = "增速26H1%"
    NEW_ISSUE = "26H1新发"
    NAV_CONTRIB = "26H1净值"
    HOLDING_CONTRIB = "26H1持营"
    TRACK = "赛道（结合区域和主题打标）"
    AREA = "A股、港股or其他跨境"
    NATIONAL_TEAM = "是否国家队"


# 原始列名（含换行等）→ 标准列名
COLUMN_ALIASES: dict[str, str] = {
    "是否国家队\n持仓": BaseCols.NATIONAL_TEAM,
}

# Excel 读入后按列位置改名（底表列顺序固定时使用；变更 sheet 结构时需同步更新）
XLSX_POSITIONAL_RENAMES: dict[int, str] = {
    1: BaseCols.CODE_FULL,
    2: BaseCols.FUND_NAME,
}

REQUIRED_COLUMNS: tuple[str, ...] = (
    BaseCols.CODE_6,
    BaseCols.FUND_NAME,
    BaseCols.MANAGER,
    BaseCols.START_SIZE,
    BaseCols.END_SIZE,
    BaseCols.DELTA,
    BaseCols.GROWTH_RATE,
    BaseCols.NEW_ISSUE,
    BaseCols.NAV_CONTRIB,
    BaseCols.HOLDING_CONTRIB,
    BaseCols.TRACK,
    BaseCols.AREA,
)

NUMERIC_COLUMNS: tuple[str, ...] = (
    BaseCols.START_SIZE,
    BaseCols.END_SIZE,
    BaseCols.DELTA,
    BaseCols.GROWTH_RATE,
    BaseCols.NEW_ISSUE,
    BaseCols.NAV_CONTRIB,
    BaseCols.HOLDING_CONTRIB,
)

# 可选维度列：缺失时不阻断基础校验，但对应聚合会失败
OPTIONAL_DIMENSION_COLUMNS: tuple[str, ...] = (
    BaseCols.NATIONAL_TEAM,
)


@dataclass(frozen=True)
class BalanceRule:
    """行级平衡校验：computed(df) 应约等于 expected 列。"""

    name: str
    description: str
    compute: Callable[[pd.DataFrame], pd.Series]
    expected_col: str
    tolerance: float = META.validation_tolerance

    def bad_count(self, df: pd.DataFrame) -> int:
        left = self.compute(df)
        right = df[self.expected_col]
        return int((left - right).abs().gt(self.tolerance).sum())


BALANCE_RULES: tuple[BalanceRule, ...] = (
    BalanceRule(
        name="delta_equals_end_minus_start",
        description=f"{BaseCols.DELTA} = {BaseCols.END_SIZE} - {BaseCols.START_SIZE}",
        compute=lambda df: df[BaseCols.END_SIZE] - df[BaseCols.START_SIZE],
        expected_col=BaseCols.DELTA,
    ),
    BalanceRule(
        name="delta_equals_contribution_sum",
        description=(
            f"{BaseCols.DELTA} = {BaseCols.NEW_ISSUE} + "
            f"{BaseCols.NAV_CONTRIB} + {BaseCols.HOLDING_CONTRIB}"
        ),
        compute=lambda df: (
            df[BaseCols.NEW_ISSUE] + df[BaseCols.NAV_CONTRIB] + df[BaseCols.HOLDING_CONTRIB]
        ),
        expected_col=BaseCols.DELTA,
    ),
)


def normalize_column_name(col: str) -> str:
    stripped = col.strip() if isinstance(col, str) else col
    return COLUMN_ALIASES.get(stripped, COLUMN_ALIASES.get(col, stripped))


def field_catalog() -> list[dict[str, str | bool]]:
    """供 manifest / 文档导出的字段清单。"""
    required = set(REQUIRED_COLUMNS)
    numeric = set(NUMERIC_COLUMNS)
    rows: list[dict[str, str | bool]] = []
    seen: set[str] = set()
    for name in [*REQUIRED_COLUMNS, *OPTIONAL_DIMENSION_COLUMNS, BaseCols.CODE_FULL]:
        if name in seen:
            continue
        seen.add(name)
        rows.append(
            {
                "name": name,
                "required": name in required,
                "numeric": name in numeric,
                "optional_dimension": name in OPTIONAL_DIMENSION_COLUMNS,
            }
        )
    return rows
