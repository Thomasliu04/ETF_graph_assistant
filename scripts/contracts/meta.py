"""数据契约元信息：版本、统计区间、单位、底表 sheet 等。"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class DataContractMeta:
    """全局口径与版本。换报告期时优先改这里，而不是散落在业务代码里。"""

    version: str = "0.3.0"
    unit: str = "亿元"
    sheet_name: str = "260630股票etf底表"
    period_start: str = "2025-12-31"
    period_end: str = "2026-06-30"
    period_label: str = "2026H1"
    target_company: str = "银华基金"
    # 底表管理人全称可能更长；匹配时会使用这些别名/包含关系
    target_company_aliases: tuple[str, ...] = (
        "银华基金管理股份有限公司",
        "银华基金",
    )
    validation_tolerance: float = 0.02

    def as_dict(self) -> dict:
        data = asdict(self)
        data["target_company_aliases"] = list(self.target_company_aliases)
        return data

    @property
    def period_title(self) -> str:
        return f"{self.period_start} ~ {self.period_end}"


META = DataContractMeta()
