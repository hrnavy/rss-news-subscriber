"""配置管理模块

负责加载、验证和管理应用程序配置。
支持从 YAML 文件加载配置，并允许通过环境变量覆盖特定配置项。
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class LLMConfig:
    """LLM (大语言模型) 配置"""
    
    api_base: str = "http://localhost:1234/v1"
    model: str = "local-model"
    timeout: int = 60


@dataclass
class FetchConfig:
    """RSS 抓取配置"""
    
    interval: int = 3600  # 抓取间隔（秒）
    timeout: int = 30  # 请求超时（秒）
    max_retries: int = 3  # 最大重试次数


@dataclass
class DatabaseConfig:
    """数据库配置"""
    
    path: str = "data/rss_news.db"


@dataclass
class DisplayConfig:
    """显示配置"""
    
    page_size: int = 20


@dataclass
class Config:
    """应用程序总配置"""
    
    llm: LLMConfig = field(default_factory=LLMConfig)
    fetch: FetchConfig = field(default_factory=FetchConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)


def get_default_config_path() -> Path:
    """获取默认配置文件路径
    
    配置文件位于项目根目录的 config/config.yaml
    """
    current_file = Path(__file__)
    project_root = current_file.parent.parent.parent.parent
    return project_root / "config" / "config.yaml"


def load_yaml_config(config_path: Path) -> dict[str, Any]:
    """从 YAML 文件加载配置
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        配置字典，如果文件不存在则返回空字典
        
    Raises:
        yaml.YAMLError: YAML 解析错误
    """
    if not config_path.exists():
        return {}
    
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
        return data if data else {}


def apply_env_overrides(config: Config) -> Config:
    """应用环境变量覆盖配置
    
    支持的环境变量:
        - LLM_API_BASE: 覆盖 llm.api_base
        - LLM_MODEL: 覆盖 llm.model
        - LLM_TIMEOUT: 覆盖 llm.timeout
        - FETCH_INTERVAL: 覆盖 fetch.interval
        - FETCH_TIMEOUT: 覆盖 fetch.timeout
        - FETCH_MAX_RETRIES: 覆盖 fetch.max_retries
        - DATABASE_PATH: 覆盖 database.path
        - DISPLAY_PAGE_SIZE: 覆盖 display.page_size
    
    Args:
        config: 原始配置对象
        
    Returns:
        应用环境变量覆盖后的配置对象
    """
    # LLM 配置覆盖
    if api_base := os.getenv("LLM_API_BASE"):
        config.llm.api_base = api_base
    if model := os.getenv("LLM_MODEL"):
        config.llm.model = model
    if timeout := os.getenv("LLM_TIMEOUT"):
        config.llm.timeout = int(timeout)
    
    # Fetch 配置覆盖
    if interval := os.getenv("FETCH_INTERVAL"):
        config.fetch.interval = int(interval)
    if fetch_timeout := os.getenv("FETCH_TIMEOUT"):
        config.fetch.timeout = int(fetch_timeout)
    if max_retries := os.getenv("FETCH_MAX_RETRIES"):
        config.fetch.max_retries = int(max_retries)
    
    # Database 配置覆盖
    if db_path := os.getenv("DATABASE_PATH"):
        config.database.path = db_path
    
    # Display 配置覆盖
    if page_size := os.getenv("DISPLAY_PAGE_SIZE"):
        config.display.page_size = int(page_size)
    
    return config


def validate_config(config: Config) -> list[str]:
    """验证配置有效性
    
    Args:
        config: 配置对象
        
    Returns:
        错误消息列表，空列表表示验证通过
    """
    errors: list[str] = []
    
    # 验证 LLM 配置
    if not config.llm.api_base:
        errors.append("LLM API 地址不能为空")
    if not config.llm.model:
        errors.append("LLM 模型名称不能为空")
    if config.llm.timeout <= 0:
        errors.append("LLM 超时时间必须大于 0")
    
    # 验证 Fetch 配置
    if config.fetch.interval <= 0:
        errors.append("抓取间隔必须大于 0")
    if config.fetch.timeout <= 0:
        errors.append("请求超时时间必须大于 0")
    if config.fetch.max_retries < 0:
        errors.append("最大重试次数不能为负数")
    
    # 验证 Database 配置
    if not config.database.path:
        errors.append("数据库路径不能为空")
    
    # 验证 Display 配置
    if config.display.page_size <= 0:
        errors.append("每页显示数量必须大于 0")
    
    return errors


def create_config_from_dict(data: dict[str, Any]) -> Config:
    """从字典创建配置对象
    
    Args:
        data: 配置字典
        
    Returns:
        配置对象
    """
    config = Config()
    
    # 填充 LLM 配置
    if llm_data := data.get("llm"):
        config.llm = LLMConfig(
            api_base=llm_data.get("api_base", config.llm.api_base),
            model=llm_data.get("model", config.llm.model),
            timeout=llm_data.get("timeout", config.llm.timeout),
        )
    
    # 填充 Fetch 配置
    if fetch_data := data.get("fetch"):
        config.fetch = FetchConfig(
            interval=fetch_data.get("interval", config.fetch.interval),
            timeout=fetch_data.get("timeout", config.fetch.timeout),
            max_retries=fetch_data.get("max_retries", config.fetch.max_retries),
        )
    
    # 填充 Database 配置
    if db_data := data.get("database"):
        config.database = DatabaseConfig(
            path=db_data.get("path", config.database.path),
        )
    
    # 填充 Display 配置
    if display_data := data.get("display"):
        config.display = DisplayConfig(
            page_size=display_data.get("page_size", config.display.page_size),
        )
    
    return config


def load_config(config_path: Path | None = None) -> Config:
    """加载配置
    
    加载流程:
    1. 从 YAML 文件加载配置
    2. 应用环境变量覆盖
    3. 验证配置有效性
    
    Args:
        config_path: 配置文件路径，默认使用 config/config.yaml
        
    Returns:
        配置对象
        
    Raises:
        ValueError: 配置验证失败
    """
    # 确定配置文件路径
    if config_path is None:
        config_path = get_default_config_path()
    
    # 从 YAML 文件加载
    yaml_data = load_yaml_config(config_path)
    
    # 创建配置对象
    config = create_config_from_dict(yaml_data)
    
    # 应用环境变量覆盖
    config = apply_env_overrides(config)
    
    # 验证配置
    errors = validate_config(config)
    if errors:
        raise ValueError(f"配置验证失败:\n" + "\n".join(f"  - {e}" for e in errors))
    
    return config


def get_database_path(config: Config) -> Path:
    """获取数据库绝对路径
    
    Args:
        config: 配置对象
        
    Returns:
        数据库文件的绝对路径
    """
    db_path = Path(config.database.path)
    
    # 如果是相对路径，则相对于项目根目录
    if not db_path.is_absolute():
        project_root = Path(__file__).parent.parent.parent.parent
        db_path = project_root / db_path
    
    return db_path
