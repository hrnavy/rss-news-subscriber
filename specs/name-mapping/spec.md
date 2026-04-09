# 人名映射库规范

## 背景

当前的健康检查工具使用音译映射表来检测中英文名对应关系，但这种方式可能导致误判。例如：
- `Judd Trump` 和 `Donald Trump` 都包含 `Trump`，但不是同一个人
- 音译规则可能不完整，无法覆盖所有情况

## 目标

1. **基于新闻内容验证名字关联**：不再仅依赖音译规则，而是通过 LLM 分析相关新闻内容来判断两个名字是否指向同一个人
2. **建立持久化人名映射库**：存储已确认的名字关联关系，包括：
   - 中英文名对应（如 `特朗普` ↔ `Donald Trump`）
   - 不同拼写（如 `Zelensky` ↔ `Zelenskyy`）
   - 别名/昵称（如 `Ye` ↔ `Kanye West`）
3. **在 Wiki 生成时使用映射库**：生成新页面时自动查询映射库，避免创建重复页面

## 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                    Wiki 生成流程                             │
├─────────────────────────────────────────────────────────────┤
│  1. 提取新闻中的人名                                         │
│  2. 查询人名映射库 ──────→ 命中 → 使用规范名称               │
│         ↓ 未命中                                             │
│  3. 创建新页面                                               │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    健康检查流程                              │
├─────────────────────────────────────────────────────────────┤
│  1. 检测潜在重复名字（相似度 + 音译规则）                     │
│  2. 查询人名映射库 ──────→ 已确认 → 跳过                     │
│         ↓ 未确认                                             │
│  3. LLM 分析新闻内容                                         │
│  4. 用户确认 / 自动确认                                      │
│  5. 存入人名映射库                                           │
└─────────────────────────────────────────────────────────────┘
```

## 数据模型

### 人名映射表 (name_mappings)

```python
@dataclass
class NameMapping:
    id: int                          # 主键
    primary_name: str                # 主名称（规范名称）
    variant_name: str                # 变体名称
    variant_type: VariantType        # 变体类型
    confidence: float                # 置信度 (0.0-1.0)
    source: MappingSource            # 来源
    evidence: list[str]              # 证据（新闻摘要/来源）
    article_ids: list[int]           # 相关文章 ID
    created_at: datetime             # 创建时间
    updated_at: datetime             # 更新时间
    verified: bool                   # 是否已人工验证

class VariantType(Enum):
    CHINESE_TRANSLATION = "chinese_translation"  # 中文译名
    SPELLING_VARIANT = "spelling_variant"        # 拼写变体
    ALIAS = "alias"                              # 别名/昵称
    FULL_NAME = "full_name"                      # 全名 vs 简称

class MappingSource(Enum):
    LLM_ANALYSIS = "llm_analysis"      # LLM 分析得出
    USER_CONFIRMED = "user_confirmed"  # 用户确认
    MANUAL_ENTRY = "manual_entry"      # 手动录入
    PREDEFINED = "predefined"          # 预定义规则
```

### 数据库表结构

```sql
CREATE TABLE name_mappings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    primary_name TEXT NOT NULL,        -- 规范名称
    variant_name TEXT NOT NULL,        -- 变体名称
    variant_type TEXT NOT NULL,        -- 变体类型
    confidence REAL NOT NULL,          -- 置信度
    source TEXT NOT NULL,              -- 来源
    evidence TEXT,                     -- 证据 JSON 数组
    article_ids TEXT,                  -- 相关文章 ID JSON 数组
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    verified INTEGER DEFAULT 0,        -- 是否已验证
    UNIQUE(variant_name, primary_name)
);

-- 索引：快速查询变体名称
CREATE INDEX idx_variant_name ON name_mappings(variant_name);
CREATE INDEX idx_primary_name ON name_mappings(primary_name);
```

## 核心功能

### 1. 人名映射服务 (NameMappingService)

```python
class NameMappingService:
    def get_primary_name(self, name: str) -> str | None:
        """查询变体名称对应的主名称"""
        
    def get_all_variants(self, primary_name: str) -> list[str]:
        """获取主名称的所有变体"""
        
    def add_mapping(self, mapping: NameMapping) -> bool:
        """添加新的映射关系"""
        
    def confirm_mapping(self, mapping_id: int) -> bool:
        """确认映射关系（用户验证）"""
        
    def analyze_and_add(
        self, 
        names: list[str], 
        article_ids: list[int]
    ) -> NameMapping | None:
        """分析名字关联并添加映射"""
