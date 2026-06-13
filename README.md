# UT 覆盖率 Agent 工具

`ut-cover-agent-tool` 是一个独立的 UT 与覆盖率辅助工具，用于根据 git commit id 列表分析代码变更、运行测试、解析覆盖率，并辅助 OpenCode Agent 补充单元测试。

它的设计原则是：确定性的工作放在 CLI 里完成，测试怎么补、失败怎么修这类需要判断的工作交给 OpenCode Agent 编排。

## 主要功能

- 读取 commit id 列表，提取 commit 元信息、变更文件和 diff。
- 按目标仓库配置运行测试命令或覆盖率命令。
- 解析 coverage.py JSON 和 Cobertura XML 覆盖率报告。
- 生成 JSON 和 Markdown 格式的 UT/覆盖率报告。
- 提供 OpenCode 子代理工作流，用于自动分析缺失测试、补 UT、反复验证。

CLI 本身不会直接生成测试代码。OpenCode Agent 会读取 CLI 的分析结果，判断要补哪些测试，然后调用 CLI 反复运行测试和覆盖率，直到结果明确。

## 安装

在 `ut-cover-agent-tool` 目录中执行：

```powershell
py -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -e .
```

如果系统没有 `py`，请使用 Python 3.10 或更高版本的完整路径。

验证安装：

```powershell
ut-cover --version
ut-cover doctor --repo <TARGET_REPO>
```

Git 查找顺序为：先查 `PATH`，再查 `UT_COVER_GIT` 环境变量，然后查 Windows 常见安装位置，包括 GitHub Desktop、Program Files Git、Scoop 和 Chocolatey。

如果 Git 不在 `PATH` 中，也可以手动指定：

```powershell
$env:UT_COVER_GIT="C:\path\to\git.exe"
```

## 配置目标仓库

“目标仓库”指的是你真正想补 UT、算覆盖率的业务代码仓库，不是 `ut-cover-agent-tool` 这个工具仓库。

例如：

```text
C:\Tools\ut-cover-agent-tool        # 工具目录：解压和安装本工具
C:\Work\my-product-repo             # 目标仓库：要给它的 commit 补 UT
```

新手推荐不要手工复制配置文件，直接让工具自动识别目标仓库并生成：

```powershell
ut-cover init-config --repo C:\Work\my-product-repo
```

这个命令会在目标仓库根目录生成：

```text
C:\Work\my-product-repo\.ut-cover.yaml
```

工具会根据目标仓库文件自动判断常见项目类型：

- 看到 `CMakeLists.txt` 或 `.cpp/.cc/.hpp` 等文件时，按 C++/CMake 项目生成。
- 看到 `pyproject.toml`、`pytest.ini` 等 pytest 线索时，按 Python pytest 项目生成。
- 看到 `package.json` 里使用 Jest 时，按 Node/Jest 项目生成。
- 判断不出来时，使用 Python `unittest` 作为保守默认值。

如果你想手动指定，也可以选一个预设：

```powershell
ut-cover init-config --repo C:\Work\my-product-repo --preset python-pytest
ut-cover init-config --repo C:\Work\my-product-repo --preset node-jest
ut-cover init-config --repo C:\Work\my-product-repo --preset cpp-cmake-gcovr
```

如果你已经知道项目自己的测试命令，也可以直接写进去：

```powershell
ut-cover init-config --repo C:\Work\my-product-repo `
  --test-command "python -m pytest" `
  --coverage-command "python -m pytest --cov=src --cov-report=json:coverage.json"
```

如果还是不知道该选哪个命令，把目标仓库路径告诉 OpenCode 主 AI，让它查看项目文件后帮你决定。

### C++ 项目说明

本工具适用于 C++ 代码仓，但需要目标仓库本身能运行测试并生成覆盖率报告。

默认 C++ 预设是：

```yaml
test_command: 'ctest --test-dir build --output-on-failure'
coverage_command: 'gcovr -r . --xml-pretty -o coverage.xml'
coverage_report: 'coverage.xml'
source_dirs: ['src', 'include']
test_dirs: ['tests', 'test']
```

