import io
import os
from pathlib import Path

import pandas as pd

try:
    from .contracts import (
        AGGREGATION_SPECS,
        BALANCE_RULES,
        META,
        NUMERIC_COLUMNS,
        REQUIRED_COLUMNS,
        SORTABLE_COLUMNS,
        STANDARD_RENAME_MAP,
        VALUE_AGG_COLUMNS,
        XLSX_POSITIONAL_RENAMES,
        AggCols,
        AggregationSpec,
        BaseCols,
        contract_manifest,
        get_table_description,
        get_table_export_meta,
        normalize_column_name,
        register_aggregation_spec as register_contract_aggregation_spec,
        validate_agg_schema,
    )
    from .calculations import TargetCompanyCalculator
    from .run_context import RunContext
except ImportError:
    from contracts import (
        AGGREGATION_SPECS,
        BALANCE_RULES,
        META,
        NUMERIC_COLUMNS,
        REQUIRED_COLUMNS,
        SORTABLE_COLUMNS,
        STANDARD_RENAME_MAP,
        VALUE_AGG_COLUMNS,
        XLSX_POSITIONAL_RENAMES,
        AggCols,
        AggregationSpec,
        BaseCols,
        contract_manifest,
        get_table_description,
        get_table_export_meta,
        normalize_column_name,
        register_aggregation_spec as register_contract_aggregation_spec,
        validate_agg_schema,
    )
    from calculations import TargetCompanyCalculator
    from run_context import RunContext

# 兼容旧导入：from data_calc import AggregationSpec
__all__ = ["AggregationSpec", "ETFDataCalculator"]


