"""非标准 groupby 的确定性计算模块。"""

from .target_company import TargetCompanyCalculator, match_company_mask

__all__ = ["TargetCompanyCalculator", "match_company_mask"]
