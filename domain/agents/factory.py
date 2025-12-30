"""
智能体工厂
根据配置动态创建智能体实例
支持Agent缓存和热更新
"""
import yaml
import os
import threading
from typing import Dict, List, Any, Optional, TYPE_CHECKING
from langchain_core.tools import BaseTool
from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph
else:
    # 运行时使用 Any 作为类型占位符
    CompiledStateGraph = Any

from infrastructure.llm.client import get_llm
from domain.tools.registry import TOOL_REGISTRY
from app.core.config import settings
from infrastructure.prompts.manager import PromptManager
from infrastructure.prompts.placeholder import PlaceholderManager
import logging

logger = logging.getLogger(__name__)


class AgentFactory:
    """智能体工厂类"""
    
    _config: Dict[str, Any] = {}
    _config_path: str = "config/agents.yaml"
    _prompt_manager: Optional[PromptManager] = None
    
    # Agent缓存机制
    _agent_cache: Dict[str, CompiledStateGraph] = {}
    _config_mtime: Optional[float] = None
    _cache_lock = threading.Lock()
    _cache_stats: Dict[str, Any] = {
        "hits": 0,
        "misses": 0,
        "created": 0,
        "reloaded": 0,
        "cleared": 0,
    }
    
    @classmethod
    def _get_prompt_manager(cls) -> PromptManager:
        """获取提示词管理器实例（单例）"""
        if cls._prompt_manager is None:
            cls._prompt_manager = PromptManager()
        return cls._prompt_manager
    
    @classmethod
    def load_config(cls, config_path: Optional[str] = None):
        """
        加载智能体配置文件
        
        Args:
            config_path: 配置文件路径（可选）
        """
        if config_path:
            cls._config_path = config_path
        
        # 支持相对路径和绝对路径
        if not os.path.isabs(cls._config_path):
            config_path = os.path.join(os.getcwd(), cls._config_path)
        else:
            config_path = cls._config_path
        
        if os.path.exists(config_path):
            # 更新配置文件的修改时间
            current_mtime = os.path.getmtime(config_path)
            if cls._config_mtime is not None and current_mtime > cls._config_mtime:
                logger.info(f"检测到配置文件更新: {config_path}, 清除Agent缓存")
                cls._clear_cache()
            cls._config_mtime = current_mtime
            
            with open(config_path, "r", encoding="utf-8") as f:
                cls._config = yaml.safe_load(f).get("agents", {})
        else:
            raise FileNotFoundError(f"配置文件不存在: {config_path}")
    
    @classmethod
    def create_agent(
        cls,
        agent_key: str,
        llm: Optional[BaseChatModel] = None,
        tools: Optional[List[BaseTool]] = None,
        force_reload: bool = False
    ):
        """
        根据配置创建智能体（支持缓存）
        
        Args:
            agent_key: 智能体键名（如 blood_pressure_agent）
            llm: LLM 实例（可选，如果不提供则从配置创建）
            tools: 工具列表（可选，如果不提供则从配置加载）
            force_reload: 强制重新加载（忽略缓存）
        
        Returns:
            CompiledGraph: 已编译的 LangGraph Agent 实例
        """
        if not cls._config:
            cls.load_config()
        
        # 检查缓存（如果未强制重新加载）
        if not force_reload:
            with cls._cache_lock:
                if agent_key in cls._agent_cache:
                    # 检查配置是否更新（在锁外检查，避免死锁）
                    config_updated = cls._is_config_updated()
                    if config_updated:
                        logger.info("检测到配置更新，清除Agent缓存")
                        cls._clear_cache_internal()  # 已持有锁，使用内部方法
                    else:
                        logger.debug(f"使用缓存的Agent: {agent_key}")
                        cls._cache_stats["hits"] += 1
                        return cls._agent_cache[agent_key]
        
        # 缓存未命中或强制重新加载
        cls._cache_stats["misses"] += 1
        
        # 检查配置是否更新
        if cls._is_config_updated():
            logger.info("检测到配置更新，清除Agent缓存")
            cls._clear_cache()  # 未持有锁，使用公共方法
        
        # 创建新Agent
        agent = cls._create_agent_internal(agent_key, llm, tools)
        
        # 缓存Agent
        with cls._cache_lock:
            cls._agent_cache[agent_key] = agent
            cls._cache_stats["created"] += 1
        
        logger.info(f"创建并缓存Agent: {agent_key}")
        return agent
    
    @classmethod
    def _create_agent_internal(
        cls,
        agent_key: str,
        llm: Optional[BaseChatModel] = None,
        tools: Optional[List[BaseTool]] = None
    ) -> CompiledStateGraph:
        """
        内部方法：实际创建智能体（不涉及缓存）
        
        职责：
        1. 创建 LLM 实例
        2. 加载工具列表
        3. 加载 Agent 特定占位符配置（用于运行时占位符填充）
        4. 创建 ReAct Agent 实例（不传入 prompt，由运行时动态注入系统消息）
        
        Args:
            agent_key: 智能体键名
            llm: LLM 实例（可选）
            tools: 工具列表（可选）
        
        Returns:
            CompiledStateGraph: 已编译的 LangGraph Agent 实例
        """
        
        agent_config = cls._config.get(agent_key)
        if not agent_config:
            raise ValueError(f"智能体配置不存在: {agent_key}")
        
        # 1. 获取 LLM 实例
        if not llm:
            llm_config = agent_config.get("llm", {})
            llm = get_llm(
                model=llm_config.get("model", settings.LLM_MODEL),
                temperature=llm_config.get(
                    "temperature",
                    settings.LLM_TEMPERATURE_DEFAULT
                )
            )
        
        # 2. 获取工具列表
        if not tools:
            tool_names = agent_config.get("tools", [])
            tools = [
                TOOL_REGISTRY[name]
                for name in tool_names
                if name in TOOL_REGISTRY
            ]
        
        # 3. 加载Agent特定占位符配置（用于运行时占位符填充）
        # 注意：这里只加载配置，不加载提示词模板
        # 提示词模板将在运行时（domain/router/graph.py:with_user_context）通过
        # AgentTemplateLoader 统一加载
        PlaceholderManager.load_agent_placeholders(agent_key, agent_config)
        
        # 4. 创建 ReAct Agent（不传入 prompt，由运行时动态注入系统消息）
        # 原因：
        # 1. 避免 create_agent 自动添加系统消息，导致运行时系统消息重复
        # 2. 系统消息将在运行时（domain/router/graph.py:with_user_context）动态注入
        # 3. 这样可以确保系统消息包含完整的上下文信息（已填充所有占位符）
        # 4. 提示词模板加载统一由 AgentTemplateLoader 处理，避免代码重复
        return create_agent(
            model=llm,
            tools=tools,
            # 不传入 prompt 参数，避免 create_agent 自动添加系统消息
            # 系统消息将在运行时（domain/router/graph.py:with_user_context）动态注入
        )
    
    @classmethod
    def _is_config_updated(cls) -> bool:
        """
        检查配置文件是否更新
        
        Returns:
            如果配置文件已更新返回True，否则返回False
        """
        if not cls._config_path:
            return False
        
        # 支持相对路径和绝对路径
        if not os.path.isabs(cls._config_path):
            config_path = os.path.join(os.getcwd(), cls._config_path)
        else:
            config_path = cls._config_path
        
        if not os.path.exists(config_path):
            return False
        
        current_mtime = os.path.getmtime(config_path)
        if cls._config_mtime is None:
            cls._config_mtime = current_mtime
            return False
        
        if current_mtime > cls._config_mtime:
            cls._config_mtime = current_mtime
            return True
        
        return False
    
    @classmethod
    def _clear_cache_internal(cls):
        """
        清除Agent缓存（内部方法，不获取锁，调用者必须已持有锁）
        """
        count = len(cls._agent_cache)
        cls._agent_cache.clear()
        cls._cache_stats["cleared"] += 1
        logger.info(f"已清除Agent缓存, 清除项数: {count}")
    
    @classmethod
    def _clear_cache(cls):
        """
        清除Agent缓存（内部方法，线程安全）
        """
        with cls._cache_lock:
            cls._clear_cache_internal()
    
    @classmethod
    def clear_cache(cls, agent_key: Optional[str] = None):
        """
        清除Agent缓存
        
        Args:
            agent_key: Agent键名（可选，如果提供则只清除该Agent的缓存，否则清除所有缓存）
        """
        with cls._cache_lock:
            if agent_key:
                if agent_key in cls._agent_cache:
                    del cls._agent_cache[agent_key]
                    cls._cache_stats["cleared"] += 1
                    logger.info(f"已清除Agent缓存: {agent_key}")
                else:
                    logger.debug(f"Agent缓存中不存在: {agent_key}")
            else:
                count = len(cls._agent_cache)
                cls._agent_cache.clear()
                cls._cache_stats["cleared"] += 1
                logger.info(f"已清除所有Agent缓存, 清除项数: {count}")
    
    @classmethod
    def reload_agent(cls, agent_key: str) -> CompiledStateGraph:
        """
        重新加载Agent（热更新）
        
        Args:
            agent_key: Agent键名
        
        Returns:
            CompiledStateGraph: 重新加载后的Agent实例
        
        Raises:
            ValueError: Agent配置不存在
        """
        logger.info(f"重新加载Agent: {agent_key}")
        
        # 清除该Agent的缓存
        cls.clear_cache(agent_key)
        
        # 重新创建Agent
        agent = cls.create_agent(agent_key, force_reload=True)
        
        with cls._cache_lock:
            cls._cache_stats["reloaded"] += 1
        
        logger.info(f"Agent重新加载完成: {agent_key}")
        return agent
    
    @classmethod
    def reload_all_agents(cls):
        """
        重新加载所有Agent（热更新）
        
        Returns:
            Dict[str, CompiledStateGraph]: 重新加载后的Agent字典
        """
        logger.info("重新加载所有Agent")
        
        # 清除所有缓存
        cls.clear_cache()
        
        # 重新加载配置
        cls.load_config()
        
        # 重新创建所有Agent
        agents = {}
        for agent_key in cls.list_agents():
            agents[agent_key] = cls.create_agent(agent_key, force_reload=True)
        
        with cls._cache_lock:
            cls._cache_stats["reloaded"] += len(agents)
        
        logger.info(f"所有Agent重新加载完成, 共 {len(agents)} 个Agent")
        return agents
    
    @classmethod
    def get_cache_stats(cls) -> Dict[str, Any]:
        """
        获取缓存统计信息
        
        Returns:
            缓存统计字典
        """
        with cls._cache_lock:
            stats = cls._cache_stats.copy()
            stats["cache_size"] = len(cls._agent_cache)
            stats["cached_agents"] = list(cls._agent_cache.keys())
            stats["hit_rate"] = (
                stats["hits"] / (stats["hits"] + stats["misses"])
                if (stats["hits"] + stats["misses"]) > 0
                else 0.0
            )
        return stats
    
    @classmethod
    def is_cached(cls, agent_key: str) -> bool:
        """
        检查Agent是否已缓存
        
        Args:
            agent_key: Agent键名
        
        Returns:
            如果已缓存返回True，否则返回False
        """
        with cls._cache_lock:
            return agent_key in cls._agent_cache
    
    @classmethod
    def list_agents(cls) -> List[str]:
        """
        列出所有可用的智能体
        
        Returns:
            智能体键名列表
        """
        if not cls._config:
            cls.load_config()
        return list(cls._config.keys())

# 模块加载时自动读取配置（如果配置文件存在）
try:
    AgentFactory.load_config()
except FileNotFoundError:
    # 配置文件不存在时，使用空配置（后续会通过配置创建）
    pass

