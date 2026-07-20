"""对照测试：登记表加载后，内置聚合与目标公司切片结果与纯代码内置规格一致。"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd

from scripts.contracts.aggregations import BUILTIN_AGGREGATION_SPECS
from scripts.contracts.base_table import BaseCols
from scripts.contracts.table_plugins import (
    ensure_plugins_loaded,
    write_registry_excel,
)
from scripts.data_calc import ETFDataCalculator


def _make_sample_csv(path: Path) -> Path:
    rows = []
    areas = ["A股", "港股", "其他跨境"]
    tracks = ["宽基", "行业", "跨境"]
    managers = ["华夏基金", "易方达基金", "银华基金管理股份有限公司"]
    for i in range(12):
        start = 10.0 + i
        end = start + (i % 5) - 1
        new_issue = float(i % 3)
        nav = float((i % 4) - 1)
        holding = (end - start) - new_issue - nav
        rows.append(
            {
                BaseCols.CODE_6: f"{100000 + i}",
                BaseCols.CODE_FULL: f"{100000 + i}.OF",
                BaseCols.FUND_NAME: f"样本基金{i}",
                BaseCols.MANAGER: managers[i % 3],
                BaseCols.START_SIZE: start,
                BaseCols.END_SIZE: end,
                BaseCols.DELTA: end - start,
                BaseCols.GROWTH_RATE: (end - start) / start,
                BaseCols.NEW_ISSUE: new_issue,
                BaseCols.NAV_CONTRIB: nav,
                BaseCols.HOLDING_CONTRIB: holding,
                BaseCols.TRACK: tracks[i % 3],
                BaseCols.AREA: areas[i % 3],
                BaseCols.NATIONAL_TEAM: "是" if i % 2 == 0 else "否",
            }
        )
    df = pd.DataFrame(rows)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def _assert_frame_equal(left: pd.DataFrame, right: pd.DataFrame, label: str) -> None:
    left2 = left.reset_index(drop=True)
    right2 = right.reset_index(drop=True)
    assert list(left2.columns) == list(right2.columns), f"{label} 列不一致: {list(left2.columns)} vs {list(right2.columns)}"
    pd.testing.assert_frame_equal(
        left2,
        right2,
        check_dtype=False,
        atol=1e-8,
        rtol=1e-8,
        obj=label,
    )


def test_registry_parity_with_builtin_specs():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        csv_path = _make_sample_csv(tmp_path / "base.csv")
        registry_path = write_registry_excel(tmp_path / "聚合登记表.xlsx")
        missing = tmp_path / "不存在.xlsx"
        names = list(BUILTIN_AGGREGATION_SPECS.keys())
        keys = [
            "area",
            "track",
            "manager",
            "national_team",
            "target_summary",
            "target_by_area",
            "target_by_track",
            "target_top_bottom",
        ]

        # 回退内置
        ensure_plugins_loaded(force=True, path=missing)
        builtin_tables = ETFDataCalculator(str(csv_path)).calc_analysis_tables(
            agg_names=names,
            include_target_company=True,
            target_company="银华基金",
        )

        # 登记表加载
        ensure_plugins_loaded(force=True, path=registry_path)
        registry_tables = ETFDataCalculator(str(csv_path)).calc_analysis_tables(
            agg_names=names,
            include_target_company=True,
            target_company="银华基金",
        )

        for key in keys:
            assert key in builtin_tables and key in registry_tables
            _assert_frame_equal(builtin_tables[key], registry_tables[key], key)


def test_analysis_order_matches_legacy():
    ensure_plugins_loaded(force=True)
    from scripts.contracts import analysis_table_order
    from scripts.report_sections import get_section_table_keys

    order = [k for k, _, _ in analysis_table_order()]
    assert order[:4] == ["area", "track", "manager", "national_team"]
    assert order[4:8] == [
        "target_summary",
        "target_by_area",
        "target_by_track",
        "target_top_bottom",
    ]
    sections = get_section_table_keys()
    assert sections["area"] == ("area", "national_team")
    assert sections["track"] == ("track",)
    assert sections["manager"] == ("manager",)
    assert sections["target"][-1] == "manager"


if __name__ == "__main__":
    test_registry_parity_with_builtin_specs()
    test_analysis_order_matches_legacy()
    print("parity ok")
