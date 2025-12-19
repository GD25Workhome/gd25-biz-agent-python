"""
模板加载器
负责加载和解析提示词模板配置文件
"""
import yaml
from pathlib import Path
from typing import Dict, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class PromptModule:
    """提示词模块"""
    name: str
    type: str  # required, optional, business
    loader: str  # config, file, dynamic, database
    source: str
    enabled: bool = True
    condition: Optional[str] = None
    template: Optional[str] = None


@dataclass
class PromptTemplate:
    """提示词模板"""
    agent_key: str
    version: str
    modules: Dict[str, PromptModule]
    composition: Dict


class TemplateLoader:
    """模板加载器"""
    
    def __init__(self, templates_dir: str = "config/prompts/templates"):
        """
        初始化模板加载器
        
        Args:
            templates_dir: 模板文件目录
        """
        self.templates_dir = Path(templates_dir)
        # 如果目录不存在，尝试从项目根目录查找
        if not self.templates_dir.exists():
            root_templates_dir = Path.cwd() / templates_dir
            if root_templates_dir.exists():
                self.templates_dir = root_templates_dir
            else:
                logger.warning(f"模板目录不存在: {templates_dir}，将尝试创建")
                self.templates_dir.mkdir(parents=True, exist_ok=True)
    
    def load(self, agent_key: str) -> PromptTemplate:
        """
        加载模板配置
        
        Args:
            agent_key: Agent键名（如 blood_pressure_agent）
        
        Returns:
            PromptTemplate对象
        
        Raises:
            FileNotFoundError: 模板文件不存在
            ValueError: 模板格式错误
        """
        template_file = self.templates_dir / f"{agent_key}.yaml"
        
        if not template_file.exists():
            raise FileNotFoundError(f"模板文件不存在: {template_file}")
        
        try:
            with open(template_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            
            if not data:
                raise ValueError(f"模板文件为空: {template_file}")
            
            # 验证必需字段
            if "agent_key" not in data:
                raise ValueError(f"模板文件缺少 agent_key 字段: {template_file}")
            
            # 解析模块
            modules = {}
            for name, module_data in data.get("modules", {}).items():
                if not isinstance(module_data, dict):
                    logger.warning(f"模块 {name} 配置格式错误，跳过")
                    continue
                
                modules[name] = PromptModule(
                    name=name,
                    type=module_data.get("type", "business"),
                    loader=module_data.get("loader", "config"),
                    source=module_data.get("source", ""),
                    enabled=module_data.get("enabled", True),
                    condition=module_data.get("condition"),
                    template=module_data.get("template")
                )
            
            template = PromptTemplate(
                agent_key=data["agent_key"],
                version=data.get("version", "1.0.0"),
                modules=modules,
                composition=data.get("composition", {})
            )
            
            logger.info(f"成功加载模板: {agent_key}, 版本: {template.version}, 模块数: {len(modules)}")
            return template
            
        except yaml.YAMLError as e:
            logger.error(f"YAML解析失败: {template_file}, 错误: {str(e)}")
            raise ValueError(f"模板文件格式错误: {template_file}, 错误: {str(e)}")
        except Exception as e:
            logger.error(f"加载模板失败: {template_file}, 错误: {str(e)}")
            raise
