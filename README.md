# ETF Graph Assistant

一个用于 ETF 底表数据计算、可视化、AI 分析和 AI 审核的 Python 项目。

项目设计原则是：确定性数据计算由 `pandas` 完成，AI 只负责观察、总结和发现；字段口径集中在数据契约层；每次运行都会保留输入、聚合表、图表、Prompt、模型请求/响应和运行清单，方便复核和审计。

## 功能概览

- 将 ETF 底表 Excel 转为 CSV。
- 基于数据契约校验底表字段与平衡公式。
- 基于底表计算聚合表（当前默认）：
  - 区域维度：A股 / 港股 / 其他跨境
  - 赛道维度：按赛道聚合，并提取每个赛道增量 TOP3 产品
  - 管理人维度：按基金公司聚合，并提取每个管理人增量 TOP3 产品
  - 国家队维度：按是否国家队持仓聚合
  - 目标公司切片：总览、分区域、分赛道、增量/缩水产品梯队（默认银华，含全称别名匹配）
- **主交付物：多 sheet Excel 聚合汇总表**（含目录页；可用 Excel 自行制图）。
- Web「一键分析」：上传底表后自动完成转换、聚合、Excel 导出、AI 报告与审核。
- 调用大模型生成 ETF 分析报告（输入含目标公司切片，减少编造）。
- 调用审核模型校验报告；低分自动重试重写。
- 图表仅为可选预览，默认不生成。
- 为每次运行生成独立审计目录 `runs/{run_id}/`。

## 项目结构

```text
.
├── data/
│   ├── etf底表.xlsx
│   └── etf底表.csv
├── output/
│   └── 可选图表预览（默认不生成）
├── result/
│   ├── ETF聚合汇总表.xlsx   # 主交付物
│   ├── AI数据分析报告第一版测试.md
│   └── AI审核报告.md
├── runs/
│   └── 每次运行的完整审计留痕（含同名 Excel）
├── scripts/
│   ├── contracts/         # 数据契约（字段、校验、聚合 schema）
│   │   ├── meta.py        # 版本、区间、sheet、目标公司
│   │   ├── base_table.py  # 底表列名、别名、平衡规则
│   │   └── aggregations.py# AggregationSpec 与输出列
│   ├── calculations/      # 非标准聚合（目标公司切片等）
│   ├── pipeline.py        # CLI/Web 共用一键流水线
│   ├── config.py          # 路径与模型配置（口径默认值来自契约）
│   ├── data_calc.py       # pandas 确定性计算与 Excel 导出
│   ├── visual_plot.py     # 可选图表预览
│   ├── llm_client.py      # 大模型请求封装
│   ├── ai_analyst.py      # AI 分析报告生成
│   ├── review_ai.py       # AI 审核
│   ├── run_context.py     # 运行留痕
│   ├── main.py            # 命令行主入口
│   └── qwen.py            # 简单模型连通性测试
├── skills.md              # 分析模型使用的 Skill
├── skill_check.md         # 审核模型使用的 Skill
├── ROLLBACK.md            # 改造过程中的回退指南
├── web.py                 # Streamlit 页面
├── requirements.txt
└── .env.example
```

## 安装依赖

建议先创建虚拟环境：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

如果你使用 PyCharm，也可以在项目解释器中安装 `requirements.txt`。

## 配置 API Key

项目不会在代码里保存真实 API Key。推荐使用本地 `.env` 文件保存密钥，`.env.example` 只保留模板。

### 推荐方式：使用 `.env`

复制模板文件：

```bash
cp .env.example .env
```

然后编辑 `.env`，写入真实 API Key：

```text
ETF_AI_API_KEY=你的真实APIKey
ETF_AI_API_TYPE=aliyun
ETF_AI_MODEL_NAME=qwen3.7-plus
ETF_AI_BASE_URL=https://你的兼容OpenAI接口地址/v1
ETF_AI_REQUEST_TIMEOUT=300
ETF_AI_REQUEST_RETRIES=2
```

之后直接运行主程序即可，代码会自动读取项目根目录下的 `.env`：

```bash
python scripts/main.py
```

`.env` 已经被 `.gitignore` 忽略，不应提交到 Git。`.env.example` 可以提交，但只能放占位符：

```text
ETF_AI_API_KEY=replace_with_your_api_key
```

### 可选方式：终端临时设置

如果不想使用 `.env`，也可以在当前终端临时设置：

```bash
export ETF_AI_API_KEY="你的API Key"
python scripts/main.py
```

程序支持以下环境变量名，优先级为：

1. `ETF_AI_API_KEY`
2. `DASHSCOPE_API_KEY`
3. `OPENAI_API_KEY`

