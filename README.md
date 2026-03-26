# 网页邮箱提取器

一个基于 Flask 的 Web 应用，输入批量网站 URL，自动爬取页面内容，提取所有电子邮件地址，并通过多维度评分算法智能识别每个网站的**官方联系邮箱**。

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)
![Flask](https://img.shields.io/badge/Flask-3.0-lightgrey?logo=flask)
![License](https://img.shields.io/badge/License-MIT-green)

---

## 功能特性

- **批量输入**：每行一个网址，一次性处理多个网站
- **多策略提取**：
  - 正则扫描全文（含 JS 代码块、内嵌 JSON）
  - 解析 `<a href="mailto:...">` 链接
  - 解析 JSON-LD 结构化数据中的 `"email"` 字段（优先级最高）
  - HTML 实体编码还原（`&#64;` → `@`）
  - `[at]` / `[dot]` 反混淆
- **官方邮箱评分**：综合域名匹配、官方前缀、来源页面权重、JSON-LD 声明等多个维度打分排序
- **垃圾邮箱过滤**：自动排除 Sentry、CDN、noreply 等系统服务邮箱
- **实时进度**：轮询方式每 2 秒刷新一次结果，处理完一个立即显示
- **一键导出**：结果导出为 CSV 文件
- **可执行打包**：支持 PyInstaller 打包为独立 `.exe`，无需安装 Python

---

## 界面预览

> 深色主题，支持展开/折叠每个网站的详情卡片，一键复制邮箱

```
┌─────────────────────────────────────────────┐
│  ✉ 网页邮箱提取器                            │
│  输入网站地址，自动爬取并识别官方联系邮箱      │
├─────────────────────────────────────────────┤
│  https://example.com                        │
│  https://openai.com            [开始提取]   │
├─────────────────────────────────────────────┤
│  进度 2/2  ████████████  100%               │
├─────────────────────────────────────────────┤
│  🌐 https://example.com        ✓ 已找到     │
│  ├─ 官方邮箱: info@example.com   [复制]     │
│  └─ 所有邮箱: info@example.com (85分)       │
└─────────────────────────────────────────────┘
```

---

## 快速开始

### 方式一：直接运行（需要 Python 环境）

**1. 克隆仓库**
```bash
git clone git@github.com:ohMargin/email-extractor.git
cd email-extractor
```

**2. 创建并激活 Conda 环境**
```bash
conda create -n email_extractor python=3.11 -y
conda activate email_extractor
```

**3. 安装依赖**
```bash
pip install -r requirements.txt
```

**4. 启动应用**
```bash
python app.py
```

**5. 打开浏览器访问**
```
http://127.0.0.1:5000
```

---

### 方式二：打包为独立可执行文件（分发给他人）

```bash
# 确保已激活 conda 环境
conda activate email_extractor

# 执行打包脚本（约 1-3 分钟）
build.bat
```

打包完成后：
- 可执行文件夹：`dist/邮箱提取器/`
- 压缩包：`dist/邮箱提取器.zip`

将 zip 发给朋友，解压后双击 `邮箱提取器.exe` 即可使用，**无需安装 Python 或任何依赖**。

---

## 项目结构

```
email_extractor/
├── app.py              # Flask 后端（路由、轮询 API）
├── extractor.py        # 核心逻辑（爬取、提取、评分）
├── launcher.py         # PyInstaller 打包入口（自动开浏览器）
├── debug_extract.py    # 诊断脚本（逐步展示提取过程）
├── email_extractor.spec# PyInstaller 打包配置
├── build.bat           # 一键打包脚本
├── requirements.txt    # Python 依赖
├── plan.md             # 项目设计文档
└── templates/
    └── index.html      # 前端单页面
```

---

## 官方邮箱评分算法

| 维度 | 规则 | 分值 |
|------|------|------|
| JSON-LD 声明 | 网站在结构化数据中主动声明的 `"email"` 字段 | +80 |
| 域名匹配 | 邮箱域名与目标网站主域名一致 | +50 |
| 官方前缀 | `info` / `contact` / `admin` / `support` 等 | +20 |
| 来源页面 | 来自 `/contact`、`/about` 等联系页面 | +15 |
| 免费邮箱 | Gmail / QQ / 163 等 | -30 |
| 系统邮箱 | 哈希地址、Sentry、CDN 等基础设施邮箱 | -999 |

---

## 诊断工具

遇到某个网站提取不到邮箱时，使用诊断脚本逐步排查：

```bash
python debug_extract.py https://example.com
```

输出包含每一步的详细结果：抓取状态、原始正则结果、mailto 链接、JSON-LD 内容及最终官方邮箱判断。

---

## 依赖说明

| 包 | 用途 |
|----|------|
| `flask` | Web 框架 |
| `requests` | HTTP 请求 |
| `beautifulsoup4` + `lxml` | HTML 解析 |
| `tldextract` | 精准提取主域名 |
| `fake-useragent` | 随机 User-Agent |

---

## License

[MIT](LICENSE)
