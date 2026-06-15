# 远端 Linux 执行流程

这份文档给能力较弱的 OpenCode 主 AI 使用。场景是：Windows 本地有代码仓和测试修改，但 Windows 不能编译，需要通过 SFTP 同步到 Linux 执行机上构建、跑 DT 或覆盖率。

## 前提

- 目标仓库在 Windows 本地。
- 远端连接和凭据已经由 `Create_tool` 里的 `ai_ssh_mcp` 配好。
- 本工具只复用 `ai_ssh_mcp`，不保存 SSH 密码、私钥或设备凭据。
- 第一版同步当前 Windows 工作区，不使用远端 git checkout。

## 配置检查

目标仓库 `.ut-cover.yaml` 至少需要：

```yaml
execution_mode: 'remote'
remote_backend: 'ai_ssh_mcp'
remote_workspace_root: '/tmp/ut-cover'
remote_build_command: '<远端构建命令>'
remote_dt_command: '<远端 DT 或覆盖率命令>'
remote_artifacts:
  - 'coverage.xml'
  - 'build.log'
  - 'dt.log'
sync_include:
  - '**/*'
sync_exclude:
  - '.git/**'
  - '.ut-cover/**'
  - 'build/**'
remote_clean_before_sync: true
```

如果用户不知道远端命令，主 AI 必须先查目标仓库 README、CI、构建脚本，再问用户确认。不要自己编命令。

## 步骤 1：远端配置体检

```powershell
ut-cover remote-doctor --repo <repo>
```

预期：

- `ok: true`
- `execution_mode` 是 `remote`
- `remote_backend` 是 `ai_ssh_mcp`
- `ai_ssh_mcp` 可导入
- 至少配置了 `remote_build_command` 或 `remote_dt_command`

失败处理：

- `execution_mode` 不是 `remote`：修改配置或使用本地模式。
- `ai_ssh_mcp` 不可用：停止，让用户先安装或配置现有 SSH MCP。
- 远端命令为空：停止，询问用户项目远端构建/DT 命令。

## 步骤 2：同步 Windows 当前工作区

```powershell
ut-cover remote-sync --repo <repo>
```

预期输出：

```text
.ut-cover\remote-sync.json
```

重点字段：

- `remote_workspace`
- `uploaded_count`
- `uploaded_files`
- `next_action`

失败处理：

- 路径不安全：停止，不要改成 `/tmp`、`/home` 这类大目录。
- 上传失败：停止，让用户检查 SSH/SFTP 权限。

## 步骤 3：远端执行构建和 DT

```powershell
ut-cover remote-run --repo <repo>
```

预期输出：

```text
.ut-cover\remote-run.json
```

重点字段：

- `build_result`
- `dt_result`
- `ok`
- `next_action`

失败处理：

如果 `ok: false`，不要猜原因，进入步骤 5。

## 步骤 4：拉回远端产物

```powershell
ut-cover remote-fetch --repo <repo>
```

预期输出：

```text
.ut-cover\remote-fetch.json
.ut-cover\remote\coverage.xml
.ut-cover\remote\build.log
.ut-cover\remote\dt.log
```

失败处理：

- 如果 coverage 拉不回来，但日志拉回来了，继续诊断。
- 如果所有产物都拉不回来，停止，让用户检查远端产物路径和权限。

## 步骤 5：失败诊断

```powershell
ut-cover remote-diagnose --repo <repo>
```

诊断分类：

- `environment_or_path`：远端缺依赖、命令不存在、路径错误、权限错误。
- `source_compile_error`：业务源码编译失败。
- `test_code_compile_error`：测试代码导致编译失败。
- `dt_failure`：DT 命令运行失败。
- `unknown`：无法安全分类。

按 `next_action` 执行：

- `fix_test_code`：可以继续改测试文件。
- `ask_user_environment`：停止，让用户修远端环境。
- `continue`：继续下一步。
- `stop`：停止并说明原因。

## 一步式远端覆盖率

配置为远端模式后，可以直接执行：

```powershell
ut-cover run-coverage --repo <repo>
```

它会自动执行：

```text
remote-sync -> remote-run -> remote-fetch -> parse coverage -> coverage gate
```

输出：

```text
.ut-cover\coverage.json
.ut-cover\remote-sync.json
.ut-cover\remote-run.json
.ut-cover\remote-fetch.json
.ut-cover\remote-diagnosis.json   # 仅失败时生成
```

主 AI 必须读取 `.ut-cover\coverage.json` 中的：

- `test_result`
- `remote_run`
- `remote_fetch`
- `coverage`
- `coverage_gate`

如果 `coverage_gate.status` 是 `failed`，继续补 UT；如果是 `unknown` 且 `next_action` 是 `stop`，停止并说明覆盖率无法判断。

## 禁止事项

- 不要把远端工作区配置成 `/tmp`、`/home`、`/root`、`/usr`、`/opt`。
- 不要在远端直接 `git checkout` 覆盖用户本地未提交测试修改。
- 不要把 SSH 密码、私钥或设备凭据写进 `.ut-cover.yaml`。
- 不要把 DT/integration/e2e 测试当作 UT 风格来源。
- 远端失败时不要猜，必须先运行诊断。
