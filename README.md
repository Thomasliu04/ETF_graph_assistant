# ETF Graph Assistant

用 **pandas 做确定性计算**、用 **LLM 写分析报告并交叉审核** 的 ETF 底表分析工具。

同事接手时：

1. 勾选 [`docs/同事上手清单.md`](docs/同事上手清单.md)  
2. 按本文「5 分钟上手」跑通  
3. 扩展聚合表读 [`docs/如何新增一张聚合表.md`](docs/如何新增一张聚合表.md)

---

## 5 分钟上手

```bash
# 1) 进入项目
cd /path/to/ETF_graph_assistant

# 2) 虚拟环境 + 依赖
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3) 配置密钥（不要把真实 Key 写进代码或提交 Git）
cp .env.example .env
# 编辑 .env，至少填写：
#   ETF_AI_API_KEY=你的Key
#   ETF_AI_API_TYPE=aliyun          # 或 deepseek / zhipu / moonshot 等，见 scripts/providers.py
#   ETF_AI_MODEL_NAME=qwen3.7-plus

# 4) 准备底表：放到 data/etf底表.xlsx（或 Web 里上传）
#    默认 Sheet 名见 scripts/contracts/meta.py → sheet_name

# 5) 启动网页（推荐）
streamlit run web.py
```

网页左侧点 **一键分析** → 下载 Excel → 在「AI 报告」查看生成/审核结果。

没有 API Key 时仍会完成转换、聚合和 Excel 导出，只是跳过 AI。

命令行完整跑一遍：

```bash
python scripts/main.py
```

快速自检：

```bash
# Key 是否读到（不打印内容）
python - <<'PY'
from scripts.config import AppConfig
c = AppConfig()
print("api_key_loaded", bool(c.api_key), "type", c.api_type, "model", c.model_name)
PY

# 聚合登记表 / 内置表是否正常
python -m scripts.tests.test_agg_parity
```

---

## 这个系统在做什么

| 步骤 | 谁做 | 产出 |
|------|------|------|
| 底表校验、聚合、增速/TOP 产品 | pandas（确定性） | `result/ETF聚合汇总表.xlsx` |
| 写研报式分析 | 分析 LLM | `result/AI数据分析报告…md` |
| 打分 + 错误清单 + 重写指令 | 审核 LLM | `result/AI审核报告.md` |
| 低分时按章节改写再复审 | 流水线 loop | 保留最高分版本 |

设计原则：**数字以表为准，AI 只总结与挑错**；每次运行写入 `runs/{run_id}/` 便于复核。

当前 AI 流程不是「盲着重生成」，而是：

```text
全文生成 → 结构化审核
  → 分数达标则结束
  → 否则按失败章节局部改写（或一次全文反馈改写）→ 增量复审
  → 达标 / 增益不足 / 达到改写轮数上限则停，保留最佳版本
```

---

## 功能概览

- Excel ↔ CSV 转换；契约校验字段与平衡公式  
- 默认聚合：区域 / 赛道 / 管理人 / 国家队 + 目标公司切片（默认银华）  
- **主交付物**：多 sheet「ETF聚合汇总表.xlsx」（含目录页）  
- Web 一键分析：分阶段进度条；报告阅读默认隐藏「来源：…」，出处集中展示  
- 标准聚合可用 **`configs/聚合登记表.xlsx`** 加行扩展（无需改 Python）  
- 多厂商 OpenAI 兼容接口预设（`scripts/providers.py`）  
- 图表仅为可选预览，默认不生成  

---

## 项目结构（接手时看这些）

```text
.
├── web.py                 # Streamlit 入口（日常推荐）
├── skills.md              # 分析模型写作规范
├── skill_check.md         # 审核打分与 JSON 输出规范
├── configs/
│   └── 聚合登记表.xlsx     # 非开发扩展标准聚合（勿乱改内置四行）
├── docs/
│   └── 如何新增一张聚合表.md
├── scripts/
│   ├── main.py            # CLI 入口
│   ├── pipeline.py        # 一键流水线 + AI 改写 loop
│   ├── config.py          # 环境变量 / 路径
│   ├── providers.py       # 厂商 base_url 预设
│   ├── data_calc.py       # pandas 计算与 Excel 导出
│   ├── contracts/         # 数据契约（口径单一事实来源）
│   │   ├── meta.py
│   │   ├── base_table.py
│   │   ├── aggregations.py
│   │   └── table_plugins.py   # 读取聚合登记表
│   ├── calculations/      # 复杂切片（如目标公司）
│   ├── ai_analyst.py / review_ai.py
│   ├── report_sections.py / report_display.py
│   └── tests/test_agg_parity.py
├── data/                  # 底表（本地，通常不入库）
├── result/                # 最近一次导出（本地）
├── runs/                  # 每次运行审计目录（本地）
├── requirements.txt
└── .env.example
```

---

## 安装与配置

### 依赖

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### `.env`

```bash
cp .env.example .env
```

常用项：

| 变量 | 含义 | 默认/示例 |
|------|------|-----------|
| `ETF_AI_API_KEY` | 密钥 | 必填才跑 AI |
| `ETF_AI_API_TYPE` | 厂商预设 key | `aliyun` |
| `ETF_AI_MODEL_NAME` | 模型名 | `qwen3.7-plus` |
| `ETF_AI_BASE_URL` | 覆盖预设 base（一般留空） | 空则用 `providers.py` |
| `ETF_AI_PASS_SCORE` | 审核达标分 | `80` |
| `ETF_AI_MAX_REVISE_ROUNDS` | 局部改写最多轮数 | `2` |
| `ETF_AI_MIN_SCORE_GAIN` | 分数增益不足则停 | `5` |
| `ETF_AI_REQUEST_TIMEOUT` | 单次请求超时秒 | `300` |

