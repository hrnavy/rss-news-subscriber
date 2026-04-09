# Wiki 人物健康检查工具规范

## 1. 背景与问题

### 1.1 当前存在的问题

经过对现有 Wiki 人物页面的分析，发现以下问题：

#### 问题 1：名字重复/合并问题
- **拼写差异**：`Volodymyr Zelensky` 和 `Volodymyr Zelenskyy` 是同一个人，但被创建为两个独立页面
- **中英文名**：`Donald Trump` 和 `特朗普` 是同一个人，但被分开处理
- **别名问题**：`Kanye West` 和 `Kanye West Ye` 是同一个人
- **称谓差异**：`Ali Khamenei` 和 `Ayatollah Ali Khamenei` 可能是同一个人
- **非人物实体**：`Iran.md`、`Israel.md`、`Bahrain.md` 等是国家名，不应该作为人物

#### 问题 2：时间线质量问题
当前时间线直接使用新闻标题，例如：
```
- **2026-04-05**: Ukraine's Zelensky fears Iran war may lead to less support to fight Russia's invasion
```
应该总结人物在该事件中做了什么：
```
- **2026-04-05**: 泽连斯基表示担心中东战争可能削弱美国对乌克兰的支持，特别是爱国者导弹的供应
```

#### 问题 3：新闻来源缺失
当前相关新闻只显示标题和日期：
```
- [Ukraine's Zelensky fears Iran war may lead to less support to fight Russia's invasion](article://2012) - 2026-04-05
```
缺少新闻来源信息（如新闻网站名称）。

#### 问题 4：LLM 臆测问题
当前 LLM 直接生成人物信息，没有基于新闻全文给出理由，可能导致不准确的信息。

## 2. 解决方案

### 2.1 健康检查工具架构

创建 `WikiHealthCheckService` 服务，提供以下功能：

```
wiki_health_check/
├── services/
│   └── wiki_health_check_service.py  # 健康检查核心服务
├── cli/
│   └── wiki_health_cmd.py            # 命令行工具
└── models/
    └── health_check_result.py        # 检查结果数据模型
```

### 2.2 核心功能模块

#### 模块 1：名字合并检查器 (NameMergeChecker)

**功能**：检测可能重复的人物名称，基于新闻全文分析是否为同一人

**检查规则**：
1. 字符串相似度检测（Levenshtein 距离）
2. 中文名与英文名对应检测
3. 别名检测（如 Ye = Kanye West）
4. 称谓差异检测（如 Ayatollah 是尊称）

**LLM 分析流程**：
1. 收集所有相关新闻全文
2. 构建 prompt，要求 LLM 基于新闻内容判断是否为同一人
3. 必须给出基于新闻原文的理由
4. 返回合并建议

**输出格式**：
```json
{
  "potential_duplicates": [
    {
      "names": ["Volodymyr Zelensky", "Volodymyr Zelenskyy"],
      "is_same_person": true,
      "confidence": 0.95,
      "reason": "根据新闻原文，两者均指乌克兰总统，在新闻中描述了相同的角色和行为",
      "evidence": [
        "新闻 ID 2012 中提到 'Ukraine's Zelensky'",
        "新闻 ID 2123 中提到 'Zelenskyy says'"
      ],
      "suggested_primary_name": "Volodymyr Zelensky"
    }
  ]
}
```

#### 模块 2：时间线质量检查器 (TimelineQualityChecker)

**功能**：检查时间线是否只是新闻标题，生成基于全文的人物行为总结

**检查规则**：
1. 检测时间线条目是否与新闻标题完全相同
2. 检测是否缺少人物行为描述

**LLM 分析流程**：
1. 获取时间线对应的新闻全文
2. 构建 prompt，要求 LLM 总结人物在该事件中的行为
3. 限制上下文长度，分批处理长文章

**输出格式**：
```json
{
  "timeline_issues": [
    {
      "date": "2026-04-05",
      "original": "Ukraine's Zelensky fears Iran war may lead to less support to fight Russia's invasion",
      "improved": "泽连斯基表示担心中东战争可能削弱美国对乌克兰的支持，特别是爱国者导弹的供应",
      "article_id": 2012
    }
  ]
}
```

#### 模块 3：新闻来源检查器 (NewsSourceChecker)

**功能**：检查并补充新闻来源信息

**实现方式**：
1. 通过 `feed_id` 关联 `feeds` 表获取新闻源标题
2. 在相关新闻中添加来源字段

