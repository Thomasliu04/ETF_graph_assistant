"""目标公司（默认银华）切片：总览、分区域、分赛道、产品梯队。"""

from __future__ import annotations

import re

import pandas as pd

try:
    from ..contracts import AggCols, BaseCols, META, STANDARD_RENAME_MAP, VALUE_AGG_COLUMNS
except ImportError:
    from contracts import AggCols, BaseCols, META, STANDARD_RENAME_MAP, VALUE_AGG_COLUMNS


def match_company_mask(
    series: pd.Series,
    company: str,
    aliases: tuple[str, ...] | None = None,
) -> pd.Series:
    """按全名/别名/包含关系匹配管理人。"""
    names = [n for n in [company, *(aliases or ())] if n]
    text = series.astype(str)
    mask = pd.Series(False, index=series.index)
    for name in names:
        mask |= text == name
    if mask.any():
        return mask
    for name in names:
        partial = text.str.contains(re.escape(name), na=False)
        if partial.any():
            return partial
    return mask


def resolve_company_label(series: pd.Series, company: str, aliases: tuple[str, ...] | None = None) -> str:
    mask = match_company_mask(series, company, aliases)
    if not mask.any():
        return company
    return str(series[mask].iloc[0])


class TargetCompanyCalculator:
    PRODUCT_COLUMNS = [
        BaseCols.CODE_6,
        BaseCols.FUND_NAME,
        BaseCols.MANAGER,
        BaseCols.TRACK,
        BaseCols.AREA,
        BaseCols.START_SIZE,
        BaseCols.END_SIZE,
        BaseCols.DELTA,
        BaseCols.GROWTH_RATE,
        BaseCols.NEW_ISSUE,
        BaseCols.NAV_CONTRIB,
        BaseCols.HOLDING_CONTRIB,
    ]

    def __init__(
        self,
        df_raw: pd.DataFrame,
        company: str | None = None,
        aliases: tuple[str, ...] | None = None,
        top_n: int = 3,
    ):
        self.df_raw = df_raw
        self.company = company or META.target_company
        self.aliases = aliases if aliases is not None else META.target_company_aliases
        self.top_n = top_n
        self.mask = match_company_mask(df_raw[BaseCols.MANAGER], self.company, self.aliases)
        self.company_df = df_raw[self.mask].copy()
        self.resolved_name = (
            resolve_company_label(df_raw[BaseCols.MANAGER], self.company, self.aliases)
            if self.mask.any()
            else self.company
        )

    def require_data(self) -> None:
        if self.company_df.empty:
            raise ValueError(
                f"底表中未找到目标公司「{self.company}」及其别名 {list(self.aliases)}。"
                "请检查管理人列是否包含该公司，或在 scripts/contracts/meta.py 中更新 "
                "target_company / target_company_aliases。"
            )

    def _aggregate(self, group_col: str, output_col: str) -> pd.DataFrame:
        agg_df = (
            self.company_df.groupby(group_col, dropna=False)
            .agg(VALUE_AGG_COLUMNS)
            .reset_index()
            .rename(columns={group_col: output_col, **STANDARD_RENAME_MAP})
        )
        agg_df[AggCols.DELTA] = agg_df[AggCols.END_SIZE] - agg_df[AggCols.START_SIZE]
        agg_df[AggCols.GROWTH_RATE] = agg_df[AggCols.DELTA] / agg_df[AggCols.START_SIZE].where(
            agg_df[AggCols.START_SIZE] != 0
        )
        agg_df[AggCols.HOLDING_GROWTH] = agg_df[AggCols.HOLDING_CONTRIB] / agg_df[
            AggCols.START_SIZE
        ].where(agg_df[AggCols.START_SIZE] != 0)
        return agg_df.sort_values(AggCols.DELTA, ascending=False).reset_index(drop=True)

    def calc_summary(self, manager_agg: pd.DataFrame | None = None) -> pd.DataFrame:
        self.require_data()
        start = float(self.company_df[BaseCols.START_SIZE].sum())
        end = float(self.company_df[BaseCols.END_SIZE].sum())
        new_issue = float(self.company_df[BaseCols.NEW_ISSUE].sum())
        nav = float(self.company_df[BaseCols.NAV_CONTRIB].sum())
        holding = float(self.company_df[BaseCols.HOLDING_CONTRIB].sum())
        delta = end - start
        growth = delta / start if start else None
        holding_growth = holding / start if start else None

        rank = None
        manager_delta = None
        if manager_agg is not None and AggCols.MANAGER in manager_agg.columns:
            m_mask = match_company_mask(manager_agg[AggCols.MANAGER], self.company, self.aliases)
            if m_mask.any():
                row = manager_agg.loc[m_mask].iloc[0]
                rank = int(row[AggCols.RANK]) if AggCols.RANK in manager_agg.columns else None
                manager_delta = float(row[AggCols.DELTA])

        return pd.DataFrame(
            [
                {
                    "目标公司": self.resolved_name,
                    "匹配关键词": self.company,
                    "产品数量": int(len(self.company_df)),
                    AggCols.START_SIZE: start,
                    AggCols.END_SIZE: end,
                    AggCols.NEW_ISSUE: new_issue,
                    AggCols.NAV_CONTRIB: nav,
                    AggCols.HOLDING_CONTRIB: holding,
                    AggCols.DELTA: delta,
                    AggCols.GROWTH_RATE: growth,
                    AggCols.HOLDING_GROWTH: holding_growth,
                    "增量排名": rank,
                    "管理人表规模增量": manager_delta,
                }
            ]
        )

    def calc_by_area(self) -> pd.DataFrame:
        self.require_data()
        return self._aggregate(BaseCols.AREA, AggCols.AREA_TYPE)

    def calc_by_track(self) -> pd.DataFrame:
        self.require_data()
        return self._aggregate(BaseCols.TRACK, AggCols.TRACK_TYPE)

    def calc_products(self) -> pd.DataFrame:
        self.require_data()
        cols = [c for c in self.PRODUCT_COLUMNS if c in self.company_df.columns]
        products = self.company_df[cols].copy()
        products = products.rename(
            columns={
                BaseCols.CODE_6: "代码",
                BaseCols.FUND_NAME: "简称",
                BaseCols.MANAGER: "管理人",
                BaseCols.TRACK: AggCols.TRACK_TYPE,
                BaseCols.AREA: AggCols.AREA_TYPE,
                **STANDARD_RENAME_MAP,
                BaseCols.DELTA: AggCols.DELTA,
                BaseCols.GROWTH_RATE: AggCols.GROWTH_RATE,
            }
        )
        products = products.sort_values(AggCols.DELTA, ascending=False).reset_index(drop=True)
        products.insert(0, "增量排名_公司内", products.index + 1)
        return products

    def calc_top_bottom_products(self) -> pd.DataFrame:
        """增量 TOP N + 缩水 TOP N，供 AI 产品梯队分析。"""
        products = self.calc_products()
        top = products.head(self.top_n).copy()
        top.insert(0, "梯队", "增量TOP")
        bottom = products.sort_values(AggCols.DELTA, ascending=True).head(self.top_n).copy()
        bottom.insert(0, "梯队", "缩水TOP")
        return pd.concat([top, bottom], ignore_index=True)

    def build_tables(self, manager_agg: pd.DataFrame | None = None) -> dict[str, pd.DataFrame]:
        return {
            "target_summary": self.calc_summary(manager_agg=manager_agg),
            "target_by_area": self.calc_by_area(),
            "target_by_track": self.calc_by_track(),
            "target_products": self.calc_products(),
            "target_top_bottom": self.calc_top_bottom_products(),
        }
