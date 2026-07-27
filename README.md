# Markdown Viewer

一个轻量级 Windows 桌面 Markdown / YAML 三栏预览工具。

> 让用户在不离开文件系统的前提下，获得分栏式、带导航的预览体验：标题导航树 + 渲染预览 + 原始源码视图。

[![Python](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows-lightgrey.svg)](https://www.microsoft.com/windows)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## 功能概览

- **三栏布局**：左栏文档标题导航树、中栏可编辑源码、右栏实时渲染预览；分隔条可拖拽调整宽度
- **Markdown 预览**：`.md` / `.markdown` / `.mdx` 文件渲染为 HTML；支持 h1~h6 标题提取与导航
- **YAML 结构化显示**：`.yaml` / `.yml` 文件渲染为带类型着色的 HTML 表格/树视图
- **Front Matter**：自动解析 Hugo/Jekyll 风格的 YAML front matter
- **多编码自动检测**：UTF-8-BOM → UTF-8 → GBK → GB2312 回退链，中文不丢字符
- **全文搜索**：`Ctrl+F` 搜索关键词，跳转到对应行，匹配项高亮
- **文件关联注册**：一键关联 `.md` / `.yaml` 文件到本应用（HKCU，无需管理员）
- **配置持久化**：窗口大小、主题、字体、打开历史自动保存
- **打开历史**：最近 50 条记录，按路径去重，按时间倒序
- **滚动位置记忆**：每个文件独立记住滚动位置，关闭后重新打开自动恢复
- **Markdown 语法高亮**：标题、列表、代码块在中栏编辑器中高亮显示，深色/浅色模式自适应
- **主题系统**：浅色 / 深色 / 跟随系统 / 自定义四档切换
- **自定义主题**：用户可自定义背景、文字、高亮等颜色，深色背景自动识别并切换浅色文字
- **多窗口支持**：同一文件聚焦已有窗口，不同文件打开新窗口
- **单实例模式**：通过 QLocalServer 确保同一时间只有一个应用实例
- **拖拽打开**：拖拽文件到任意栏位（左/中/右栏及 header）直接打开
- **缩放支持**：`Ctrl+鼠标滚轮` 或 `Ctrl++` / `Ctrl+-` 调整字体大小
- **打包分发**：支持 PyInstaller 打包为 Windows 可执行文件（onedir 模式）
- **字号系统**：左栏保持系统默认；中栏/右栏正文 12pt；HTML 标题层次分明（h1=24pt, h2=18pt, h3=16pt, h4=14pt, h5/h6=12pt）

### 不在范围内（当前版本）

- 跨平台支持（仅 Windows）
- 文件内容格式转换导出
- 插件系统
- 本地化/多语言界面

## 技术栈

| 层面 | 选型 | 理由 |
|------|------|------|
| Markdown 渲染 | [mistletoe](https://github.com/miyuchina/mistletoe) | 纯 Python，CommonMark 兼容，无需 JS 引擎 |
| YAML 解析 | [PyYAML](https://pyyaml.org/) | 工业标准，`safe_load` 防止代码注入 |
| GUI 框架 | PyQt5 / PySide2 | Windows 原生体验，信号槽机制 |
| 测试框架 | pytest | 生态完善，fixture 支持好 |
| 配置存储 | JSON | 人类可读，适合小数据量 |
| 打包工具 | PyInstaller | 支持 onedir/onefile 模式 |

## 项目结构

```
markdown_viewer/
├── main.py                      # 入口点
├── src/
│   ├── core/                    # 核心逻辑层（无 GUI 依赖，可独立测试）
│   │   ├── file_loader.py       # 多编码文件读取
│   │   ├── file_type_detector.py # 文件类型识别
│   │   ├── frontmatter.py       # YAML front matter 提取
│   │   ├── parser.py            # Markdown 解析、标题提取、HTML 渲染
│   │   └── yaml_renderer.py     # YAML → HTML 结构化显示
│   ├── ui/                      # UI 层（PyQt5）
│   │   └── __init__.py          # MainWindow + 三栏布局 + 主题系统
│   └── utils/                   # 系统工具层
│       ├── config.py            # 配置/历史 JSON 持久化
│       ├── file_association.py  # Windows 注册表文件关联
│       └── search.py            # 全文搜索
├── tests/                       # 单元测试
│   ├── test_core.py
│   ├── test_file_loader.py
│   ├── test_file_type.py
│   ├── test_utils.py
│   ├── test_yaml_renderer.py
│   ├── test_ui.py
│   ├── test_ui_real.py
│   ├── test_search_ui.py
│   ├── test_scroll_memory.py
│   ├── test_custom_theme.py
│   ├── test_save.py
│   └── conftest.py
├── specs/                       # 产品需求与验收标准
│   ├── PRD.md
│   └── acceptance-criteria.md
├── design/                      # 设计文档
│   ├── HLD.md
│   └── contracts/
├── memory/                      # Session 进度与架构决策
│   ├── progress.md
│   ├── decisions.md
│   ├── blockers.md
│   └── architecture.md
└── markdown_viewer.spec         # PyInstaller 打包配置
```

## 架构分层

```
┌─────────────────────────────────────────────────────────┐
│                    UI Layer (PyQt5)                      │
│            src/ui/__init__.py (MainWindow)               │
│  ┌─────────────┐ ┌──────────────┐ ┌──────────────────┐  │
│  │ SearchBar   │ │ ScrollMemory │ │ MarkdownHighlight│  │
│  │ Ctrl+F      │ │ per-file     │ │ QSyntaxHighlight │  │
│  └─────────────┘ └──────────────┘ └──────────────────┘  │
└──────────────┬──────────────────────┬───────────────────┘
               │                      │
    ┌──────────▼──────────┐  ┌───────▼───────────────┐
    │   Core Layer        │  │   Utils Layer          │
    │ src/core/           │  │ src/utils/             │
    │ ├── file_loader.py  │  │ ├── config.py          │
    │ ├── file_type_detector.py │ ├── file_association.py│
    │ ├── frontmatter.py  │  │ ├── search.py          │
    │ ├── parser.py       │  │ └── __init__.py        │
    │ └── yaml_renderer.py│  └────────────────────────┘
    └─────────────────────┘
               │
    ┌──────────▼──────────────────────────┐
    │   External Dependencies             │
    │   ├── PyQt5 (UI)                    │
    │   ├── mistletoe (Markdown→HTML)     │
    │   ├── PyYAML (YAML解析)             │
    │   └── pytest (Testing)              │
    └─────────────────────────────────────┘
```

> **关键约束**：`src/core/` 完全无 GUI 依赖，确保纯 Python 逻辑可被单独单元测试覆盖。

## 快速开始

### 环境要求

- Python 3.9+
- Windows 10/11
- PyQt5

### 安装

```bash
# 克隆项目
git clone <repo-url>
cd markdown_viewer

# 创建虚拟环境（推荐）
python -m venv .venv
.venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 运行

```bash
# 启动 GUI（打开指定文件）
python main.py your_file.md

# 或先打开空窗口，再通过菜单 File → Open 选择文件
python main.py
```

### 开发

```bash
# 运行测试
pytest tests/

# 代码检查
ruff check .
```

## 打包为 Windows 可执行文件

项目使用 PyInstaller 打包为 `onedir` 模式（启动更快，比 `onefile` 更稳定）。

### 打包步骤

```bash
# 1. 创建打包专用虚拟环境（推荐）
python -m venv .venv_build
.venv_build\Scripts\activate

# 2. 安装依赖 + PyInstaller
pip install -r requirements.txt pyinstaller

# 3. 清理旧构建
rm -rf build/ dist/

# 4. 打包
pyinstaller --clean markdown_viewer.spec

# 5. 输出在 dist/markdown_viewer/
```

### 打包输出

```
dist/markdown_viewer/
├── markdown_viewer.exe    # 主程序
└── _internal/             # 依赖库和资源
```

### 配置文件位置

打包后的 exe 会自动查找项目根目录的 `.markdown_viewer/` 文件夹：

```
D:\Python Project\markdown_viewer\.markdown_viewer\
├── config.json      # 主题、窗口大小、字体等配置
└── history.json     # 文件打开历史
```

**注意**：首次打包后，请将项目根目录已有的 `.markdown_viewer/` 复制到 `dist/markdown_viewer/.markdown_viewer/`，以保留现有配置。

## 使用示例

### Markdown 预览

1. 启动应用：`python main.py notes.md`
2. 自动解析标题并生成左侧导航树
3. 点击导航项可在中栏源码中定位对应行
4. 按 `Ctrl+F` 进行全文搜索

### YAML 结构化显示

1. 启动应用：`python main.py config.yaml`
2. 自动渲染为带类型着色的 HTML 表格/树视图
3. 支持嵌套字典和列表的递归展示

### 文件关联

1. 启动应用后，通过菜单 `Tools → Associate .md/.yaml files` 注册文件关联
2. 或使用命令行：`markdown_viewer.exe --associate`
3. 注册后，双击 `.md` / `.yaml` 文件即可用 Markdown Viewer 打开

### 多编码支持

应用自动尝试以下编码顺序：
- UTF-8-BOM → UTF-8 → GBK → GB2312

无需手动指定编码。

## 测试

```bash
# 运行全部测试
pytest tests/

# 运行指定测试文件
pytest tests/test_core.py -v
pytest tests/test_ui_real.py -v
```

## License

MIT
