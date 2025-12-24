"""
测试代码：从 Langfuse 读取所有模版的最新版本并存储到本地

功能：
1. 连接到 Langfuse 服务
2. 获取所有提示词模版的最新版本
3. 将模版内容保存到 config/prompts/local 目录
"""
import sys
from pathlib import Path
from typing import List, Dict, Optional
import logging

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from app.core.config import settings

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 延迟导入 Langfuse，避免在未安装时出错
try:
    from langfuse import Langfuse
    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False
    logger.error("Langfuse 未安装，请安装: pip install langfuse")


def get_template_names_from_config() -> List[str]:
    """
    从配置文件中获取所有模版名称
    
    Returns:
        模版名称列表
    """
    template_names = set()
    
    # 从 agents.yaml 获取 Agent 模版名称
    try:
        from domain.agents.factory import AgentFactory
        AgentFactory.load_config()
        config = AgentFactory._config
        
        for agent_config in config.values():
            if "langfuse_template" in agent_config:
                template_names.add(agent_config["langfuse_template"])
        
        logger.info(f"从 agents.yaml 获取到 {len(template_names)} 个 Agent 模版名称")
    except Exception as e:
        logger.warning(f"从 agents.yaml 获取模版名称失败: {e}")
    
    # 添加路由工具的模版名称（这些在代码中直接使用）
    router_templates = [
        "router_intent_identification_prompt",
        "router_clarify_intent_prompt",
    ]
    template_names.update(router_templates)
    
    logger.info(f"总共获取到 {len(template_names)} 个模版名称: {sorted(template_names)}")
    return sorted(list(template_names))


def save_template_to_local(template_name: str, content: str, output_dir: Path) -> Path:
    """
    将模版内容保存到本地文件
    
    Args:
        template_name: 模版名称
        content: 模版内容
        output_dir: 输出目录
        
    Returns:
        保存的文件路径
    """
    # 确保输出目录存在
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 构建文件路径（使用 .txt 扩展名）
    # 清理模版名称，移除可能的不合法字符
    safe_name = template_name.replace("/", "_").replace("\\", "_")
    file_path = output_dir / f"{safe_name}.txt"
    
    # 写入文件
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    
    logger.info(f"已保存模版到: {file_path}")
    return file_path


def fetch_all_templates_to_local(output_dir: Optional[Path] = None) -> Dict[str, Path]:
    """
    从 Langfuse 获取所有模版的最新版本并保存到本地
    
    Args:
        output_dir: 输出目录，默认为 config/prompts/local
        
    Returns:
        字典，key 为模版名称，value 为保存的文件路径
    """
    # 确定输出目录
    if output_dir is None:
        project_root = Path(__file__).parent.parent.parent
        output_dir = project_root / "config" / "prompts" / "local"
    
    logger.info(f"开始从 Langfuse 获取所有模版并保存到: {output_dir}")
    
    # 检查 Langfuse 是否可用
    if not LANGFUSE_AVAILABLE:
        raise ImportError("Langfuse 未安装，请安装: pip install langfuse")
    
    # 检查 Langfuse 配置
    if not settings.LANGFUSE_ENABLED:
        raise ValueError("Langfuse 未启用，请设置 LANGFUSE_ENABLED=True")
    
    if not settings.LANGFUSE_PUBLIC_KEY or not settings.LANGFUSE_SECRET_KEY:
        raise ValueError("Langfuse 配置不完整，请设置 LANGFUSE_PUBLIC_KEY 和 LANGFUSE_SECRET_KEY")
    
    # 从配置文件获取模版名称列表
    template_names = get_template_names_from_config()
    
    if not template_names:
        logger.warning("未找到任何模版名称，请检查配置文件")
        return {}
    
    # 使用 LangfusePromptAdapter 获取每个模版的最新版本
    from infrastructure.prompts.langfuse_adapter import LangfusePromptAdapter
    
    adapter = LangfusePromptAdapter()
    saved_files = {}
    
    for template_name in template_names:
        try:
            logger.info(f"正在获取模版: {template_name}")
            # 获取最新版本（version=None 表示使用最新版本）
            content = adapter.get_template(template_name, version=None)
            
            if not content:
                logger.warning(f"模版 {template_name} 内容为空，跳过保存")
                continue
            
            # 保存到本地
            file_path = save_template_to_local(template_name, content, output_dir)
            saved_files[template_name] = file_path
            
        except Exception as e:
            logger.error(f"获取模版 {template_name} 失败: {e}")
            continue
    
    logger.info(f"成功保存 {len(saved_files)}/{len(template_names)} 个模版到本地")
    return saved_files


def main():
    """主函数"""
    try:
        # 检查配置
        if not settings.LANGFUSE_ENABLED:
            logger.error("Langfuse 未启用，请设置 LANGFUSE_ENABLED=True")
            return
        
        if not settings.LANGFUSE_PUBLIC_KEY or not settings.LANGFUSE_SECRET_KEY:
            logger.error("Langfuse 配置不完整，请设置 LANGFUSE_PUBLIC_KEY 和 LANGFUSE_SECRET_KEY")
            return
        
        # 获取并保存所有模版
        saved_files = fetch_all_templates_to_local()
        
        # 打印结果
        print("\n" + "="*60)
        print("模版获取和保存结果")
        print("="*60)
        print(f"成功保存 {len(saved_files)} 个模版:")
        for template_name, file_path in saved_files.items():
            print(f"  - {template_name} -> {file_path}")
        print("="*60)
        
    except Exception as e:
        logger.error(f"执行失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