注意：不要把真实 key 写入 `.env.example`、README 或代码文件。如果真实 key 曾经上传到 GitHub 或发给别人，建议到模型服务平台后台轮换 key。

如果请求国内模型 endpoint 容易超时，可以在 `.env` 中调大：

```text
ETF_AI_REQUEST_TIMEOUT=600
ETF_AI_REQUEST_RETRIES=3
```

如果你的 API Key 来自不同 workspace 或不同服务商，需要同步修改：

```text
ETF_AI_BASE_URL=你的实际base_url
ETF_AI_MODEL_NAME=你的实际模型名
```

## 命令行运行

完整运行：

```bash
python scripts/main.py
```

运行流程：

1. 读取 `data/etf底表.xlsx`
2. 转换为 `data/etf底表.csv`
3. 按数据契约校验底表
4. 执行 pandas 聚合计算（含目标公司切片）
5. 导出主交付物 `result/ETF聚合汇总表.xlsx`（多 sheet + 目录页）
6. 如已配置 API Key，生成 AI 分析报告并审核
7. 将本次运行留痕保存到 `runs/{run_id}/`（含同名 Excel 与契约摘要）

如果没有配置 API Key，程序仍会完成转换、聚合和 Excel 导出，然后跳过 AI 阶段。图表默认不生成。

## Web 页面运行

```bash
streamlit run web.py
```

页面支持：

- 上传新的 Excel 底表
- **一键分析**（转换 + 聚合 + 导出 Excel + AI）
- 下载多 sheet「ETF聚合汇总表.xlsx」（主交付物）
- 预览各聚合表；可选生成简易图表预览
- 输入 API Key 后生成 AI 分析报告并执行审核
- 查看历史运行中的报告、Excel、审核结果

Web 使用建议（推荐）：

1. 在左侧上传底表，或直接使用默认 `data/etf底表.xlsx`。
2. 确认已配置 API Key（`.env` 或侧边栏输入）。
3. 点击 **一键分析**：自动完成转换 → 校验聚合 → **导出 Excel** → AI 报告 → 审核。
4. 在侧边栏或「导出 Excel」页下载汇总表，再用 Excel 自行制图。
5. 「图表预览」页仅作可选预览，不是主流程。
6. 在 `历史运行` 页可下载该次运行的 Excel / 报告 / 审核结果。

目标公司默认是契约中的 `银华基金`，并通过别名匹配底表中的「银华基金管理股份有限公司」。若要换公司，修改 `scripts/contracts/meta.py` 的 `target_company` / `target_company_aliases`。

## Excel 导出说明

`ETF聚合汇总表.xlsx` 结构：

1. **目录**：列出各工作表名称、说明、行数
2. 区域 / 赛道 / 管理人 / 国家队 等全市场聚合表
3. 目标公司总览、分区域、分赛道、产品明细、增量/缩水梯队

数值默认保留 4 位小数，便于在 Excel 中继续计算或插入图表。文件同时写入：

- `result/ETF聚合汇总表.xlsx`
- `runs/{run_id}/ETF聚合汇总表.xlsx`

## 审计留痕

每次运行会生成一个目录：

```text
runs/{run_id}/
├── input/                 # 本次使用的输入文件副本
├── tables/                # 聚合后的 CSV 表
├── charts/                # 本次运行生成的图表
├── prompts/               # 分析和审核 Prompt
├── ai/                    # AI request / response / report / review
└── run_manifest.json      # 运行清单
```

`run_manifest.json` 会记录：

- 运行 ID
- 创建时间
- git commit
- 配置信息（含 `data_contract_version`）
- `data_contract`：本次使用的完整契约摘要
- 输入文件 hash
- 输出文件 hash
- 数据校验结果
- 最终审核得分

这使得每次报告都可以追溯到当时的输入数据、计算结果、口径版本、Prompt 和模型原始返回。

## 数据契约

`scripts/contracts/` 是字段名、统计区间、行级校验规则和聚合输出 schema 的**单一事实来源**。当前版本：`data_contract_version = 0.3.0`。

| 文件 | 内容 |
|------|------|
| `meta.py` | 契约版本、sheet 名、统计区间、目标公司、校验容差 |
| `base_table.py` | 底表标准列名（`BaseCols`）、别名、必要/数值列、平衡公式 |
| `aggregations.py` | 聚合输出列（`AggCols`）、`AggregationSpec` 注册表、输出 schema 校验 |

`AppConfig` 与 `ETFDataCalculator` 都从契约读取默认口径；计算完成后还会按契约检查聚合表是否缺列。

