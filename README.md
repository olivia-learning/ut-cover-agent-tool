# UT 覆盖率 Agent 工具

`ut-cover-agent-tool` 是一个独立打包的 AI 辅助 UT/覆盖率工具。它根据用户提供的 git commit id 列表，分析变更文件，寻找本次变更附近可信的 UT 样例，运行测试/覆盖率命令，并生成报告。

第一版的原则是：确定性的事情交给 CLI 做，写测试这种需要判断的事情交给 OpenCode Agent 做。为了照顾能力较弱的主 AI，CLI 会输出结构化结果、`next_action` 和低置信度停止建议，减少 AI 自由发挥。

## 适用场景

- 根据 commit id 列表补单元测试。
- 计算整体覆盖率和本次变更文件覆盖率。
- 大仓库里 UT、DT、integration、e2e 混在一起时，只模仿局部最近邻 UT。
- Windows 本地保存代码和修改，但只能把代码同步到 Linux 执行机上编译、跑 DT 和覆盖率。
- C++/CMake、Python unittest、Python pytest、Node/Jest 项目的起步配置。

## 安装

解压 `ut-cover-agent-tool.zip` 后，进入工具目录：

```powershell
py -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -e .
ut-cover --version
```

如果当前 shell 找不到 `ut-cover`，可以使用：

```powershell
.\.venv\Scripts\python -m ut_cover_agent_tool --version
```

## 两个目录不要混淆

工具目录：解压和安装本工具的位置。

目标仓库：真正要补 UT、跑覆盖率的业务代码仓。

示例：

```text
C:\Tools\ut-cover-agent-tool        # 工具目录
C:\Work\my-product-repo             # 目标仓库
```

不要把工具源码复制进目标仓库。目标仓库只会生成 `.ut-cover.yaml` 配置文件和 `.ut-cover/` 运行产物。

## 新手最简单用法

不要手动复制 `examples/.ut-cover.yaml`。让主 AI 或你自己执行：

```powershell
ut-cover init-config --repo C:\Work\my-product-repo
```

它会自动识别目标仓库类型，并在目标仓库根目录生成：

```text
C:\Work\my-product-repo\.ut-cover.yaml
```

支持的自动识别：

- 发现 `CMakeLists.txt` 或 `.cpp/.cc/.hpp` 等文件：生成 C++/CMake/gcovr 起步配置。
- 发现 pytest 配置或依赖：生成 Python pytest 配置。
- 发现 Jest 配置或依赖：生成 Node/Jest 配置。
- 判断不出来：使用 Python unittest 作为保守默认值。

如果项目测试命令很特殊，主 AI 应先看目标仓库的 README、CI、构建脚本、CMakePresets，再调整 `.ut-cover.yaml`。

## 覆盖率目标

不要求用户手动改 YAML。主 AI 应询问：

- 整体覆盖率目标是多少？
- 本次变更文件覆盖率目标是多少？
- 覆盖率报告无法判断时，是警告还是失败？

用户不知道时使用推荐值：

```powershell
ut-cover set-coverage-goal --repo C:\Work\my-product-repo --overall 80 --changed-files 85 --unknown-action warn
```

之后 `run-coverage` 会输出 `coverage_gate`：

- `passed`：覆盖率达标。
- `failed`：覆盖率不达标。
- `unknown`：覆盖率报告缺失或无法判断。

AI 必须按 `next_action` 行动，不要自己猜。

## C++ 支持

本工具适用 C++ 代码仓，但 C++ 构建差异很大，默认配置只是起点：

```yaml
test_command: 'ctest --test-dir build --output-on-failure'
coverage_command: 'gcovr -r . --xml-pretty -o coverage.xml'
coverage_report: 'coverage.xml'
source_dirs:
  - 'src'
  - 'include'
test_dirs:
  - 'tests'
  - 'test'
```

如果目标仓库没有现成 `build` 目录，主 AI 不能直接盲跑。应先查：

- `README.md`
- `CMakeLists.txt`
- `CMakePresets.json`
- CI 配置
- 项目自带构建脚本

常见 CMake 起步命令可能是：

```powershell
cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug
cmake --build build
ctest --test-dir build --output-on-failure
gcovr -r . --xml-pretty -o coverage.xml
```

但如果项目使用 MSVC、Bazel、Makefile、Ninja、自研构建系统或远端 Linux 编译，应按项目实际命令修改配置。

## Windows 本地 + Linux 远端执行

当 Windows 本地无法编译时，可以启用远端模式。工具会：

1. 把 Windows 当前工作区同步到 Linux 执行机，包括未提交的测试修改。
2. 在远端隔离目录中执行构建命令和 DT/覆盖率命令。
3. 拉回日志、coverage、DT report 等产物。
4. 分类失败原因并输出 `next_action`。

远端连接和凭据复用 `Create_tool` 里已有的 `ai_ssh_mcp`，本工具不重新实现凭据管理。

配置示例：

```yaml
execution_mode: 'remote'
remote_backend: 'ai_ssh_mcp'
remote_workspace_root: '/tmp/ut-cover'
remote_build_command: './build.sh'
remote_dt_command: './run_dt.sh'
remote_artifacts:
  - 'coverage.xml'
  - 'build.log'
  - 'dt.log'
sync_include:
  - '**/*'
sync_exclude:
  - '.git/**'
  - 'build/**'
  - '.ut-cover/**'
remote_clean_before_sync: true
```

远端命令：