**输出格式**：
```json
{
  "news_with_source": [
    {
      "title": "Ukraine's Zelensky fears Iran war...",
      "source": "Reuters",
      "date": "2026-04-05",
      "article_id": 2012
    }
  ]
}
```

#### 模块 4：非人物实体检测器 (NonPersonEntityChecker)

**功能**：检测被错误分类为人物的非人物实体

**检查规则**：
1. 国家名检测（如 Iran, Israel, Bahrain）
2. 组织名检测（如 Planet Labs PBC）
3. LLM 辅助判断

**输出格式**：
```json
{
  "non_person_entities": [
    {
      "name": "Iran",
      "type": "country",
      "suggested_action": "move_to_events_or_delete"
    }
  ]
}
```

### 2.3 上下文限制处理

为避免 LLM 上下文限制问题：

1. **全文获取策略**：
   - 从数据库获取完整的 `content` 字段
   - 不截断新闻内容

2. **分批处理策略**：
   - 单篇文章超过 `MAX_ARTICLE_CHARS` 时，分多次 LLM 调用
   - 每批处理后汇总结果

3. **Token 估算**：
   - 使用现有的 `estimate_tokens` 方法
   - 确保每批不超过 `BATCH_MAX_TOKENS`

### 2.4 命令行接口

```bash
# 运行完整健康检查
rss-news wiki health-check

# 只检查名字合并
rss-news wiki health-check --check names

# 只检查时间线质量
rss-news wiki health-check --check timeline

# 只检查新闻来源
rss-news wiki health-check --check source

# 自动修复问题
rss-news wiki health-check --fix

# 生成报告
rss-news wiki health-check --report
```

## 3. 数据模型

### 3.1 健康检查结果

```python
@dataclass
class HealthCheckResult:
    check_type: str                    # 检查类型
    status: str                        # pass/warning/error
    issues: list[dict]                 # 问题列表
    suggestions: list[dict]            # 建议列表
    timestamp: str                     # 检查时间
```

### 3.2 名字合并建议

```python
@dataclass
class NameMergeSuggestion:
    names: list[str]                   # 可能重复的名字列表
    is_same_person: bool               # 是否为同一人
    confidence: float                  # 置信度
    reason: str                        # 基于新闻的理由
    evidence: list[str]                # 证据（新闻引用）
    suggested_primary_name: str        # 建议的主名称
```

### 3.3 时间线改进建议

```python
@dataclass
class TimelineImprovement:
    person_name: str                   # 人物名称
    date: str                          # 日期
    original: str                      # 原始内容
    improved: str                      # 改进后内容
    article_id: int                    # 关联文章 ID
```

## 4. 实现要点

### 4.1 LLM Prompt 设计

**名字合并判断 Prompt**：
```
你是一个实体识别专家。请基于以下新闻全文，判断这些名字是否指向同一个人。

名字列表：{names}

相关新闻全文：
{articles}

请回答：
1. 这些名字是否指向同一个人？
2. 你的判断依据是什么？必须引用新闻原文。
3. 如果是同一人，建议使用哪个名字作为主名称？

注意：不要臆测，必须基于新闻原文给出理由。
```

**时间线改进 Prompt**：
```
请基于以下新闻全文，总结 {person_name} 在这个事件中做了什么。

新闻全文：
{article_content}

要求：
1. 用一句话总结人物的行为或表态
2. 不要只复述新闻标题
3. 必须基于新闻原文
```

### 4.2 数据库查询优化

修改 `_get_articles_by_ids` 方法，增加 `feed_id` 和关联查询：

```sql
SELECT a.id, a.title, a.content, a.published_at, f.title as source_name
FROM articles a
LEFT JOIN feeds f ON a.feed_id = f.id
WHERE a.id IN (?)
```

### 4.3 Wiki 页面生成改进

修改 `generate_person_page` 方法：

1. 相关新闻增加来源字段
2. 时间线使用 LLM 生成的行为总结
3. 保留原始新闻标题作为链接

## 5. 预期成果

1. **健康检查报告**：生成详细的 Wiki 健康检查报告
2. **合并建议**：提供基于新闻全文的名字合并建议
3. **时间线改进**：自动改进时间线内容质量
4. **新闻来源补充**：为相关新闻添加来源信息
5. **自动修复**：支持自动修复检测到的问题
