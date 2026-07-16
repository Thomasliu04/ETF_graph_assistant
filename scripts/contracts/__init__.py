"""
数据契约层：底表字段、校验规则、聚合输出 schema 的单一事实来源。

换报告期 / 改列名 / 加聚合维度时，优先改本包，再改 Skill 与流水线注册。
"""

from __future__ import annotations

from .aggregations import (
    AGGREGATION_SPECS,
    CORE_METRIC_COLUMNS,
    EXTRA_TABLE_SPECS,
    SORTABLE_COLUMNS,
    STANDARD_RENAME_MAP,
    VALUE_AGG_COLUMNS,
    AggCols,
    AggregationSpec,
    TableExportSpec,
    get_table_description,
    get_table_export_meta,
    register_aggregation_spec,
    validate_agg_schema,
)
from .base_table import (
    BALANCE_RULES,
    COLUMN_ALIASES,
    NUMERIC_COLUMNS,
    OPTIONAL_DIMENSION_COLUMNS,
    REQUIRED_COLUMNS,
    XLSX_POSITIONAL_RENAMES,
    BalanceRule,
    BaseCols,
    field_catalog,
    normalize_column_name,
)
from .meta import META, DataContractMeta


def contract_manifest() -> dict:
    """写入 run_manifest，便于审计本次运行使用的口径版本。"""
    return {
        "data_contract_version": META.version,
        "meta": META.as_dict(),
        "base_fields": field_catalog(),
        "aggregation_specs": {
            name: {
                "sheet_name": spec.sheet_name,
                "csv_name": spec.csv_name,
                "group_cols": list(spec.group_cols),
                "rename_map": dict(spec.rename_map),
                "sort_by": spec.sort_by,
                "include_rank": spec.include_rank,
                "include_top_products": spec.include_top_products,
                "required_output_columns": spec.required_output_columns(),
            }
            for name, spec in AGGREGATION_SPECS.items()
        },
        "extra_table_specs": {
            name: {
                "sheet_name": spec.sheet_name,
                "csv_name": spec.csv_name,
                "description": spec.description,
            }
            for name, spec in EXTRA_TABLE_SPECS.items()
        },
        "balance_rules": [
            {"name": rule.name, "description": rule.description, "tolerance": rule.tolerance}
            for rule in BALANCE_RULES
        ],
    }


__all__ = [
    "AGGREGATION_SPECS",
    "BALANCE_RULES",
    "COLUMN_ALIASES",
    "CORE_METRIC_COLUMNS",
    "EXTRA_TABLE_SPECS",
    "META",
    "NUMERIC_COLUMNS",
    "OPTIONAL_DIMENSION_COLUMNS",
    "REQUIRED_COLUMNS",
    "SORTABLE_COLUMNS",
    "STANDARD_RENAME_MAP",
    "VALUE_AGG_COLUMNS",
    "XLSX_POSITIONAL_RENAMES",
    "AggCols",
    "AggregationSpec",
    "BalanceRule",
    "BaseCols",
    "DataContractMeta",
    "TableExportSpec",
    "contract_manifest",
    "field_catalog",
    "get_table_description",
    "get_table_export_meta",
    "normalize_column_name",
    "register_aggregation_spec",
    "validate_agg_schema",
]
