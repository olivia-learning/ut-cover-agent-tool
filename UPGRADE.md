# 升级与回退说明

当新电脑上已经有旧版 `ut-cover-agent-tool` 或旧版 `ai_ssh_mcp` 时，不要直接手动覆盖目录。先用升级命令检查，再按报告原地升级。

## ZIP 放置方式

推荐把两个 ZIP 放在同一个目录：

```text
ut-cover-agent-tool.zip
ai-ssh-mcp-tool.zip
```

`ut-cover-agent-tool.zip` 只包含 UT 覆盖率工具。`ai-ssh-mcp-tool.zip` 仍然是独立 SSH MCP 工具包，不内嵌到 UT ZIP 里。

## 查看升级状态

```powershell
ut-cover upgrade-status --install-dir C:\Tools\ut-cover-agent-tool --zip-dir C:\Tools
```

输出会说明：

- 当前 `ut-cover` 版本
- 新 ZIP 版本
- `ai_ssh_mcp` 是否可导入
- SSH MCP 当前版本是否满足最低要求
- 同目录是否存在 `ai-ssh-mcp-tool.zip`
- 下一步 `next_action`

## 原地升级 UT 工具

```powershell
ut-cover upgrade `
  --install-dir C:\Tools\ut-cover-agent-tool `
  --ut-zip C:\Tools\ut-cover-agent-tool.zip
```

升级会：

- 备份旧目录到 `.upgrade-backups/<目录名>-<时间戳>`
- 覆盖工具源码和文档
- 保留 `.venv`
- 重新执行 `pip install -e .`
- 生成 `.ut-cover-upgrade/upgrade-report.json`
- 生成 `.ut-cover-upgrade/upgrade-report.md`

## 升级 SSH MCP

交互模式下，如果 `upgrade-status` 提示 SSH MCP 不兼容，需要显式确认：

```powershell
ut-cover upgrade `
  --install-dir C:\Tools\ut-cover-agent-tool `
  --ut-zip C:\Tools\ut-cover-agent-tool.zip `
  --ssh-zip C:\Tools\ai-ssh-mcp-tool.zip `
  --upgrade-ssh
```

无人值守模式下，如果目标仓库 `.ut-cover.yaml` 中是 `interaction_mode: autonomous`，且同目录存在新版 `ai-ssh-mcp-tool.zip`，工具可以自动升级 SSH MCP。

SSH 凭据继续由系统 keyring 和现有 `ai_ssh_mcp` 管理。升级流程不会导出、打印或复制密码、私钥、token。

## 旧版没有 upgrade 命令

如果旧版 `ut-cover` 没有 `upgrade` 命令：

1. 先把新 ZIP 解压到临时目录。
2. 执行新包里的 bootstrap：

```powershell
python C:\Temp\ut-cover-agent-tool\scripts\upgrade_from_zip.py `
  --install-dir C:\Tools\ut-cover-agent-tool `
  --ut-zip C:\Tools\ut-cover-agent-tool.zip
```

从完成这次升级后，后续版本就优先使用 `ut-cover upgrade`。

## 回退

如果升级失败，可以从 `.upgrade-backups` 中恢复旧工具目录。回退只恢复工具代码和安装状态，不回退用户业务仓，也不回退 SSH keyring 凭据。
