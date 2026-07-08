import pandas as pd
import os
from dataclasses import dataclass
from pathlib import Path

try:
    from .run_context import RunContext
except ImportError:
    from run_context import RunContext


@dataclass(frozen=True)
class AggregationSpec:
    name: str
    sheet_name: str
    csv_name: str
    group_cols: list[str]
    rename_map: dict[str, str]
    sort_by: str = "规模增量"
    ascending: bool = False
    include_rank: bool = False
    rank_col: str = "增量排名"
    include_top_products: bool = False
    top_n: int = 3
    top_sort_col: str = "增量26H1"


class ETFDataCalculator:
    COLUMN_ALIASES = {
        "是否国家队\n持仓": "是否国家队",
    }
    REQUIRED_COLUMNS = [
        "前6位代码",
        "基金简称",
        "基金公司",
        "25Q4",
        "26Q2",
        "增量26H1",
        "增速26H1%",
        "26H1新发",
        "26H1净值",
        "26H1持营",
        "赛道（结合区域和主题打标）",
        "A股、港股or其他跨境",
    ]
    NUMERIC_COLUMNS = [
        "25Q4",
        "26Q2",
        "增量26H1",
        "增速26H1%",
        "26H1新发",
        "26H1净值",
        "26H1持营",
    ]
    VALUE_AGG_COLUMNS = {
        "25Q4": "sum",
        "26Q2": "sum",
        "26H1新发": "sum",
        "26H1净值": "sum",
        "26H1持营": "sum",
    }
    STANDARD_RENAME_MAP = {
        "25Q4": "期初规模",
        "26Q2": "期末规模",
        "26H1新发": "新发贡献",
        "26H1净值": "净值贡献",
        "26H1持营": "持营贡献",
    }
    AGGREGATION_SPECS = {
        "area": AggregationSpec(
            name="area",
            sheet_name="区域ETF汇总",
            csv_name="area_agg.csv",
            group_cols=["A股、港股or其他跨境"],
            rename_map={"A股、港股or其他跨境": "区域类型"},
        ),
        "track": AggregationSpec(
            name="track",
            sheet_name="赛道ETF汇总",
            csv_name="track_agg.csv",
            group_cols=["赛道（结合区域和主题打标）"],
            rename_map={"赛道（结合区域和主题打标）": "赛道类型"},
            include_top_products=True,
        ),
        "manager": AggregationSpec(
            name="manager",
            sheet_name="管理人排名",
            csv_name="manager_agg.csv",
            group_cols=["基金公司"],
            rename_map={"基金公司": "管理人"},
            include_rank=True,
            include_top_products=True,
        ),
        "national_team": AggregationSpec(
            name="national_team",
            sheet_name="国家队汇总",
            csv_name="national_team_agg.csv",
            group_cols=["是否国家队"],
            rename_map={"是否国家队": "是否国家队"},
        ),
    }

    def __init__(self, base_csv_path: str, run_context: RunContext | None = None):
        # 初始化直接读取转换好的csv，不再读xlsx
        self.df_raw = pd.read_csv(base_csv_path, encoding="utf-8-sig")
        self.df_raw = self.normalize_columns(self.df_raw)
        self.output_dir = Path(base_csv_path).parent.parent / "result"
        self.run_context = run_context
        os.makedirs(self.output_dir, exist_ok=True)
        self.validate_input()

    @staticmethod
    def xlsx_to_csv(xlsx_file: Path, save_csv_path: Path, sheet_name: str = "260630股票etf底表"):
        """
        静态方法：xlsx底表转csv
        :param xlsx_file: 原始xlsx完整路径
        :param save_csv_path: 输出csv保存路径
        :return: 转换完成后的csv路径字符串
        """
        # 读取指定sheet
        df = pd.read_excel(xlsx_file, sheet_name=sheet_name)
        # 修正列名（和之前逻辑保持一致）
        col_list = df.columns.tolist()
        col_list[1] = "基金代码_全量"
        col_list[2] = "基金简称"
        df.columns = col_list

        # 保存csv，utf-8-sig保证中文不乱码
        df.to_csv(save_csv_path, index=False, encoding="utf-8-sig")
        print(f"XLSX已转换为CSV，保存路径：{save_csv_path.resolve()}")
        return str(save_csv_path)

    @staticmethod
    def safe_div(numerator, denominator):
        return numerator.div(denominator.where(denominator != 0))

    @classmethod
    def normalize_columns(cls, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df.columns = [cls.COLUMN_ALIASES.get(col, col.strip()) for col in df.columns]
        return df

    @classmethod
    def register_aggregation_spec(cls, spec: AggregationSpec):
        cls.AGGREGATION_SPECS[spec.name] = spec

    def validate_input(self):
        missing = [col for col in self.REQUIRED_COLUMNS if col not in self.df_raw.columns]
        if missing:
            raise ValueError(f"底表缺少必要字段：{missing}")

        for col in self.NUMERIC_COLUMNS:
            self.df_raw[col] = pd.to_numeric(self.df_raw[col], errors="raise")

        calc_delta = self.df_raw["26Q2"] - self.df_raw["25Q4"]
        delta_diff = (calc_delta - self.df_raw["增量26H1"]).abs()
        bad_delta_count = int((delta_diff > 0.02).sum())

        contribution_delta = self.df_raw["26H1新发"] + self.df_raw["26H1净值"] + self.df_raw["26H1持营"]
        contribution_diff = (contribution_delta - self.df_raw["增量26H1"]).abs()
        bad_contribution_count = int((contribution_diff > 0.02).sum())

        if self.run_context:
            self.run_context.record_value(
                "input_validation",
                {
                    "row_count": int(len(self.df_raw)),
                    "column_count": int(len(self.df_raw.columns)),
                    "bad_delta_count": bad_delta_count,
                    "bad_contribution_count": bad_contribution_count,
                    "tolerance": 0.02,
                },
            )

        if bad_delta_count:
            raise ValueError(f"底表校验失败：{bad_delta_count} 行的 增量26H1 != 26Q2 - 25Q4")
        if bad_contribution_count:
            raise ValueError(f"底表校验失败：{bad_contribution_count} 行的 增量26H1 != 新发 + 净值 + 持营")

    def calc_aggregation(self, spec_or_name: AggregationSpec | str) -> pd.DataFrame:
        spec = self.get_aggregation_spec(spec_or_name)
        self.validate_aggregation_spec(spec)

        agg_df = self.df_raw.groupby(spec.group_cols, dropna=False).agg(self.VALUE_AGG_COLUMNS).reset_index()
        agg_df = agg_df.rename(columns={**spec.rename_map, **self.STANDARD_RENAME_MAP})

        agg_df["规模增量"] = agg_df["期末规模"] - agg_df["期初规模"]
        agg_df["规模增速"] = self.safe_div(agg_df["规模增量"], agg_df["期初规模"])
        agg_df["持营增速"] = self.safe_div(agg_df["持营贡献"], agg_df["期初规模"])
        agg_df = agg_df.sort_values(spec.sort_by, ascending=spec.ascending).reset_index(drop=True)

        if spec.include_rank:
            agg_df[spec.rank_col] = agg_df.index + 1
        if spec.include_top_products:
            agg_df = self.attach_top_products(agg_df, spec)
        return agg_df

    def calc_registered_aggs(self, names: list[str] | None = None) -> dict[str, pd.DataFrame]:
        target_names = names or list(self.AGGREGATION_SPECS.keys())
        return {name: self.calc_aggregation(name) for name in target_names}

    def get_aggregation_spec(self, spec_or_name: AggregationSpec | str) -> AggregationSpec:
        if isinstance(spec_or_name, AggregationSpec):
            return spec_or_name
        if spec_or_name not in self.AGGREGATION_SPECS:
            raise KeyError(f"未注册的聚合规格：{spec_or_name}")
        return self.AGGREGATION_SPECS[spec_or_name]

    def validate_aggregation_spec(self, spec: AggregationSpec):
        missing_group_cols = [col for col in spec.group_cols if col not in self.df_raw.columns]
        if missing_group_cols:
            raise ValueError(f"聚合规格 {spec.name} 使用了不存在的分组字段：{missing_group_cols}")

        missing_rename_cols = [col for col in spec.group_cols if col not in spec.rename_map]
        if missing_rename_cols:
            raise ValueError(f"聚合规格 {spec.name} 缺少分组字段重命名：{missing_rename_cols}")

        if spec.sort_by not in [*self.STANDARD_RENAME_MAP.values(), "规模增量", "规模增速", "持营增速"]:
            raise ValueError(f"聚合规格 {spec.name} 使用了不支持的排序字段：{spec.sort_by}")

    def attach_top_products(self, agg_df: pd.DataFrame, spec: AggregationSpec) -> pd.DataFrame:
        top_rows = []
        output_group_cols = [spec.rename_map[col] for col in spec.group_cols]

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
                    top_dict[f"TOP{rank}产品"] = f"{row['前6位代码']}{row['基金简称']}({row[spec.top_sort_col]:.2f}亿)"
                    top_dict[f"TOP{rank}代码"] = row["前6位代码"]
                    top_dict[f"TOP{rank}简称"] = row["基金简称"]
                    top_dict[f"TOP{rank}增量"] = row[spec.top_sort_col]
                else:
                    top_dict[f"TOP{rank}产品"] = "-"
                    top_dict[f"TOP{rank}代码"] = ""
                    top_dict[f"TOP{rank}简称"] = ""
                    top_dict[f"TOP{rank}增量"] = None
            top_rows.append(top_dict)

        return agg_df.merge(pd.DataFrame(top_rows), on=output_group_cols, how="left")

    # 维度1：按区域聚合 A股/港股/其他跨境
    def calc_area_agg(self) -> pd.DataFrame:
        return self.calc_aggregation("area")

    # 维度2：按赛道聚合（结合区域和主题打标）
    def calc_track_agg(self) -> pd.DataFrame:
        return self.calc_aggregation("track")

    # 维度3：按管理人聚合，按规模增量排名
    def calc_manager_agg(self) -> pd.DataFrame:
        return self.calc_aggregation("manager")

    def export_agg_tables(self, tables: dict[str, pd.DataFrame]):
        save_path = os.path.join(self.output_dir, "ETF聚合汇总表.xlsx")
        with pd.ExcelWriter(save_path) as writer:
            for name, df in tables.items():
                spec = self.get_aggregation_spec(name)
                df.to_excel(writer, sheet_name=spec.sheet_name, index=False)

        if self.run_context:
            for name, df in tables.items():
                spec = self.get_aggregation_spec(name)
                table_path = self.run_context.table_dir / spec.csv_name
                df.to_csv(table_path, index=False, encoding="utf-8-sig")
                self.run_context.record_artifact(f"{name}_agg", table_path)
            self.run_context.record_artifact("agg_excel", Path(save_path))
            self.run_context.record_value("aggregation_tables", list(tables.keys()))

        print(f"聚合数据表已导出至：{save_path}")
        return save_path

    # 输出全部聚合结果为Excel
    def export_all_agg(self, area_df, track_df, manager_df):
        return self.export_agg_tables({
            "area": area_df,
            "track": track_df,
            "manager": manager_df,
        })
