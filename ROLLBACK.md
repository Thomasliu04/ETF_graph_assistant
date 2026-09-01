# 回退与分支说明

以 **GitHub 仓库**为准：`git@github.com:Thomasliu04/ETF_graph_assistant.git`。

本地曾使用的完整目录副本（`ETF_graph_assistant_baseline_*`、`ETF_graph_assistant_github`、`_backup_before_refactor_*`）已清理；不要再依赖这些路径。

---

## 日常开发

```bash
cd /path/to/ETF_graph_assistant
git checkout main          # 或你们约定的开发分支
git pull
```

提交前确认未带入密钥：

```bash
git status
# 不应出现 .env
```

---

## 场景 A：丢掉未提交的本地修改

```bash
git status
git restore .
# 慎用：删除未跟踪文件（.env / data / runs 被 ignore，默认不会删）
# git clean -fd
```

---

## 场景 B：代码回退到某次已知提交

```bash
git fetch origin
git log --oneline -20
git checkout <commit_sha>   # 临时查看
# 或在新分支上重置（需团队同意）：
# git checkout -b fix/rollback
# git reset --hard <commit_sha>
```

若曾打过标签 `baseline-before-extensibility`，仍可用于对照更早基线：

```bash
git show baseline-before-extensibility --stat
```

---

## 场景 C：只想重新拿到干净仓库

```bash
cd ..
git clone git@github.com:Thomasliu04/ETF_graph_assistant.git
cd ETF_graph_assistant
cp .env.example .env   # 自行填入 Key；不要从别处抄含密钥的旧目录除非你确信安全
pip install -r requirements.txt
```

底表请自行放入 `data/etf底表.xlsx`（或 Web 上传）。