### 换报告期或改列名时改哪里

1. 改 `scripts/contracts/meta.py`（区间、sheet、目标公司等）。
2. 若底表物理列名变化，改 `scripts/contracts/base_table.py`（`BaseCols` / 别名 / 必要列）。
3. 若聚合维度或输出列变化，改 `scripts/contracts/aggregations.py`。
4. 同步提升 `META.version`，并更新 `skills.md` / `skill_check.md` 中的 `data_contract_version`。

不建议再在 `data_calc.py`、图表标题或 Prompt 里散落硬编码同一套中文列名与日期。

### 快速查看当前契约

```bash
python - <<'PY'
from scripts.contracts import META, contract_manifest
print(META.version, META.period_title, META.target_company)
print(sorted(contract_manifest()["aggregation_specs"]))
PY
```

## 数据校验

`scripts/data_calc.py` 在计算前执行契约中的字段与平衡校验（定义见 `scripts/contracts/base_table.py`）。

必要字段由 `REQUIRED_COLUMNS` 声明，当前包括：

- `前6位代码`、`基金简称`、`基金公司`
- `25Q4`、`26Q2`、`增量26H1`、`增速26H1%`
- `26H1新发`、`26H1净值`、`26H1持营`
- `赛道（结合区域和主题打标）`
- `A股、港股or其他跨境`

当前平衡规则（`BALANCE_RULES`）：

- `增量26H1 = 26Q2 - 25Q4`
- `增量26H1 = 26H1新发 + 26H1净值 + 26H1持营`

默认容差为 `0.02`（亿元）。校验失败会直接报错，避免后续 AI 基于错误数据生成报告。

可选维度列（如 `是否国家队`）不在必要字段中；只有当你执行对应聚合时才会要求底表存在该列。

## Skill 文件

`skills.md` 定义分析模型的任务、输入格式和输出要求。

`skill_check.md` 定义审核模型的校验规则、扣分规则和固定输出格式。

修改这两个文件会影响 AI 输出行为。`data_contract_version` 应与 `scripts/contracts/meta.py` 中的版本保持一致；重要口径变更后请同步升级。

## 配置修改

路径与模型相关配置在 `scripts/config.py`：

- 输入文件路径
- 输出目录
- 模型名称
- base_url
- 最大重试次数
- 请求超时时间

以下默认值来自 `scripts/contracts/meta.py`，也可在构造 `AppConfig(...)` 时覆盖：

- Excel sheet 名
- 统计区间
- 目标公司
- `data_contract_version`

默认模型配置为阿里云兼容 OpenAI Chat Completions 的接口。

## 扩展新的聚合计算

标准聚合已经抽象为 `AggregationSpec`。如果新计算只是基于底表字段做 `groupby + sum + 衍生指标`，只需在 `scripts/contracts/aggregations.py` 的 `AGGREGATION_SPECS` 中新增规格，并尽量使用 `BaseCols` / `AggCols`，避免魔法字符串。

### 新增单字段聚合

例如，按 `是否国家队` 聚合（项目中已注册为 `national_team`，可作模板）：

```python
from scripts.contracts import AggregationSpec, BaseCols, AggCols

"national_team": AggregationSpec(
    name="national_team",
    sheet_name="国家队汇总",
    csv_name="national_team_agg.csv",
    group_cols=[BaseCols.NATIONAL_TEAM],
    rename_map={BaseCols.NATIONAL_TEAM: AggCols.NATIONAL_TEAM},
)
```

然后在 `scripts/main.py` / `web.py` 的执行列表中加入该名字：

```python
agg_tables = calc.calc_registered_aggs(["area", "track", "manager", "national_team"])
```

这样会自动：

- 在 Excel 中新增对应 sheet
- 在运行留痕中新增 `runs/{run_id}/tables/<csv_name>`
- 在 `run_manifest.json` 中记录该表
- 按契约检查输出列是否齐全

### 新增带 TOP 产品的聚合

例如，新增按某分组字段聚合，并提取增量 TOP3 产品：

```python
from scripts.contracts import AggregationSpec, BaseCols

"location": AggregationSpec(
    name="location",
    sheet_name="所在区域汇总",
    csv_name="location_agg.csv",
    group_cols=["所在区域"],  # 若该列已进入契约，改为 BaseCols.XXX
    rename_map={"所在区域": "所在区域"},
    include_top_products=True,
)
```

默认 TOP 产品按底表 `增量26H1`（`BaseCols.DELTA`）从高到低排序，默认取 TOP3：

```python
include_top_products=True,
top_n=5,
top_sort_col=BaseCols.DELTA,
```

### 新增多字段联合聚合

