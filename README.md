# ETF Graph Assistant

一个用于 ETF 底表数据计算、可视化、AI 分析和 AI 审核的 Python 项目。

项目设计原则是：确定性数据计算由 `pandas` 完成，AI 只负责观察、总结和发现；每次运行都会保留输入、聚合表、图表、Prompt、模型请求/响应和运行清单，方便复核和审计。

## 功能概览

- 将 ETF 底表 Excel 转为 CSV。
- 基于底表计算三类聚合表：
  - 区域维度：A股 / 港股 / 其他跨境
  - 赛道维度：按赛道聚合，并提取每个赛道增量 TOP3 产品
  - 管理人维度：按基金公司聚合，并提取每个管理人增量 TOP3 产品
- 生成图表：
  - 区域 ETF 增量对比
  - 赛道增速 TOP10
  - 管理人增速 TOP20
- 调用大模型生成 ETF 分析报告。
- 调用审核模型校验报告中的数据、逻辑和遗漏项。
- 为每次运行生成独立审计目录 `runs/{run_id}/`。

## 项目结构

```text
.
├── data/
│   ├── etf底表.xlsx
│   └── etf底表.csv
├── output/
│   └── 图表输出
├── result/
│   ├── ETF聚合汇总表.xlsx
│   ├── AI数据分析报告第一版测试.md
│   └── AI审核报告.md
├── runs/
│   └── 每次运行的完整审计留痕
├── scripts/
│   ├── config.py          # 统一配置
│   ├── data_calc.py       # pandas 确定性计算
│   ├── visual_plot.py     # 图表生成
│   ├── llm_client.py      # 大模型请求封装
│   ├── ai_analyst.py      # AI 分析报告生成
│   ├── review_ai.py       # AI 审核
│   ├── run_context.py     # 运行留痕
│   ├── main.py            # 命令行主入口
│   └── qwen.py            # 简单模型连通性测试
├── skills.md              # 分析模型使用的 Skill
├── skill_check.md         # 审核模型使用的 Skill
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
3. 执行 pandas 聚合计算
4. 导出 `result/ETF聚合汇总表.xlsx`
5. 生成图表到 `output/`
6. 如已配置 API Key，生成 AI 分析报告
7. 调用审核模型审核报告
8. 将本次运行留痕保存到 `runs/{run_id}/`

如果没有配置 API Key，程序仍会完成 Excel 转换、聚合计算和图表生成，然后跳过 AI 阶段。

## Web 页面运行

```bash
streamlit run web.py
```

页面支持：

- 上传新的 Excel 底表
- 手动执行 Excel 转 CSV
- 手动执行聚合计算
- 生成并展示图表
- 输入 API Key 后生成 AI 分析报告并执行审核
- 查看历史运行中的报告、聚合表和审核结果
- 下载聚合汇总表

Web 使用建议：

1. 在左侧上传底表，或直接使用默认 `data/etf底表.xlsx`。
2. 点击 `转换底表`。
3. 点击 `计算聚合表`。
4. 在 `聚合表` 和 `图表` 页查看结果。
5. 如需 AI 报告，确认 `.env` 中已配置 API Key，然后点击 `生成 AI 报告并审核`。
6. 在 `历史运行` 页查看每次运行的报告、聚合表、审核结果和文件清单。

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
- 配置信息
- 输入文件 hash
- 输出文件 hash
- 数据校验结果
- 最终审核得分

这使得每次报告都可以追溯到当时的输入数据、计算结果、Prompt 和模型原始返回。

## 数据校验

`scripts/data_calc.py` 会在计算前检查底表字段和公式一致性。

必要字段包括：

- `前6位代码`
- `基金简称`
- `基金公司`
- `25Q4`
- `26Q2`
- `增量26H1`
- `增速26H1%`
- `26H1新发`
- `26H1净值`
- `26H1持营`
- `赛道（结合区域和主题打标）`
- `A股、港股or其他跨境`

当前校验规则：

- `增量26H1 = 26Q2 - 25Q4`
- `增量26H1 = 26H1新发 + 26H1净值 + 26H1持营`

如果校验失败，程序会直接报错，避免后续 AI 基于错误数据生成报告。

## Skill 文件

`skills.md` 定义分析模型的任务、输入格式和输出要求。

`skill_check.md` 定义审核模型的校验规则、扣分规则和固定输出格式。

修改这两个文件会影响 AI 输出行为。建议每次重要修改后更新文件中的 `skill_version` 或 `data_contract_version`。

## 配置修改

主要配置集中在 `scripts/config.py`：

- 输入文件路径
- 输出目录
- Excel sheet 名
- 统计区间
- 目标公司
- 模型名称
- base_url
- 最大重试次数
- 请求超时时间

默认模型配置为阿里云兼容 OpenAI Chat Completions 的接口。

## 扩展新的聚合计算

标准聚合已经抽象为 `AggregationSpec`。如果新计算只是基于底表字段做 `groupby + sum + 衍生指标`，不需要复制一整段计算函数，只需要在 `scripts/data_calc.py` 的 `AGGREGATION_SPECS` 中新增一个规格。

### 新增单字段聚合

例如，新增按 `是否国家队` 聚合：

```python
"national_team": AggregationSpec(
    name="national_team",
    sheet_name="国家队汇总",
    csv_name="national_team_agg.csv",
    group_cols=["是否国家队"],
    rename_map={"是否国家队": "是否国家队"},
)
```

然后在 `scripts/main.py` 中把它加入执行列表：

```python
agg_tables = calc.calc_registered_aggs(["area", "track", "manager", "national_team"])
```

这样会自动：

- 在 Excel 中新增 sheet：`国家队汇总`
- 在运行留痕中新增：`runs/{run_id}/tables/national_team_agg.csv`
- 在 `run_manifest.json` 中记录该表

### 新增带 TOP 产品的聚合

例如，新增按 `所在区域` 聚合，并提取每个区域增量 TOP3 产品：

```python
"location": AggregationSpec(
    name="location",
    sheet_name="所在区域汇总",
    csv_name="location_agg.csv",
    group_cols=["所在区域"],
    rename_map={"所在区域": "所在区域"},
    include_top_products=True,
)
```

默认 TOP 产品按 `增量26H1` 从高到低排序，默认取 TOP3。可以通过参数调整：

```python
include_top_products=True,
top_n=5,
top_sort_col="增量26H1",
```

### 新增多字段联合聚合

例如，新增 `基金公司 + 赛道` 联合聚合：

```python
"manager_track": AggregationSpec(
    name="manager_track",
    sheet_name="管理人赛道汇总",
    csv_name="manager_track_agg.csv",
    group_cols=["基金公司", "赛道（结合区域和主题打标）"],
    rename_map={
        "基金公司": "管理人",
        "赛道（结合区域和主题打标）": "赛道类型",
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

## 原版本备份

本次重构前的版本已保留在：

```text
_backup_before_refactor_20260708/
```

如果新版本运行不符合预期，可以从该目录恢复旧文件。

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

当前默认 sheet 名为：

```text
260630股票etf底表
```

如果底表 sheet 名变化，请修改 `scripts/config.py` 中的 `sheet_name`。