```powershell
ut-cover remote-doctor --repo C:\Work\my-product-repo
ut-cover remote-sync --repo C:\Work\my-product-repo
ut-cover remote-run --repo C:\Work\my-product-repo
ut-cover remote-fetch --repo C:\Work\my-product-repo
ut-cover remote-diagnose --repo C:\Work\my-product-repo
```

如果 `.ut-cover.yaml` 里是 `execution_mode: 'remote'`，直接运行下面命令也会走完整远端流程：

```powershell
ut-cover run-coverage --repo C:\Work\my-product-repo
```

更详细的弱主 AI 远端步骤见 `REMOTE_WORKFLOW.md`。

## 固定工作流

主 AI 应按这个顺序执行：

```powershell
ut-cover init-config --repo <repo>
ut-cover set-coverage-goal --repo <repo> --overall 80 --changed-files 85 --unknown-action warn
ut-cover doctor --repo <repo>
ut-cover analyze-commits --repo <repo> --commit <ids>
ut-cover inspect-tests --repo <repo>
ut-cover plan-tests --repo <repo>
```

然后 AI 只能模仿 `plan-tests` 里 1-3 个高置信度 UT 邻居。遇到 `low_confidence` 必须停下说明原因。

写完或修改 UT 后：

```powershell
ut-cover run-coverage --repo <repo>
ut-cover review-tests --repo <repo> --touched-test <test_path>
ut-cover report --analysis <repo>\.ut-cover\analysis.json --coverage <repo>\.ut-cover\coverage.json --touched-test <test_path>
```

## 防止模仿错 UT 风格

工具默认不做全仓库测试风格总结。`inspect-tests` 和 `plan-tests` 只围绕 commit 变更源码查局部最近邻测试。

默认会把这些路径或文件名判为非 UT 候选：

```text
integration, e2e, system, dt, device, driver, hardware, scenario, acceptance
```

可以通过 `.ut-cover.yaml` 调整：

```yaml
unit_test_include: []
unit_test_exclude: []
dt_test_patterns:
  - '*integration*'
  - '*e2e*'
  - '*system*'
  - '*dt*'
preferred_test_roots: []
```

## 报告内容

最终报告包含：

- commit id
- 变更文件
- 测试命令结果
- 覆盖率摘要
- 覆盖率门槛结果
- 未覆盖文件/行
- Agent 新增或修改的测试文件列表

默认输出：

```text
.ut-cover\analysis.json
.ut-cover\test-neighbors.json
.ut-cover\test-plan.json
.ut-cover\test-review.json
.ut-cover\coverage.json
.ut-cover\reports\ut-coverage-report.md
.ut-cover\reports\ut-coverage-report.json
```

## Git 查找

`doctor` 会按顺序查找 Git：

1. `PATH`
2. `UT_COVER_GIT`
3. GitHub Desktop 自带 Git
4. Program Files Git
5. Scoop
6. Chocolatey

也可以手动指定：

```powershell
$env:UT_COVER_GIT="C:\path\to\git.exe"
```

## 自动化测试

当前测试位于 `tests/`，共 34 个用例，覆盖：

- 配置读取和默认值。
- Git 查找。
- commit 列表解析。
- coverage JSON/XML 解析。
- JSON/Markdown 报告生成。
- ZIP 打包隔离。
- C++/Python/Node 自动识别。
- UT/DT 邻居分类。
- `plan-tests`、`review-tests`。
- `set-coverage-goal`。
- 覆盖率门槛 passed/failed/unknown。
- 远端同步 include/exclude。
- 远端工作区路径安全校验。
- mock 远端上传、执行、拉回和失败诊断。

运行：

```powershell
$env:PYTHONPATH="src"
python -m unittest discover -s tests -v
```

## 打包 ZIP

在工具目录执行：

```powershell
python scripts\package_zip.py
```

默认输出：

```text
..\ut-cover-agent-tool.zip
```

ZIP 只包含 `ut-cover-agent-tool/` 独立子项目，不包含虚拟环境、缓存、构建产物、覆盖率产物和旧的 AI SSH MCP 工具文件。

## 无人值守模式

用户说“我要休息”“你自己跑完”时，OpenCode 主 AI 可以开启无人值守：

```powershell
ut-cover set-autonomous-mode --repo C:\Work\my-product-repo --enable true
```

用户回来后关闭：

```powershell
ut-cover set-autonomous-mode --repo C:\Work\my-product-repo --enable false
```

查看当前状态：

```powershell
ut-cover autonomous-status --repo C:\Work\my-product-repo
```

无人值守模式下，缺少覆盖率目标时自动使用整体 `80`、变更文件 `85`、unknown 为 `warn`。没有高置信度 UT 邻居时，工具会让 AI 使用最小 UT 模板，而不是模仿 DT/integration/e2e。

如果用户提前给了远端环境修复指令，可以写入配置：

```powershell
ut-cover set-recovery-instructions --repo C:\Work\my-product-repo --command "source /opt/test-env.sh"
```

## 已有旧版本时升级

后续阶段性 ZIP 交付时，把下面两个 ZIP 放在同一目录：

```text
ut-cover-agent-tool.zip
ai-ssh-mcp-tool.zip
```

先检查：

```powershell
ut-cover upgrade-status --install-dir C:\Tools\ut-cover-agent-tool --zip-dir C:\Tools
```

再原地升级：

```powershell
ut-cover upgrade --install-dir C:\Tools\ut-cover-agent-tool --ut-zip C:\Tools\ut-cover-agent-tool.zip
```

更完整步骤见 `UPGRADE.md` 和 `OPENCODE_UPGRADE.md`。
