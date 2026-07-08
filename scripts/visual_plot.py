import matplotlib.pyplot as plt
import pandas as pd
import os
import warnings
from pathlib import Path

try:
    from .run_context import RunContext
except ImportError:
    from run_context import RunContext

# 屏蔽全部字体相关警告
warnings.filterwarnings("ignore", category=UserWarning)

# 仅保留Mac稳定自带字体，删掉PingFang SC
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False
# =================================

class ETFVisualizer:
    def __init__(self, save_dir="output", run_context: RunContext | None = None):
        self.save_dir = Path(save_dir)
        self.run_context = run_context
        os.makedirs(save_dir, exist_ok=True)

    # 区域规模增量对比图
    def plot_area_increment(self, area_df: pd.DataFrame):
        fig, ax = plt.subplots(figsize=(10, 5))
        x = area_df["区域类型"]
        y = area_df["规模增量"]
        # 颜色区分正负增长
        colors = ["#2ca02c" if val >= 0 else "#d62728" for val in y]
        bars = ax.bar(x, y, color=colors)
        ax.set_title("2025.12.31-2026.06.30 各区域ETF规模增量（亿元）", fontsize=14)
        ax.set_ylabel("规模增量(亿元)", fontsize=12)
        # 标注数值
        for bar in bars:
            h = bar.get_height()
            ax.text(bar.get_x()+bar.get_width()/2, h, f"{h:.1f}", ha="center", va="bottom" if h>=0 else "top", fontsize=11)
        plt.tight_layout()
        save_path = self.save_dir / "区域ETF增量对比.png"
        plt.savefig(save_path, dpi=300, bbox_inches="tight")
        if self.run_context:
            chart_path = self.run_context.chart_dir / "区域ETF增量对比.png"
            fig.savefig(chart_path, dpi=300, bbox_inches="tight")
            self.run_context.record_artifact("chart_area_increment", chart_path)
        print(f"✅ 区域增量对比图已保存至：{save_path}")
        return fig

    # 赛道规模增速TOP10图
    def plot_track_top10(self, track_df: pd.DataFrame):
        top10 = track_df.head(10)
        fig, ax = plt.subplots(figsize=(12, 6))
        # 横向条形图，按增速降序
        bars = ax.barh(top10["赛道类型"][::-1], top10["规模增速"][::-1]*100, color="#1f77b4")
        ax.set_title("2026年上半年ETF赛道规模增速TOP10", fontsize=14)
        ax.set_xlabel("规模增速(%)", fontsize=12)
        # 标注数值
        for bar in bars:
            w = bar.get_width()
            ax.text(w, bar.get_y()+bar.get_height()/2, f"{w:.1f}%", ha="left" if w>=0 else "right", va="center", fontsize=11)
        plt.tight_layout()
        save_path = self.save_dir / "赛道增速TOP10.png"
        plt.savefig(save_path, dpi=300, bbox_inches="tight")
        if self.run_context:
            chart_path = self.run_context.chart_dir / "赛道增速TOP10.png"
            fig.savefig(chart_path, dpi=300, bbox_inches="tight")
            self.run_context.record_artifact("chart_track_top10", chart_path)
        print(f"✅ 赛道增速TOP10图已保存至：{save_path}")
        return fig

    # 管理人TOP20规模增速图
    def plot_manager_top20(self, manager_df: pd.DataFrame):
        top20 = manager_df.head(20)
        fig, ax = plt.subplots(figsize=(14, 7))
        bars = ax.barh(top20["管理人"][::-1], top20["规模增速"][::-1]*100, color="#ff7f0e")
        ax.set_title("2026年上半年管理人权益ETF规模增速TOP20", fontsize=14)
        ax.set_xlabel("规模增速(%)", fontsize=12)
        # 标注数值
        for bar in bars:
            w = bar.get_width()
            ax.text(w, bar.get_y()+bar.get_height()/2, f"{w:.1f}%", ha="left" if w>=0 else "right", va="center", fontsize=10)
        plt.tight_layout()
        save_path = self.save_dir / "管理人增速TOP20.png"
        plt.savefig(save_path, dpi=300, bbox_inches="tight")
        if self.run_context:
            chart_path = self.run_context.chart_dir / "管理人增速TOP20.png"
            fig.savefig(chart_path, dpi=300, bbox_inches="tight")
            self.run_context.record_artifact("chart_manager_top20", chart_path)
        print(f" 管理人增速TOP20图已保存至：{save_path}")
        return fig