class ETFDataCalculator:
    # 类属性指向契约，便于外部/旧代码读取
    REQUIRED_COLUMNS = REQUIRED_COLUMNS
    NUMERIC_COLUMNS = NUMERIC_COLUMNS
    VALUE_AGG_COLUMNS = VALUE_AGG_COLUMNS
    STANDARD_RENAME_MAP = STANDARD_RENAME_MAP
    AGGREGATION_SPECS = AGGREGATION_SPECS

    def __init__(self, base_csv_path: str, run_context: RunContext | None = None):
        self.df_raw = pd.read_csv(base_csv_path, encoding="utf-8-sig")
        self.df_raw = self.normalize_columns(self.df_raw)
        self.output_dir = Path(base_csv_path).parent.parent / "result"
        self.run_context = run_context
        os.makedirs(self.output_dir, exist_ok=True)
        if self.run_context:
            self.run_context.record_value("data_contract", contract_manifest())
        self.validate_input()

    @staticmethod
    def xlsx_to_csv(
        xlsx_file: Path,
        save_csv_path: Path,
        sheet_name: str = META.sheet_name,
    ):
        """
        静态方法：xlsx底表转csv
        :param xlsx_file: 原始xlsx完整路径
        :param save_csv_path: 输出csv保存路径
        :return: 转换完成后的csv路径字符串
        """
        df = pd.read_excel(xlsx_file, sheet_name=sheet_name)
        col_list = df.columns.tolist()
        for index, new_name in XLSX_POSITIONAL_RENAMES.items():
            if index < len(col_list):
                col_list[index] = new_name
        df.columns = col_list

        df.to_csv(save_csv_path, index=False, encoding="utf-8-sig")
        print(f"XLSX已转换为CSV，保存路径：{save_csv_path.resolve()}")
        return str(save_csv_path)

    @staticmethod
    def safe_div(numerator, denominator):
        return numerator.div(denominator.where(denominator != 0))

    @classmethod
    def normalize_columns(cls, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df.columns = [normalize_column_name(col) for col in df.columns]
        return df

    @classmethod
    def register_aggregation_spec(cls, spec: AggregationSpec):
        register_contract_aggregation_spec(spec)
        cls.AGGREGATION_SPECS = AGGREGATION_SPECS

    def validate_input(self):
        missing = [col for col in REQUIRED_COLUMNS if col not in self.df_raw.columns]
        if missing:
            raise ValueError(f"底表缺少必要字段：{missing}")

        for col in NUMERIC_COLUMNS:
            self.df_raw[col] = pd.to_numeric(self.df_raw[col], errors="raise")

        rule_results = {}
        for rule in BALANCE_RULES:
            rule_results[f"bad_{rule.name}_count"] = rule.bad_count(self.df_raw)

        if self.run_context:
            self.run_context.record_value(
                "input_validation",
                {
                    "data_contract_version": META.version,
                    "row_count": int(len(self.df_raw)),
                    "column_count": int(len(self.df_raw.columns)),
                    "tolerance": META.validation_tolerance,
                    **rule_results,
                },
            )

        for rule in BALANCE_RULES:
            bad_count = rule_results[f"bad_{rule.name}_count"]
            if bad_count:
                raise ValueError(f"底表校验失败：{bad_count} 行不满足 {rule.description}")

    def calc_aggregation(self, spec_or_name: AggregationSpec | str) -> pd.DataFrame:
        spec = self.get_aggregation_spec(spec_or_name)
        self.validate_aggregation_spec(spec)

        agg_df = self.df_raw.groupby(spec.group_cols, dropna=False).agg(VALUE_AGG_COLUMNS).reset_index()
        agg_df = agg_df.rename(columns={**spec.rename_map, **STANDARD_RENAME_MAP})

        agg_df[AggCols.DELTA] = agg_df[AggCols.END_SIZE] - agg_df[AggCols.START_SIZE]
        agg_df[AggCols.GROWTH_RATE] = self.safe_div(agg_df[AggCols.DELTA], agg_df[AggCols.START_SIZE])
        agg_df[AggCols.HOLDING_GROWTH] = self.safe_div(
            agg_df[AggCols.HOLDING_CONTRIB], agg_df[AggCols.START_SIZE]
        )
        agg_df = agg_df.sort_values(spec.sort_by, ascending=spec.ascending).reset_index(drop=True)

        if spec.include_rank:
            agg_df[spec.rank_col] = agg_df.index + 1
        if spec.include_top_products:
            agg_df = self.attach_top_products(agg_df, spec)

        missing_cols = validate_agg_schema(spec.name, agg_df)
        if missing_cols:
            raise ValueError(f"聚合表 {spec.name} 缺少契约字段：{missing_cols}")
        return agg_df

    def calc_registered_aggs(self, names: list[str] | None = None) -> dict[str, pd.DataFrame]:
        target_names = names or list(AGGREGATION_SPECS.keys())
        return {name: self.calc_aggregation(name) for name in target_names}

    def get_aggregation_spec(self, spec_or_name: AggregationSpec | str) -> AggregationSpec:
        if isinstance(spec_or_name, AggregationSpec):
            return spec_or_name
        if spec_or_name not in AGGREGATION_SPECS:
            raise KeyError(f"未注册的聚合规格：{spec_or_name}")
        return AGGREGATION_SPECS[spec_or_name]

    def validate_aggregation_spec(self, spec: AggregationSpec):
        missing_group_cols = [col for col in spec.group_cols if col not in self.df_raw.columns]
        if missing_group_cols:
            raise ValueError(f"聚合规格 {spec.name} 使用了不存在的分组字段：{missing_group_cols}")

        missing_rename_cols = [col for col in spec.group_cols if col not in spec.rename_map]
        if missing_rename_cols:
            raise ValueError(f"聚合规格 {spec.name} 缺少分组字段重命名：{missing_rename_cols}")

        if spec.sort_by not in SORTABLE_COLUMNS:
            raise ValueError(f"聚合规格 {spec.name} 使用了不支持的排序字段：{spec.sort_by}")

    def attach_top_products(self, agg_df: pd.DataFrame, spec: AggregationSpec) -> pd.DataFrame:
        top_rows = []
        output_group_cols = spec.output_group_cols

        for _, agg_row in agg_df[output_group_cols].iterrows():
            mask = pd.Series(True, index=self.df_raw.index)
            top_dict = {col: agg_row[col] for col in output_group_cols}
            for raw_col, output_col in zip(spec.group_cols, output_group_cols):
                mask &= self.df_raw[raw_col] == agg_row[output_col]

            top = self.df_raw[mask].sort_values(spec.top_sort_col, ascending=False).head(spec.top_n)
            for idx in range(spec.top_n):
                rank = idx + 1
                if len(top) > idx:
                    row = top.iloc[idx]
                    top_dict[f"TOP{rank}产品"] = (
                        f"{row[BaseCols.CODE_6]}{row[BaseCols.FUND_NAME]}"
                        f"({row[spec.top_sort_col]:.2f}亿)"
                    )
                    top_dict[f"TOP{rank}代码"] = row[BaseCols.CODE_6]
                    top_dict[f"TOP{rank}简称"] = row[BaseCols.FUND_NAME]
                    top_dict[f"TOP{rank}增量"] = row[spec.top_sort_col]
                else:
                    top_dict[f"TOP{rank}产品"] = "-"
                    top_dict[f"TOP{rank}代码"] = ""
                    top_dict[f"TOP{rank}简称"] = ""
                    top_dict[f"TOP{rank}增量"] = None
            top_rows.append(top_dict)

        return agg_df.merge(pd.DataFrame(top_rows), on=output_group_cols, how="left")

    def calc_area_agg(self) -> pd.DataFrame:
        return self.calc_aggregation("area")

    def calc_track_agg(self) -> pd.DataFrame:
        return self.calc_aggregation("track")

    def calc_manager_agg(self) -> pd.DataFrame:
        return self.calc_aggregation("manager")

    def calc_target_company_tables(
        self,
        company: str | None = None,
        manager_agg: pd.DataFrame | None = None,
    ) -> dict[str, pd.DataFrame]:
        manager_df = manager_agg if manager_agg is not None else self.calc_manager_agg()
        calc = TargetCompanyCalculator(self.df_raw, company=company or META.target_company)
        return calc.build_tables(manager_agg=manager_df)

    def calc_analysis_tables(
        self,
        agg_names: list[str] | None = None,
        include_target_company: bool = True,
        target_company: str | None = None,
    ) -> dict[str, pd.DataFrame]:
        """标准聚合 + 目标公司切片，供导出与 AI 使用。"""
        names = agg_names or ["area", "track", "manager", "national_team"]
        tables = self.calc_registered_aggs(names)
        if include_target_company:
            tables.update(
                self.calc_target_company_tables(
                    company=target_company,
                    manager_agg=tables.get("manager"),
                )
            )
        return tables

    @staticmethod
    def prepare_df_for_excel(df: pd.DataFrame) -> pd.DataFrame:
        """导出前整理：数值保留合理小数，便于 Excel 再制图。"""
        out = df.copy()
        numeric_cols = out.select_dtypes(include="number").columns
        out[numeric_cols] = out[numeric_cols].round(4)
        return out

    @classmethod
    def build_excel_catalog(cls, tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
        rows = []
        for name, df in tables.items():
            sheet_name, csv_name = get_table_export_meta(name)
            rows.append(
                {
                    "工作表": sheet_name,
                    "表键": name,
                    "说明": get_table_description(name),
                    "行数": int(len(df)),
                    "列数": int(len(df.columns)),
                    "对应CSV": csv_name,
                }
            )
        catalog = pd.DataFrame(rows)
        catalog.insert(0, "序号", range(1, len(catalog) + 1))
        return catalog

    @classmethod
    def write_tables_to_excel(cls, tables: dict[str, pd.DataFrame], save_path: Path | str) -> Path:
        """将聚合表写入多 sheet Excel，首表为目录。"""
        path = Path(save_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        catalog = cls.build_excel_catalog(tables)
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            catalog.to_excel(writer, sheet_name="目录", index=False)
            for name, df in tables.items():
                sheet_name, _ = get_table_export_meta(name)
                cls.prepare_df_for_excel(df).to_excel(writer, sheet_name=sheet_name, index=False)
        return path

    @classmethod
    def tables_to_excel_bytes(cls, tables: dict[str, pd.DataFrame]) -> bytes:
        buffer = io.BytesIO()
        catalog = cls.build_excel_catalog(tables)
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            catalog.to_excel(writer, sheet_name="目录", index=False)
            for name, df in tables.items():
                sheet_name, _ = get_table_export_meta(name)
                cls.prepare_df_for_excel(df).to_excel(writer, sheet_name=sheet_name, index=False)
        return buffer.getvalue()

    def export_agg_tables(self, tables: dict[str, pd.DataFrame]):
        save_path = Path(self.output_dir) / "ETF聚合汇总表.xlsx"
        self.write_tables_to_excel(tables, save_path)

        if self.run_context:
            for name, df in tables.items():
                _, csv_name = get_table_export_meta(name)
                table_path = self.run_context.table_dir / csv_name
                df.to_csv(table_path, index=False, encoding="utf-8-sig")
                self.run_context.record_artifact(f"{name}_agg", table_path)
            run_excel = self.run_context.run_dir / "ETF聚合汇总表.xlsx"
            self.write_tables_to_excel(tables, run_excel)
            self.run_context.record_artifact("agg_excel", run_excel)
            self.run_context.record_artifact("agg_excel_latest", save_path)
            self.run_context.record_value("aggregation_tables", list(tables.keys()))

        print(f"聚合数据表已导出至：{save_path.resolve()}")
        return str(save_path)

    def export_all_agg(self, area_df, track_df, manager_df):
        return self.export_agg_tables({
            "area": area_df,
            "track": track_df,
            "manager": manager_df,
        })
