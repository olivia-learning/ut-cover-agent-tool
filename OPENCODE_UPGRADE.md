# OpenCode 主 AI 升级指南

这份文档给弱主 AI 使用，处理“新电脑已经有旧版 SSH 服务、旧版 UT 工具，又拿到了新版 ZIP”的场景。

## 固定流程

1. 不要直接覆盖旧目录。
2. 找到新版 ZIP 所在目录，确认是否存在：

```text
ut-cover-agent-tool.zip
ai-ssh-mcp-tool.zip
```

3. 运行升级状态检查：

```powershell
ut-cover upgrade-status --install-dir <旧UT工具目录> --zip-dir <ZIP目录>
```

4. 如果旧版没有 `upgrade-status` 命令，解压新 ZIP 到临时目录，并运行：

```powershell
python <临时目录>\ut-cover-agent-tool\scripts\upgrade_from_zip.py `
  --install-dir <旧UT工具目录> `
  --ut-zip <ZIP目录>\ut-cover-agent-tool.zip
```

5. 如果有 `upgrade` 命令，运行：

```powershell
ut-cover upgrade `
  --install-dir <旧UT工具目录> `
  --ut-zip <ZIP目录>\ut-cover-agent-tool.zip
```

6. 如果状态提示 SSH MCP 不兼容：

交互模式下，先告诉用户需要升级 SSH MCP，再带确认参数运行：

```powershell
ut-cover upgrade `
  --install-dir <旧UT工具目录> `
  --ut-zip <ZIP目录>\ut-cover-agent-tool.zip `
  --ssh-zip <ZIP目录>\ai-ssh-mcp-tool.zip `
  --upgrade-ssh
```

无人值守模式下，如果同目录有 `ai-ssh-mcp-tool.zip`，可以自动升级；如果没有，写入升级报告，不要询问用户。

7. 升级后验证：

```powershell
ut-cover --version
ut-cover upgrade-status --install-dir <旧UT工具目录> --zip-dir <ZIP目录>
```

目标仓库是远端模式时，再运行：

```powershell
ut-cover remote-doctor --repo <目标仓库>
```

## 禁止事项

- 不要删除 `.venv`。
- 不要删除目标仓库 `.ut-cover.yaml`。
- 不要导出、复制、打印 SSH 密码、私钥或 token。
- 不要把 SSH MCP 工具源码混进 UT ZIP。
- 不要在没有备份的情况下覆盖旧工具目录。

## 输出给用户

升级完成后，说明：

- 升级前版本
- 升级后版本
- 是否升级 SSH MCP
- 备份目录
- 验证命令是否通过
- 如果失败，给出 `.ut-cover-upgrade/upgrade-report.md` 路径
