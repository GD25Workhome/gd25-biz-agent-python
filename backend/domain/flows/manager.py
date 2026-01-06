"""
流程管理器
负责流程的加载、缓存和管理
"""
import logging
from pathlib import Path
from typing import Dict, Optional, List, Any
import yaml
from langgraph.checkpoint.memory import MemorySaver

# LangGraph编译后的图类型（使用Any作为类型占位符）
CompiledGraph = Any

from backend.domain.flows.definition import FlowDefinition
from backend.domain.flows.parser import FlowParser
from backend.domain.flows.builder import GraphBuilder
from backend.app.config import find_project_root

logger = logging.getLogger(__name__)


class FlowManager:
    """流程管理器"""
    
    _flow_definitions: Dict[str, FlowDefinition] = {}  # 流程定义缓存
    _compiled_graphs: Dict[str, CompiledGraph] = {}  # 编译后的图缓存
    _flows_dir: Optional[Path] = None
    
    @classmethod
    def _get_flows_dir(cls) -> Path:
        """
        获取流程目录路径
        
        Returns:
            Path: 流程目录路径
        """
        if cls._flows_dir is None:
            project_root = find_project_root()
            cls._flows_dir = project_root / "config" / "flows"
        return cls._flows_dir
    
    @classmethod
    def scan_flows(cls) -> Dict[str, FlowDefinition]:
        """
        扫描流程文件，解析流程定义（不构建图）
        
        Returns:
            Dict[str, FlowDefinition]: 流程定义字典（key为流程名称）
        """
        flows_dir = cls._get_flows_dir()
        flows = FlowParser.scan_flows_directory(flows_dir)
        cls._flow_definitions.update(flows)
        logger.info(f"扫描到 {len(flows)} 个流程定义")
        return flows
    
    @classmethod
    def preload_flows(cls, flow_names: List[str]) -> None:
        """
        预加载指定流程（构建和编译图）
        
        Args:
            flow_names: 流程名称列表
        """
        for flow_name in flow_names:
            if flow_name in cls._compiled_graphs:
                logger.info(f"流程 {flow_name} 已加载，跳过")
                continue
            
            if flow_name not in cls._flow_definitions:
                logger.warning(f"流程定义 {flow_name} 不存在，跳过")
                continue
            
            try:
                cls._load_and_compile_flow(flow_name)
                logger.info(f"成功预加载流程: {flow_name}")
            except Exception as e:
                logger.error(f"预加载流程 {flow_name} 失败: {e}")
    
    @classmethod
    def get_flow(cls, flow_name: str) -> CompiledGraph:
        """
        获取流程图（按需加载）
        
        Args:
            flow_name: 流程名称
            
        Returns:
            CompiledGraph: 编译后的图
            
        Raises:
            ValueError: 流程不存在或加载失败
        """
        # 如果已编译，直接返回
        if flow_name in cls._compiled_graphs:
            return cls._compiled_graphs[flow_name]
        
        # 如果流程定义不存在，先扫描
        if flow_name not in cls._flow_definitions:
            cls.scan_flows()
        
        # 如果仍然不存在，报错
        if flow_name not in cls._flow_definitions:
            raise ValueError(f"流程定义不存在: {flow_name}")
        
        # 加载并编译流程
        cls._load_and_compile_flow(flow_name)
        
        return cls._compiled_graphs[flow_name]
    
    @classmethod
    def _load_and_compile_flow(cls, flow_name: str) -> None:
        """
        加载并编译流程
        
        Args:
            flow_name: 流程名称
        """
        flow_def = cls._flow_definitions[flow_name]
        
        # 构建图
        graph = GraphBuilder.build_graph(flow_def)
        
        # 编译图（使用内存检查点保存器）
        checkpoint = MemorySaver()
        compiled_graph = graph.compile(checkpointer=checkpoint)
        
        # 缓存编译后的图
        cls._compiled_graphs[flow_name] = compiled_graph
        logger.info(f"成功编译流程: {flow_name}")
    
    @classmethod
    def get_flow_loader_config(cls) -> Dict[str, List[str]]:
        """
        获取流程加载配置
        
        Returns:
            Dict[str, List[str]]: 流程加载配置（preload和lazy_load列表）
        """
        project_root = find_project_root()
        config_path = project_root / "config" / "flow_loader.yaml"
        
        if not config_path.exists():
            logger.warning(f"流程加载配置文件不存在: {config_path}，使用默认配置")
            return {
                "preload": [],
                "lazy_load": []
            }
        
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            
            return {
                "preload": config.get("flows", {}).get("preload", []),
                "lazy_load": config.get("flows", {}).get("lazy_load", [])
            }
        except Exception as e:
            logger.error(f"读取流程加载配置失败: {e}，使用默认配置")
            return {
                "preload": [],
                "lazy_load": []
            }