也支持 `DASHSCOPE_API_KEY` / `OPENAI_API_KEY` 作为 Key 的备选名。

换厂商时改 `ETF_AI_API_TYPE` + `ETF_AI_MODEL_NAME` + Key 即可；示例见 `.env.example`。支持的 type 列表：

`aliyun` · `dashscope` · `deepseek` · `zhipu` · `moonshot` · `siliconflow` · `volcengine` · `openai` · `custom`

---

## 日常怎么用

### Web（推荐）

```bash
streamlit run web.py
```

1. 上传底表或使用 `data/etf底表.xlsx`  
2. 确认侧边栏 API Key / 模型  
3. **一键分析**（进度：转换 → 聚合 → AI 子步骤 3.1～3.4）  
4. 下载 Excel；在「AI 报告」阅读（默认隐藏出处，可开关显示）  
5. 「概览 → 已加载聚合」确认登记表是否生效  
6. 「历史运行」回溯某次 `run_id`  

### CLI

```bash
python scripts/main.py
```

流程：读底表 → 转 CSV → 校验 → 聚合（含目标公司）→ 导出 Excel →（有 Key 则）AI 生成与审核 → 写入 `runs/{run_id}/`。

---

## 主交付物与审计

**Excel**：`result/ETF聚合汇总表.xlsx`（同时有一份在 `runs/{run_id}/`）

- 首表「目录」  
- 全市场聚合 + 目标公司切片  

**审计目录** `runs/{run_id}/`：

```text
input/  tables/  prompts/  ai/  run_manifest.json
```

`run_manifest.json` 含契约版本、配置、`ai_loop_log`、最终得分等。

---

## 数据契约（改口径先改这里）

`scripts/contracts/` 是字段、区间、校验与聚合 schema 的单一事实来源。当前 `data_contract_version` 见 `meta.py`。

| 文件 | 改什么 |
|------|--------|
| `meta.py` | 报告期、sheet 名、目标公司别名、版本号 |
| `base_table.py` | 底表列名、别名、必要列、平衡公式 |
| `aggregations.py` | 内置 AggregationSpec 回退源、导出元数据 |
| `table_plugins.py` | Excel 登记表加载逻辑 |

换报告期 / 列名时：改契约 → 同步 `skills.md` / `skill_check.md` 的 `data_contract_version` → 必要时 bump `META.version`。

目标公司默认「银华基金」，别名匹配「银华基金管理股份有限公司」。换公司改 `meta.py` 的 `target_company` / `target_company_aliases`。

---

## 扩展聚合表

- **标准 groupby**：编辑 `configs/聚合登记表.xlsx`（见 [`docs/如何新增一张聚合表.md`](docs/如何新增一张聚合表.md)）  
- **复杂切片**（筛选公司、多表拼接）：开发在 `scripts/calculations/` 写模块  
- 登记表坏了会**自动回退**代码内置四表（area/track/manager/national_team），一键分析仍可跑  

---

## AI Skill

- `skills.md`：分析写作、章节锚点、百分比写法、来源标注  
- `skill_check.md`：扣分规则、文末 JSON（score / errors / failed_sections）  

改这两个文件会直接影响报告与审核行为。

---

## 常见问题

**1. 没有 `pandas` / `streamlit`**  
`pip install -r requirements.txt`，并确认激活了 `.venv`。

**2. 没有 AI 报告**  
检查 `.env` 是否有 Key；侧边栏也可临时粘贴。无 Key 时仍导出 Excel。

**3. 鉴权失败 / 超时**  
核对 `ETF_AI_API_TYPE`、`ETF_AI_MODEL_NAME`、Key 与厂商是否匹配；可调大 `ETF_AI_REQUEST_TIMEOUT`。`ETF_AI_BASE_URL` 不要带 `/chat/completions`。

**4. Sheet 找不到**  
默认 sheet 在 `scripts/contracts/meta.py` 的 `sheet_name`。底表 sheet 名变了就改契约。

**5. 缺字段或平衡校验失败**  
对照 `base_table.py` 的 `REQUIRED_COLUMNS` / `BALANCE_RULES`；别名变化加到 `COLUMN_ALIASES`。

**6. Web 看起来像旧版**  
确认当前目录是本仓库（不是别的副本），强刷浏览器；新版概览有「已加载聚合」，AI 报告有「显示行内出处」开关。

**7. 一键分析很慢**  
耗时主要在阶段 3（LLM）。进度条会显示 3.1 生成 / 3.2 审核 / 3.3 改写 / 3.4 复审。

---

## Git 与分支

- 远程：`git@github.com:Thomasliu04/ETF_graph_assistant.git`  
- 当前主线代码在 `main`（与功能分支 `refactor/extensibility` 已对齐过）  
- 不要提交 `.env`、`data/`、`runs/`、`result/`（已在 `.gitignore`）  

本地改乱且未推送时：

```bash
git status
git restore .
# 慎用：删除未跟踪文件
# git clean -fd
```

更细的历史回退说明见 [`ROLLBACK.md`](ROLLBACK.md)（部分旧本地备份目录已删除，以 GitHub 为准）。
