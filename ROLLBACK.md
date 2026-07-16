# 回退指南

本文说明在扩展性改造过程中，如何安全回到当前可用基线。

相关保护措施已在 `2026-07-16` 就绪：

| 保护层 | 位置 | 作用 |
|--------|------|------|
| Git 基线标签 | `baseline-before-extensibility` | 回退代码到改造前 |
| 基线分支 | `main` | 保持干净、可随时切换回来 |
| 开发分支 | `refactor/extensibility` | 所有新改动只在此分支进行 |
| 完整目录副本 | `../ETF_graph_assistant_baseline_20260716/` | 含 `.env`、底表、结果、历史 runs |
| 旧重构备份 | `_backup_before_refactor_20260708/` | 更早一版代码快照（仅供对照） |

---

## 开始改动前请确认

当前应处于开发分支：

```bash
cd /Users/thomasliu/PycharmProjects/ETF_graph_assistant
git status
# 期望：On branch refactor/extensibility
```

若不在该分支：

```bash
git checkout refactor/extensibility
```

---

## 场景 A：只想丢掉未提交的本地修改

工作区改乱了，但还没有 `git commit`：

```bash
cd /Users/thomasliu/PycharmProjects/ETF_graph_assistant
git status
git restore .
git clean -fd
```

说明：

- `git restore .`：撤销已跟踪文件的修改
- `git clean -fd`：删除未跟踪的新文件/目录

注意：`git clean -fd` 不可恢复，执行前先看 `git status`。  
被 `.gitignore` 忽略的内容（如 `.env`、`data/`、`runs/`）默认不会被 `git clean` 删掉。

---

## 场景 B：开发分支已提交，但想退回基线代码

### 方式 1：切回 `main`（推荐，不破坏开发分支历史）

```bash
cd /Users/thomasliu/PycharmProjects/ETF_graph_assistant
git checkout main
```

此时代码回到基线。需要继续改造时：

```bash
git checkout refactor/extensibility
```

### 方式 2：用标签硬重置当前分支

仅在确定要丢弃当前分支上的提交时使用：

```bash
cd /Users/thomasliu/PycharmProjects/ETF_graph_assistant
git checkout refactor/extensibility
git reset --hard baseline-before-extensibility
```

这会让 `refactor/extensibility` 与基线标签完全一致，该分支上已有提交会从当前分支尖端消失（本地仍可能通过 `git reflog` 找回一段时间）。

### 方式 3：只查看基线，不切换分支

```bash
git show baseline-before-extensibility:README.md
git checkout baseline-before-extensibility -- scripts/data_calc.py
```

第二条会把基线里的某个文件检出到当前工作区，适合「只还原一个文件」。

---

## 场景 C：代码回退了，但本地数据/结果也不对

Git **不会**跟踪这些内容（见 `.gitignore`）：

- `.env`
- `data/`
- `output/`
- `result/`
- `runs/`

若它们也被改坏或删除，从完整目录副本恢复：

```bash
# 先停掉正在运行的 streamlit / python
cd /Users/thomasliu/PycharmProjects

# 按需恢复，不要无脑整目录覆盖正在改的代码
# 示例：只恢复数据与结果
cp -a ETF_graph_assistant_baseline_20260716/data/. ETF_graph_assistant/data/
cp -a ETF_graph_assistant_baseline_20260716/result/. ETF_graph_assistant/result/
cp -a ETF_graph_assistant_baseline_20260716/output/. ETF_graph_assistant/output/
cp -a ETF_graph_assistant_baseline_20260716/runs/. ETF_graph_assistant/runs/
cp ETF_graph_assistant_baseline_20260716/.env ETF_graph_assistant/.env
```

若希望连代码一起恢复成「改造前可运行整包」，可直接使用副本目录运行，不必覆盖当前仓库：

```bash
cd /Users/thomasliu/PycharmProjects/ETF_graph_assistant_baseline_20260716
python scripts/main.py
# 或
streamlit run web.py
```

---

## 场景 D：整项目都不可信，想换回干净环境

最稳妥的两步：

1. 保留当前目录改名为失败实验（可选）
2. 从副本重新开工，或从 Git 基线重建

```bash
cd /Users/thomasliu/PycharmProjects

# 可选：留存失败现场
mv ETF_graph_assistant ETF_graph_assistant_failed_$(date +%Y%m%d_%H%M%S)

# 从完整副本恢复一个可运行项目
cp -a ETF_graph_assistant_baseline_20260716 ETF_graph_assistant

# 若还需要 Git 历史与标签，可再从原失败目录把 .git 拷回，
# 或重新 clone/保留原仓库后执行：
# git reset --hard baseline-before-extensibility
```

更常见、更轻量的做法仍是：

```bash
cd /Users/thomasliu/PycharmProjects/ETF_graph_assistant
git checkout main
# 再按场景 C 恢复 data / result / .env
```

---

## 场景 E：只要对照旧实现，不整库回退

更早的重构前备份仍在：

```text
_backup_before_refactor_20260708/
```

可用于对比某个旧文件实现，不建议直接覆盖整个新项目。

---

## 快速决策表

| 情况 | 做什么 |
|------|--------|
| 改了几行，还没 commit | 场景 A：`git restore` / `git clean` |
| 分支上改坏了，想继续用干净代码 | 场景 B 方式 1：`git checkout main` |
| 开发分支要作废重来 | 场景 B 方式 2：`git reset --hard baseline-before-extensibility` |
| 代码对了，底表/报告丢了 | 场景 C：从 `*_baseline_20260716` 拷数据 |
| 整个目录都乱了 | 场景 D：切回 `main` 或启用完整副本 |
| 只想看旧写法 | 场景 E：看 `_backup_before_refactor_*` |

---

## 验证回退是否成功

回退后建议做一次最小检查：

```bash
cd /Users/thomasliu/PycharmProjects/ETF_graph_assistant
git status
git describe --tags --always
# 期望看到 baseline-before-extensibility，或与之等价的提交

python - <<'PY'
from scripts.config import AppConfig
c = AppConfig()
print("api_key_loaded", bool(c.api_key))
print("xlsx_exists", c.xlsx_path.exists())
print("csv_exists", c.csv_path.exists())
PY
```

若依赖已安装，可再跑：

```bash
python scripts/main.py
```

无 API Key 时也应能完成：Excel/CSV、聚合、图表；AI 阶段会跳过。

---

## 注意

1. 日常只在 `refactor/extensibility` 上开发，不要直接在 `main` 上大改。
2. 不要删除：
   - 标签 `baseline-before-extensibility`
   - 目录 `ETF_graph_assistant_baseline_20260716`
   - `_backup_before_refactor_20260708/`（除非确认不再需要）
3. `.env` 含密钥，完整副本请只放本机，不要上传到公开仓库。
4. 本项目有自己的 `.git`；请在 `ETF_graph_assistant` 目录内执行上述命令，不要在家目录大仓库里操作。

---

## 相关标识

- 基线提交说明：`Baseline before extensibility refactor.`
- 基线标签：`baseline-before-extensibility`
- 完整副本路径：`/Users/thomasliu/PycharmProjects/ETF_graph_assistant_baseline_20260716`
