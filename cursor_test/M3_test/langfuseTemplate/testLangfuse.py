"""
Langfuse 提示词模版测试
测试从 Langfuse 服务器获取提示词模版

运行方式：
==========
# 直接运行测试文件
python cursor_test/M3_test/langfuseTemplate/testLangfuse.py

# 或者在项目根目录运行
python -m cursor_test.M3_test.langfuseTemplate.testLangfuse
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
test_file_path = Path(__file__).resolve()
project_root = test_file_path.parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from langfuse import Langfuse
from app.core.config import settings


def init_langfuse_client():
    """
    初始化 Langfuse 客户端
    
    Returns:
        Langfuse: Langfuse 客户端实例，如果初始化失败则返回 None
    """
    if not settings.LANGFUSE_ENABLED:
        print("警告: Langfuse 未启用，请设置 LANGFUSE_ENABLED=True")
        return None
    
    if not settings.LANGFUSE_PUBLIC_KEY or not settings.LANGFUSE_SECRET_KEY:
        print("错误: Langfuse 配置不完整，请设置 LANGFUSE_PUBLIC_KEY 和 LANGFUSE_SECRET_KEY")
        return None
    
    try:
        langfuse = Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            host=settings.LANGFUSE_HOST
        )
        print("✓ Langfuse 客户端初始化成功")
        return langfuse
    except Exception as e:
        print(f"错误: Langfuse 客户端初始化失败: {e}")
        return None


def test_get_prompt(langfuse: Langfuse, prompt_name: str = "blood_pressure_agent_prompt", version: int = 1):
    """
    测试获取提示词模版
    
    Args:
        langfuse: Langfuse 客户端实例
        prompt_name: 提示词模版名称
        version: 提示词版本号
    """
    if not langfuse:
        print("错误: Langfuse 客户端未初始化，无法测试")
        return
    
    print(f"开始测试获取提示词模版: {prompt_name} (version={version})")
    
    try:
        prompt = langfuse.get_prompt(name=prompt_name, version=version)
        print(f"✓ 成功获取提示词")
        
        # 提取提示词内容
        if hasattr(prompt, 'prompt'):
            content = prompt.prompt
        elif hasattr(prompt, 'content'):
            content = prompt.content
        elif isinstance(prompt, str):
            content = prompt
        else:
            content = str(prompt)
        
        print(f"提示词内容长度: {len(content)} 字符")
        print(f"提示词内容预览（前200字符）: {content[:200]}...")
        print(f"\n原始模板: {content}")
        
    except Exception as e:
        print(f"✗ 获取提示词失败: {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("Langfuse 提示词模版测试")
    print("=" * 60)
    
    # 初始化 Langfuse 客户端
    langfuse = init_langfuse_client()
    
    if langfuse:
        # 测试获取提示词
        test_get_prompt(langfuse, "blood_pressure_agent_prompt", version=1)
        print("=" * 60)
        print("测试完成")
    else:
        print("无法初始化 Langfuse 客户端，测试终止")
