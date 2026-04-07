# RSS News Subscriber

基于 Python 的 RSS 新闻订阅系统，支持本地 LLM 智能处理新闻内容。

## 功能特性

- **RSS 订阅管理** - 添加、删除、查看 RSS 订阅源
- **新闻抓取** - 自动抓取订阅源的最新新闻
- **LLM 智能处理** - 使用本地 LM Studio 进行：
  - 新闻摘要生成
  - 自动分类（科技、财经、政治等）
  - 关键词提取
- **可视化播放器** - 终端内循环播放今日新闻
- **本地存储** - SQLite 数据库存储所有新闻

## 环境要求

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) 包管理器
- [LM Studio](https://lmstudio.ai/)（可选，用于 LLM 功能）

## 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/your-username/rss-news-subscriber.git
cd rss-news-subscriber
```

### 2. 安装依赖

```bash
uv sync
```

### 3. 配置

复制配置模板并修改：

```bash
cp config/config.example.yaml config/config.yaml
```

编辑 `config/config.yaml`：

```yaml
llm:
  api_base: http://127.0.0.1:1234/v1
  model: your-model-name
  timeout: 60

fetch:
  interval: 3600
  timeout: 30
  max_retries: 3

database:
  path: data/rss_news.db

display:
  page_size: 20
```

### 4. 启动 LM Studio（可选）

如果需要使用 LLM 功能：

1. 打开 LM Studio
2. 加载模型（推荐 Qwen3.5-9B 或类似模型）
3. 启动本地服务器（默认端口 1234）

## 使用方法

### 订阅源管理

```bash
# 添加订阅源
uv run rss-news feed add https://feeds.bbci.co.uk/news/rss.xml

# 查看所有订阅源
uv run rss-news feed list

# 删除订阅源
uv run rss-news feed remove <feed_id>
```

### 新闻抓取

```bash
# 抓取所有订阅源的新闻
uv run rss-news fetch

# 查看文章列表
uv run rss-news article list

# 查看文章详情
uv run rss-news article show <article_id>
```

### LLM 智能处理

```bash
# 处理单篇文章
uv run rss-news llm summarize <article_id>
uv run rss-news llm classify <article_id>
uv run rss-news llm keywords <article_id>

# 批量处理所有待处理文章
uv run rss-news llm process-all
```

### 新闻播放器

```bash
# 启动可视化新闻播放器
uv run rss-news play

# 自定义播放间隔（秒）
uv run rss-news play -i 10

# 不显示摘要
uv run rss-news play --no-summary
```

播放器控制：
- **空格** - 暂停/继续
- **N** - 跳到下一条
- **Q** - 退出播放器

### 定时任务（后台服务）

```bash
# 启动后台服务（前台运行，按 Ctrl+C 停止）
uv run rss-news daemon

# 安装为 Windows 任务计划（开机自启）
uv run rss-news daemon install

# 卸载任务计划
uv run rss-news daemon uninstall

# 查看服务状态
uv run rss-news daemon status

# 查看日志
uv run rss-news daemon logs

# 立即执行一次任务
uv run rss-news daemon run fetch   # 只抓取
uv run rss-news daemon run llm     # 只处理
uv run rss-news daemon run all     # 全部
```

配置 `config.yaml` 中的 `daemon` 部分可调整间隔：

```yaml
daemon:
  enabled: true
  fetch_interval: 3600  # 抓取间隔（秒）
  llm_interval: 7200    # LLM处理间隔（秒）
  log_file: logs/daemon.log
```

## 项目结构

```
rss-news-subscriber/
├── config/
│   ├── config.example.yaml    # 配置模板
│   └── config.yaml            # 用户配置（需自行创建）
├── data/
│   └── rss_news.db            # SQLite 数据库
├── src/
│   └── rss_news/
│       ├── cli/               # 命令行接口
│       ├── db/                # 数据库连接与表结构
│       ├── models/            # 数据模型
│       └── services/          # 业务逻辑
├── pyproject.toml
└── README.md
```

## 数据库结构

### feeds 表（订阅源）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| title | TEXT | 订阅源标题 |
| url | TEXT | 订阅源 URL |
| description | TEXT | 描述 |
| last_fetched | TEXT | 最后抓取时间 |
| created_at | TEXT | 创建时间 |

### articles 表（文章）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| feed_id | INTEGER | 订阅源 ID |
| title | TEXT | 标题 |
| link | TEXT | 原文链接 |
| content | TEXT | 内容 |
| summary | TEXT | LLM 摘要 |
| category | TEXT | LLM 分类 |
| keywords | TEXT | LLM 关键词 |
| published_at | TEXT | 发布时间 |
| created_at | TEXT | 创建时间 |

## 推荐订阅源

```bash
# BBC News
uv run rss-news feed add https://feeds.bbci.co.uk/news/rss.xml

# AP News
uv run rss-news feed add https://news.google.com/rss

# TechCrunch
uv run rss-news feed add https://techcrunch.com/feed/

# Bloomberg
uv run rss-news feed add https://www.bloomberg.com/feed/podcast/bloomberg-technology.xml
```

## 技术栈

- **Python 3.12** - 编程语言
- **uv** - 包管理器
- **Typer** - 命令行框架
- **Rich** - 终端美化
- **feedparser** - RSS 解析
- **requests** - HTTP 请求
- **SQLite** - 数据存储

## 许可证

MIT License
