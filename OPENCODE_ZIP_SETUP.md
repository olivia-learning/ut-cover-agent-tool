# OpenCode 主 AI 使用 ZIP 指南

这份文档给 OpenCode 的主 AI 使用。目标是让主 AI 即使能力较弱，也能按固定步骤安装、配置和调用 `ut-cover`，不要自由发挥。

## 角色分工

- 主 AI：安装 ZIP、生成配置、询问覆盖率目标、调用固定命令、根据 `next_action` 决定继续或停止。
- `ut-cover` CLI：做 git 分析、测试邻居扫描、覆盖率解析、远端同步/执行/拉回、报告生成。
- `ut-coverage-writer` 子代理：只根据高置信度 UT 邻居写或修改测试。

## 安装 ZIP

1. 确认工具目录，例如：

```text
C:\Tools\ut-cover-agent-tool
```

2. 解压 ZIP 后确认这些文件存在：

```text
pyproject.toml
README.md
OPENCODE_ZIP_SETUP.md
REMOTE_WORKFLOW.md
examples\.ut-cover.yaml
.opencode\agents\ut-coverage-writer.md
src\ut_cover_agent_tool\
```

3. 安装：

```powershell
py -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -e .
ut-cover --version
```

如果 `ut-cover` 不可用，用：

```powershell
.\.venv\Scripts\python -m ut_cover_agent_tool --version
```

## 配置目标仓库

目标仓库是真正要补 UT 的业务代码仓，不是工具目录。

不要让新手手动复制示例配置。先执行：

```powershell
ut-cover init-config --repo <目标仓库>
```

然后执行：

```powershell
ut-cover doctor --repo <目标仓库>
```

如果项目是 C++，主 AI 必须查看 README、CI、CMakePresets、构建脚本后再调整 `.ut-cover.yaml`。不要盲套默认 CMake 命令。

## 覆盖率目标必须询问用户

如果 `.ut-cover.yaml` 没有覆盖率目标，主 AI 必须问用户：

```text
整体覆盖率目标是多少？如果不知道，我建议 80%。
本次变更文件覆盖率目标是多少？如果不知道，我建议 85%。
覆盖率无法判断时，是只警告还是直接失败？如果不知道，我建议 warn。
```

用户不知道时执行：

```powershell
ut-cover set-coverage-goal --repo <目标仓库> --overall 80 --changed-files 85 --unknown-action warn
```

不要让用户手动改 YAML。

## 本地模式固定流程

```powershell
ut-cover init-config --repo <repo>
ut-cover set-coverage-goal --repo <repo> --overall <n> --changed-files <n> --unknown-action warn
ut-cover doctor --repo <repo>
ut-cover analyze-commits --repo <repo> --commit <ids>
ut-cover inspect-tests --repo <repo>
ut-cover plan-tests --repo <repo>
```

读 `.ut-cover/test-plan.json`：

- 只有高置信度 UT 候选时，才允许调用子代理写测试。
- 每个新增测试只能模仿 1-3 个高置信度 UT 文件。
- 如果状态是 `low_confidence`，必须停止，告诉用户没有安全可模仿的 UT 来源。
- 禁止模仿 DT、integration、e2e、system、device、driver、hardware、scenario、acceptance。

写完测试后：

```powershell
ut-cover run-coverage --repo <repo>
ut-cover review-tests --repo <repo> --touched-test <测试文件>
ut-cover report --analysis <repo>\.ut-cover\analysis.json --coverage <repo>\.ut-cover\coverage.json --touched-test <测试文件>
```

如果 `run-coverage` 或 `review-tests` 失败，必须读取 JSON 里的 `next_action`。不要猜。

## 远端模式固定流程

当 Windows 本地无法编译，而需要同步到 Linux 执行机时：

1. 确认已有 `Create_tool` 的 `ai_ssh_mcp` 可用。
2. 在目标仓库 `.ut-cover.yaml` 设置：

```yaml
execution_mode: 'remote'
remote_backend: 'ai_ssh_mcp'
remote_workspace_root: '/tmp/ut-cover'
remote_build_command: '<项目自己的远端构建命令>'
remote_dt_command: '<项目自己的远端 DT 或覆盖率命令>'
remote_artifacts:
  - 'coverage.xml'
  - 'build.log'
  - 'dt.log'
```

3. 执行：

```powershell
ut-cover remote-doctor --repo <repo>
ut-cover run-coverage --repo <repo>
```

`run-coverage` 会自动同步、远端运行、拉回产物、解析覆盖率。

如果失败：

```powershell
ut-cover remote-diagnose --repo <repo>
```

按 `next_action`：

- `fix_test_code`：只允许修测试。
- `ask_user_environment`：停止，让用户处理远端环境或路径。
- `continue`：继续下一步。
- `stop`：停止并说明原因。

远端详细步骤见 `REMOTE_WORKFLOW.md`。

## 调用子代理

当 `plan-tests` 给出高置信度 UT 候选后，主 AI 可以这样调用：

```text
Use ut-coverage-writer. For repo <repo>, add UT for commits <ids> and calculate coverage.
```

子代理必须遵守 `.opencode/agents/ut-coverage-writer.md`，尤其是：

- 写 UT 前列出模仿来源文件。
- 只模仿高置信度 UT。
- 不模仿 DT/集成测试。
- 新测试必须有明确断言。
- 远端失败先诊断，不猜原因。

## 常见停止条件

遇到以下情况，主 AI 应停止并说明，而不是硬写：

- 找不到 Git。
- 目标仓库不是 git 仓库。
- 没有高置信度 UT 邻居。
- 只有 DT/integration/e2e 候选。
- C++ 构建方式不明确。
- 远端缺依赖、路径错误、权限错误。
- 覆盖率报告无法解析且用户选择 unknown 为 fail。
