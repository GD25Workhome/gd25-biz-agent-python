"""
系统初始化脚本
用于验证基础架构是否正确设置
"""
import sys
import logging
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def init_system():
    """初始化系统基础组件"""
    logger.info("=" * 60)
    logger.info("开始初始化系统基础组件...")
    logger.info("=" * 60)
    
    # 1. 加载配置
    logger.info("1. 加载应用配置...")
    try:
        from backend.app.config import settings, find_project_root
        project_root = find_project_root()
        logger.info(f"   ✓ 项目根目录: {project_root}")
        logger.info(f"   ✓ 默认模型: {settings.LLM_MODEL}")
        logger.info(f"   ✓ 默认温度: {settings.LLM_TEMPERATURE}")
    except Exception as e:
        logger.error(f"   ✗ 加载配置失败: {e}")
        return False
    
    # 2. 加载模型供应商配置
    logger.info("2. 加载模型供应商配置...")
    try:
        from backend.infrastructure.llm.providers.manager import ProviderManager
        config_path = project_root / "config" / "model_providers.yaml"
        
        if not config_path.exists():
            logger.warning(f"   ⚠ 配置文件不存在: {config_path}")
            logger.warning("   请创建配置文件或检查路径")
            return False
        
        ProviderManager.load_providers(config_path)
        all_providers = ProviderManager.get_all_providers()
        
        logger.info(f"   ✓ 成功加载 {len(all_providers)} 个模型供应商:")
        for provider_name, config in all_providers.items():
            logger.info(f"     - {provider_name}: {config.base_url}")
            
    except Exception as e:
        logger.error(f"   ✗ 加载供应商配置失败: {e}")
        return False
    
    # 3. 验证LLM客户端
    logger.info("3. 验证LLM客户端...")
    try:
        from backend.infrastructure.llm.client import get_llm
        
        # 尝试创建一个LLM实例（不实际调用API）
        if all_providers:
            provider_name = list(all_providers.keys())[0]
            try:
                llm = get_llm(
                    provider=provider_name,
                    model="test-model",
                    temperature=0.7
                )
                logger.info(f"   ✓ LLM客户端创建成功 (provider: {provider_name})")
            except ValueError as e:
                logger.warning(f"   ⚠ LLM客户端创建失败: {e}")
                logger.warning("   这可能是由于API密钥未设置导致的")
        else:
            logger.warning("   ⚠ 没有可用的供应商配置")
            
    except Exception as e:
        logger.error(f"   ✗ 验证LLM客户端失败: {e}")
        return False
    
    logger.info("=" * 60)
    logger.info("系统基础组件初始化完成！")
    logger.info("=" * 60)
    return True


if __name__ == "__main__":
    success = init_system()
    sys.exit(0 if success else 1)