```

### 2. LLM 名字分析

```python
def analyze_name_relationship(
    name1: str,
    name2: str,
    articles: list[dict],
) -> NameMapping | None:
    """
    使用 LLM 分析两个名字是否指向同一个人
    
    分析步骤：
    1. 提取两个名字相关的新闻内容
    2. LLM 分析新闻中的上下文
    3. 判断是否为同一人
    4. 返回分析结果和证据
    """
```

### 3. Wiki 生成集成

```python
def normalize_person_name(name: str) -> str:
    """
    在生成 Wiki 页面前规范化人名
    
    1. 查询映射库
    2. 如果找到映射，返回主名称
    3. 否则返回原名称
    """
```

## 工作流程

### 健康检查流程

```
输入: 潜在重复名字组 ['特朗普', 'Donald Trump']

1. 查询映射库
   - SELECT * FROM name_mappings WHERE variant_name IN ('特朗普', 'Donald Trump')
   
2. 如果已存在映射 → 返回已确认的关系

3. 如果不存在映射:
   a. 获取相关文章内容
   b. LLM 分析:
      - 提取新闻中提到的人名上下文
      - 判断是否指向同一实体
      - 提供证据和置信度
   c. 如果置信度 >= 0.8:
      - 自动添加到映射库
      - 标记为待验证
   d. 如果置信度 < 0.8:
      - 标记为需要人工确认

输出: NameMapping 或 None
```

### Wiki 生成流程

```
输入: 新闻中提取的人名 '特朗普'

1. 查询映射库
   - SELECT primary_name FROM name_mappings WHERE variant_name = '特朗普'
   
2. 如果找到:
   - 使用主名称 'Donald Trump'
   - 检查是否已存在该页面
   
3. 如果未找到:
   - 使用原名称 '特朗普'
   - 创建新页面

输出: 规范化后的名称
```

## 命令行接口

### 新增命令

```bash
# 查询人名映射
rss-news name-mapping lookup "特朗普"

# 添加映射（手动）
rss-news name-mapping add "Donald Trump" "特朗普" --type chinese_translation

# 列出所有映射
rss-news name-mapping list

# 验证待确认的映射
rss-news name-mapping verify

# 从健康检查结果批量添加
rss-news name-mapping import --from-health-check report.json

# 导出映射库
rss-news name-mapping export --output mappings.json

# 导入映射库
rss-news name-mapping import --file mappings.json
```

## 预定义映射

系统启动时加载预定义的常见映射：

```python
PREDEFINED_MAPPINGS = [
    # 美国政要
    ("Donald Trump", "特朗普", VariantType.CHINESE_TRANSLATION),
    ("Donald Trump", "川普", VariantType.CHINESE_TRANSLATION),
    ("Joe Biden", "拜登", VariantType.CHINESE_TRANSLATION),
    ("Barack Obama", "奥巴马", VariantType.CHINESE_TRANSLATION),
    
    # 俄罗斯
    ("Vladimir Putin", "普京", VariantType.CHINESE_TRANSLATION),
    
    # 乌克兰
    ("Volodymyr Zelensky", "泽连斯基", VariantType.CHINESE_TRANSLATION),
    ("Volodymyr Zelensky", "Volodymyr Zelenskyy", VariantType.SPELLING_VARIANT),
    
    # 中国
    ("Xi Jinping", "习近平", VariantType.CHINESE_TRANSLATION),
    
    # 其他
    ("Elon Musk", "马斯克", VariantType.CHINESE_TRANSLATION),
    ("Kanye West", "Ye", VariantType.ALIAS),
    ("Kim Jong-un", "金正恩", VariantType.CHINESE_TRANSLATION),
    # ... 更多预定义映射
]
```

## 实现优先级

1. **P0 - 核心功能**
   - 数据库表创建
   - NameMappingService 基础实现
   - LLM 名字分析逻辑

2. **P1 - 集成**
   - 健康检查集成
   - Wiki 生成集成
   - 预定义映射加载

3. **P2 - 命令行**
   - name-mapping 命令组
   - 导入/导出功能

4. **P3 - 优化**
   - 批量分析优化
   - 缓存机制
   - 统计报告