例如，新增 `基金公司 + 赛道` 联合聚合：

```python
from scripts.contracts import AggregationSpec, BaseCols, AggCols

"manager_track": AggregationSpec(
    name="manager_track",
    sheet_name="管理人赛道汇总",
    csv_name="manager_track_agg.csv",
    group_cols=[BaseCols.MANAGER, BaseCols.TRACK],
    rename_map={
        BaseCols.MANAGER: AggCols.MANAGER,
        BaseCols.TRACK: AggCols.TRACK_TYPE,
    },
    include_top_products=True,
)
```

多字段聚合也支持 TOP 产品，程序会按所有分组字段共同筛选对应产品。

### 什么时候不要用 AggregationSpec

如果计算逻辑不是标准 groupby，例如：

- 环比 / 同比趋势
- 分位数排名
- 集中度指标
- 银华 vs 行业均值对标
- 多期时间序列分析

建议新增独立计算模块，而不是硬塞进 `AggregationSpec`。推荐放在：

```text
scripts/calculations/
```

并让该模块输出一个标准 `DataFrame`，再交给导出和 AI 层使用。

### 让 AI 分析新增表

新增聚合表后，如果希望 AI 使用这张表，需要同步修改：

- `skills.md`：说明新表字段、口径和分析任务
- `skill_check.md`：说明新表的审核规则
- `scripts/ai_analyst.py`：把新表拼进分析 Prompt
- `scripts/review_ai.py`：把新表拼进审核 Prompt

如果只是先做数据计算和 Excel 导出，不需要修改 AI 相关文件。

## 回退与备份

扩展性改造期间请优先阅读：

```text
ROLLBACK.md
```

当前保护措施包括：

| 类型 | 位置 | 说明 |
|------|------|------|
| Git 基线标签 | `baseline-before-extensibility` | 回退改造前代码 |
| 开发分支 | `refactor/extensibility` | 新改动应在此分支进行 |
| 完整目录副本 | `../ETF_graph_assistant_baseline_20260716/` | 含 `.env`、底表、结果、runs |
| 旧代码备份 | `_backup_before_refactor_20260708/` | 更早一版实现对照 |

日常开发建议在 `refactor/extensibility` 分支进行；需要干净基线时切回 `main` 或重置到上述标签。详情与命令见 `ROLLBACK.md`。

## 常见问题

### 1. `ModuleNotFoundError: No module named 'pandas'`

说明当前 Python 环境没有安装依赖。执行：

```bash
pip install -r requirements.txt
```

### 2. 没有生成 AI 报告

检查项目根目录是否存在 `.env`，并且内容类似：

```text
ETF_AI_API_KEY=你的真实APIKey
```

也可以用下面命令检查程序是否能读到 key。命令只会输出是否读取成功和 key 长度，不会打印 key 内容：

```bash
python - <<'PY'
from scripts.config import AppConfig
key = AppConfig().api_key
print("api_key_loaded", bool(key))
print("api_key_length", len(key) if key else 0)
PY
```

如果没有设置成功，程序会跳过 AI 阶段。

### 3. 审核模型报鉴权错误

检查 API Key、base_url 和模型名是否匹配你的服务商配置。

### 4. AI 请求超时

如果出现类似：

```text
Read timed out
```

说明程序已经连到了模型 endpoint，但服务没有在限定时间内返回。优先检查：

- 当前网络是否能稳定访问 `.env` 中的 `ETF_AI_BASE_URL`
- API Key 是否属于该 workspace / endpoint
- `ETF_AI_MODEL_NAME` 是否可用
- 是否需要代理或 VPN

可以先在 `.env` 中调大超时和重试：

```text
ETF_AI_REQUEST_TIMEOUT=600
ETF_AI_REQUEST_RETRIES=3
```

如果仍然超时，建议先换一个更小/更快的模型做连通性测试，确认 endpoint 和 key 没问题后再跑完整报告。

### 5. Excel sheet 找不到

当前默认 sheet 名定义在 `scripts/contracts/meta.py`：

```text
260630股票etf底表
```

如果底表 sheet 名变化，请修改契约中的 `sheet_name`，或在构造 `AppConfig` 时覆盖。

### 6. 底表缺字段或平衡校验失败

报错信息会指出缺失列或不满足的平衡公式。请对照：

- `scripts/contracts/base_table.py` 中的 `REQUIRED_COLUMNS` / `BALANCE_RULES`
- 本次运行 `run_manifest.json` 里的 `data_contract` 与 `input_validation`

若只是列名别名变化，优先在契约的 `COLUMN_ALIASES` 中增加映射，而不是改计算逻辑。