这适合常见的 CMake + CTest + gcovr 工作流。实际使用前，目标仓库通常还需要先完成带覆盖率参数的构建，例如 Debug 构建、GCC/Clang coverage flags、测试二进制已生成等。不同 C++ 项目的构建方式差异很大，所以 `init-config` 生成的是起点，OpenCode 主 AI 应根据目标仓库的 `README`、`CMakePresets.json`、CI 配置或构建脚本继续调整命令。

Python 覆盖率示例：

```yaml
test_command: "python -m unittest discover"
coverage_command: "python -m coverage run -m unittest discover && python -m coverage json -o coverage.json"
coverage_report: "coverage.json"
source_dirs: ["src"]
test_dirs: ["tests"]
exclude: [".venv", "node_modules", "dist", "build"]
report_dir: ".ut-cover/reports"
```

其他语言项目也可以使用，只要把 `coverage_command` 配置成能生成覆盖率报告的项目命令即可。第一版优先支持 coverage.py JSON 和 Cobertura XML。

Windows 下如果命令里包含反斜杠路径，建议在 `.ut-cover.yaml` 里用单引号包裹命令，因为 YAML 双引号会把 `\U` 这类内容当成转义。

配置完成后，在工具目录或任意目录执行：

```powershell
ut-cover doctor --repo C:\Work\my-product-repo
```

如果 `doctor` 显示 Git、仓库、命令配置都可用，说明目标仓库已经配置好。

## 命令行用法

分析 commit：

```powershell
ut-cover analyze-commits --repo <TARGET_REPO> --commit abc123,def456
```

从文件读取 commit id：

```powershell
ut-cover analyze-commits --repo <TARGET_REPO> --commit-file commits.txt
```

运行测试和覆盖率：

```powershell
ut-cover run-coverage --repo <TARGET_REPO>
```

生成最终报告：

```powershell
ut-cover report `
  --analysis <TARGET_REPO>\.ut-cover\analysis.json `
  --coverage <TARGET_REPO>\.ut-cover\coverage.json `
  --touched-test tests\test_example.py
```

## OpenCode 代理

Agent 文件位置：

```text
.opencode\agents\ut-coverage-writer.md
```

安装本工具并确保 `ut-cover` 可用后，可以在 OpenCode 中这样使用：

```text
Use ut-coverage-writer. For repo C:\path\to\repo, add UT for commits abc123 def456 and calculate coverage.
```

Agent 必须使用 CLI 做 commit 分析、覆盖率执行和最终报告生成。除非生产代码本身存在阻碍测试的缺陷并且你明确同意，否则 Agent 应只修改测试文件。

如果你要让 OpenCode 的主 AI 根据 ZIP 自动安装和配置本工具，请使用这个文档：

```text
OPENCODE_ZIP_SETUP.md
```

`README.md` 是给人看的使用说明，`.opencode/agents/ut-coverage-writer.md` 是子代理规则，`OPENCODE_ZIP_SETUP.md` 才是指导主 AI 如何处理 ZIP 的入口文档。

## 测试覆盖

当前自动化测试位于 `tests/`，共 17 个测试点，主要覆盖：

- `test_config.py`：配置文件默认值、YAML 配置读取。
- `test_git_tools.py`：commit 列表解析、rename 文件解析、Git 缺失提示、`UT_COVER_GIT` 环境变量、Windows Git 候选路径。
- `test_coverage.py`：coverage.py JSON 和 Cobertura XML 覆盖率解析。
- `test_reports.py`：JSON/Markdown 报告内容生成。
- `test_cli_flow.py`：用假的覆盖率生成脚本验证 `run-coverage` 到 `report` 的完整 CLI 流程。
- `test_init_config.py`：验证 `init-config` 能生成新手配置、不会误覆盖已有配置、支持命令覆盖，并能自动识别 C++/CMake、Python、Node/Jest 项目。
- `test_package_zip.py`：验证 ZIP 只包含 `ut-cover-agent-tool/`，不会混入之前的 AI SSH MCP 工具目录。

运行测试：

```powershell
$env:PYTHONPATH="src"
python -m unittest discover -s tests -v
```

## 打包 ZIP

在 `ut-cover-agent-tool` 目录中执行：

```powershell
.\.venv\Scripts\python scripts\package_zip.py
```

默认输出：

```text
..\ut-cover-agent-tool.zip
```

ZIP 只包含这个独立工具目录，不包含虚拟环境、缓存、构建产物和 `.ut-cover` 运行产物。
