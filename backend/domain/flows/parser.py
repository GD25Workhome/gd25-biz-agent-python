"""
流程YAML解析器
负责解析YAML格式的流程配置文件
"""
import logging
from pathlib import Path
from typing import Dict, Any
import yaml

from backend.domain.flows.definition import FlowDefinition, NodeDefinition, EdgeDefinition

logger = logging.getLogger(__name__)


class FlowParser:
    """流程解析器"""
    
    @staticmethod
    def parse_yaml(yaml_path: Path) -> FlowDefinition:
        """
        解析YAML格式的流程配置文件
        
        Args:
            yaml_path: YAML文件路径
            
        Returns:
            FlowDefinition: 流程定义对象
            
        Raises:
            FileNotFoundError: 文件不存在
            ValueError: 文件格式错误
        """
        if not yaml_path.exists():
            raise FileNotFoundError(f"流程配置文件不存在: {yaml_path}")
        
        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            
            if not data:
                raise ValueError("YAML文件内容为空")
            
            # 获取流程目录（用于解析相对路径）
            flow_dir = str(yaml_path.parent)
            
            # 解析流程定义
            flow_def = FlowDefinition(
                name=data.get("name", ""),
                version=data.get("version", "1.0"),
                description=data.get("description"),
                nodes=[NodeDefinition(**node) for node in data.get("nodes", [])],
                edges=[EdgeDefinition(**edge) for edge in data.get("edges", [])],
                entry_node=data.get("entry_node", ""),
                flow_dir=flow_dir
            )
            
            logger.info(f"成功解析流程配置文件: {yaml_path} (流程名称: {flow_def.name})")
            return flow_def
            
        except yaml.YAMLError as e:
            raise ValueError(f"YAML文件格式错误: {e}")
        except Exception as e:
            raise ValueError(f"解析流程配置文件失败: {e}")
    
    @staticmethod
    def scan_flows_directory(flows_dir: Path) -> Dict[str, FlowDefinition]:
        """
        扫描流程目录，解析所有流程定义
        
        Args:
            flows_dir: 流程目录路径
            
        Returns:
            Dict[str, FlowDefinition]: 流程定义字典（key为流程名称）
        """
        flows = {}
        
        if not flows_dir.exists():
            logger.warning(f"流程目录不存在: {flows_dir}")
            return flows
        
        # 扫描所有流程目录
        for flow_dir in flows_dir.iterdir():
            if not flow_dir.is_dir():
                continue
            
            flow_yaml = flow_dir / "flow.yaml"
            if not flow_yaml.exists():
                logger.warning(f"流程目录 {flow_dir} 中没有 flow.yaml 文件，跳过")
                continue
            
            try:
                flow_def = FlowParser.parse_yaml(flow_yaml)
                flows[flow_def.name] = flow_def
                logger.info(f"扫描到流程: {flow_def.name} (版本: {flow_def.version})")
            except Exception as e:
                logger.error(f"解析流程 {flow_dir} 失败: {e}")
                continue
        
        return flows

