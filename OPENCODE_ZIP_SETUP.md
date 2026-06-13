# OpenCode 主 AI 使用 ZIP 安装配置指南

这份文档给 OpenCode 的主 AI 使用，用于从 `ut-cover-agent-tool.zip` 安装并配置 UT 覆盖率工具。

如果用户只是想了解工具能力，请读 `README.md`。
如果用户已经要执行“给 commit 补 UT 并算覆盖率”，请在安装完成后调用 `.opencode/agents/ut-coverage-writer.md` 对应的子代理。

## 目标

把 `ut-cover-agent-tool.zip` 解压成一个独立工具目录，安装 Python CLI，使 `ut-cover` 命令可用，然后指导用户把 `.ut-cover.yaml` 配到真正要补 UT 的目标仓库。

## 目录概念

需要区分两个目录：

```text
工具目录：安装 ut-cover-agent-tool 的地方
目标仓库：用户真正要补 UT、算覆盖率的业务代码仓库
```

示例：

```text
C:\Tools\ut-cover-agent-tool        # 工具目录
C:\Work\my-product-repo             # 目标仓库
```

不要把工具源码复制进目标仓库。目标仓库只需要一个 `.ut-cover.yaml` 配置文件和运行后生成的 `.ut-cover/` 报告目录。

## 安装步骤

1. 询问或确认用户希望把 ZIP 解压到哪里。推荐：

```text
C:\Tools\ut-cover-agent-tool
```

2. 解压 `ut-cover-agent-tool.zip`，确认工具目录里存在：

```text
pyproject.toml
README.md
OPENCODE_ZIP_SETUP.md
examples\.ut-cover.yaml
.opencode\agents\ut-coverage-writer.md
src\ut_cover_agent_tool\
```

3. 在工具目录安装：

```powershell
py -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -e .
```

如果没有 `py`，查找 Python 3.10+ 并使用完整路径。

4. 验证 CLI：

```powershell
ut-cover --version
```

如果当前 shell 找不到 `ut-cover`，优先使用工具目录里的 Python 运行：

```powershell
.\.venv\Scripts\python -m ut_cover_agent_tool --version
```

## Git 处理

先运行：

```powershell
ut-cover doctor --repo <目标仓库路径>
```

如果提示找不到 Git，不要直接认定用户没安装 Git。按顺序检查：

1. `PATH` 中是否有 `git.exe`。
2. `UT_COVER_GIT` 是否已设置。
3. GitHub Desktop 自带 Git，例如：

```text
C:\Users\<USER>\AppData\Local\GitHubDesktop\app-*\resources\app\git\cmd\git.exe
```

4. Program Files Git、Scoop、Chocolatey 常见安装路径。

本工具已经内置这些查找逻辑。`doctor` 成功找到 Git 时会显示实际使用的 `git.exe` 路径。

如果仍找不到，可以让用户设置：

```powershell
$env:UT_COVER_GIT="C:\path\to\git.exe"
```

## 配置目标仓库

新手优先使用自动生成配置，不要让用户手工复制文件。

```powershell
ut-cover init-config --repo C:\Work\my-product-repo
```

这个命令会在目标仓库根目录生成：

```text
C:\Work\my-product-repo\.ut-cover.yaml
```

默认使用自动识别。主 AI 不应该让新手自己判断语言，应该先运行：

```powershell
ut-cover init-config --repo C:\Work\my-product-repo
```

工具会根据目标仓库文件自动选择常见预设：

- `cpp-cmake-gcovr`：发现 `CMakeLists.txt` 或 C/C++ 源码文件。
- `python-pytest`：发现 pytest 配置或依赖。
- `node-jest`：发现 Jest 配置或依赖。
- `python-unittest`：无法判断时的默认值。

如果主 AI 已经从仓库文件判断出测试框架，也可以显式选择：

```powershell
ut-cover init-config --repo C:\Work\my-product-repo --preset python-unittest
ut-cover init-config --repo C:\Work\my-product-repo --preset python-pytest
ut-cover init-config --repo C:\Work\my-product-repo --preset node-jest
ut-cover init-config --repo C:\Work\my-product-repo --preset cpp-cmake-gcovr
```

如果目标仓库已经有明确测试命令，可以直接覆盖预设命令：

```powershell
ut-cover init-config --repo C:\Work\my-product-repo `
  --test-command "项目自己的测试命令" `
  --coverage-command "项目自己的覆盖率命令"
```

生成后的 `.ut-cover.yaml` 内容类似：

```yaml
test_command: "项目自己的测试命令"
coverage_command: "项目自己的覆盖率命令，并生成 coverage_report"
coverage_report: "coverage.json 或 coverage.xml"
source_dirs: ["源码目录"]
test_dirs: ["测试目录"]
exclude: [".venv", "node_modules", "dist", "build"]
report_dir: ".ut-cover/reports"
```

重点是 `coverage_command` 必须能生成 `coverage_report` 指向的文件。

Python 示例：

```yaml
test_command: "python -m unittest discover"
coverage_command: "python -m coverage run -m unittest discover && python -m coverage json -o coverage.json"
coverage_report: "coverage.json"
source_dirs: ["src"]
test_dirs: ["tests"]
exclude: [".venv", "node_modules", "dist", "build"]
report_dir: ".ut-cover/reports"
```

Windows 下如果命令包含反斜杠路径，优先用单引号，避免 YAML 双引号把 `\U` 当作转义。

## C++ 仓库处理规则

本工具支持 C++，但 C++ 覆盖率依赖项目自己的构建方式。

自动识别到 C++/CMake 后，会生成类似配置：

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

主 AI 必须检查目标仓库是否已经有 build 目录、CMake preset、CI 脚本或 README 构建说明。

如果没有现成 build，先不要盲目运行覆盖率。应根据仓库实际情况补充构建步骤，例如：

```powershell
cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug
cmake --build build
ctest --test-dir build --output-on-failure
gcovr -r . --xml-pretty -o coverage.xml
```

如果项目使用 MSVC、Bazel、Makefile、Ninja、多平台脚本或自定义测试框架，主 AI 应改写 `.ut-cover.yaml` 中的命令，而不是强行套用 CMake/gcovr 默认值。

## 验证目标仓库

配置后运行：

```powershell
ut-cover doctor --repo C:\Work\my-product-repo
```

期望结果：

- Git 可用。
- 目标路径是 git 仓库。
- `.ut-cover.yaml` 已找到。
- `test_command` 或 `coverage_command` 已配置。

覆盖率报告不存在不一定是错误，因为第一次运行覆盖率前通常还没有报告文件。

## 交给子代理执行 UT 工作

安装和配置完成后，让 OpenCode 使用子代理：

```text
Use ut-coverage-writer. For repo C:\Work\my-product-repo, add UT for commits abc123 def456 and calculate coverage.
```

子代理必须按 `.opencode\agents\ut-coverage-writer.md` 中的流程执行：

1. `ut-cover doctor`
2. `ut-cover analyze-commits`
3. 分析 diff 和变更源码
4. 新增或修改 UT
5. `ut-cover run-coverage`
6. 失败则迭代修复
7. `ut-cover report`

## 常见输出位置

默认情况下，目标仓库会生成：

```text
.ut-cover\analysis.json
.ut-cover\coverage.json
.ut-cover\reports\ut-coverage-report.md
.ut-cover\reports\ut-coverage-report.json
```

这些是运行产物，不需要放进工具 ZIP。
