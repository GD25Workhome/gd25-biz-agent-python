"""
Langfuse诊断工具
用于检查Langfuse配置和连接状态

运行命令：
    pytest cursor_test/test_langfuse_diagnosis.py -v -s
    或
    python -m pytest cursor_test/test_langfuse_diagnosis.py::test_langfuse_config -v -s
"""
import pytest
from backend.app.config import settings
from backend.infrastructure.observability.langfuse_handler import (
    get_langfuse_client,
    is_langfuse_available,
    set_langfuse_trace_context,
    create_langfuse_handler,
)


def test_langfuse_config():
    """检查Langfuse配置（从统一配置模块读取）"""
    print("\n=== Langfuse配置检查 ===")
    print("（配置来源：backend/app/config.py -> .env文件）")
    
    langfuse_enabled = settings.LANGFUSE_ENABLED
    public_key = settings.LANGFUSE_PUBLIC_KEY
    secret_key = settings.LANGFUSE_SECRET_KEY
    host = settings.LANGFUSE_HOST
    
    print(f"LANGFUSE_ENABLED: {langfuse_enabled}")
    print(f"LANGFUSE_PUBLIC_KEY: {'SET' if public_key else 'NOT SET'} ({public_key[:8] + '...' if public_key else 'None'})")
    print(f"LANGFUSE_SECRET_KEY: {'SET' if secret_key else 'NOT SET'} ({secret_key[:8] + '...' if secret_key else 'None'})")
    print(f"LANGFUSE_HOST: {host or 'NOT SET (will use default)'}")
    
    # 检查可用性
    available = is_langfuse_available()
    print(f"\nLangfuse可用性: {available}")
    
    if not available:
        print("\n❌ Langfuse不可用，可能的原因：")
        if not langfuse_enabled:
            print("  - LANGFUSE_ENABLED未设置为true")
        if not public_key:
            print("  - LANGFUSE_PUBLIC_KEY未设置")
        if not secret_key:
            print("  - LANGFUSE_SECRET_KEY未设置")
    else:
        print("\n✅ Langfuse配置正确")
    
    return available


def test_langfuse_client():
    """测试Langfuse客户端创建"""
    print("\n=== Langfuse客户端测试 ===")
    
    client = get_langfuse_client()
    if client:
        print("✅ Langfuse客户端创建成功")
        print(f"   Client类型: {type(client)}")
    else:
        print("❌ Langfuse客户端创建失败")
    
    return client is not None


def test_langfuse_trace():
    """测试Trace创建"""
    print("\n=== Langfuse Trace测试 ===")
    
    trace_id = set_langfuse_trace_context(
        name="diagnosis_test",
        user_id="test_user",
        session_id="test_session",
        metadata={"test": "diagnosis"}
    )
    
    if trace_id:
        print(f"✅ Trace创建成功: trace_id={trace_id}")
    else:
        print("❌ Trace创建失败")
    
    return trace_id


def test_langfuse_handler():
    """测试CallbackHandler创建"""
    print("\n=== Langfuse CallbackHandler测试 ===")
    
    handler = create_langfuse_handler(
        context={"test": "diagnosis"}
    )
    
    if handler:
        print(f"✅ CallbackHandler创建成功: {type(handler)}")
    else:
        print("❌ CallbackHandler创建失败")
    
    return handler is not None


def test_full_diagnosis():
    """完整诊断"""
    print("\n" + "="*50)
    print("Langfuse完整诊断")
    print("="*50)
    
    # 1. 配置检查
    config_ok = test_langfuse_config()
    if not config_ok:
        print("\n⚠️  配置检查失败，停止后续测试")
        return
    
    # 2. 客户端测试
    client_ok = test_langfuse_client()
    if not client_ok:
        print("\n⚠️  客户端创建失败，停止后续测试")
        return
    
    # 3. Trace测试
    trace_ok = test_langfuse_trace()
    
    # 4. Handler测试
    handler_ok = test_langfuse_handler()
    
    # 总结
    print("\n" + "="*50)
    print("诊断总结")
    print("="*50)
    print(f"配置检查: {'✅' if config_ok else '❌'}")
    print(f"客户端创建: {'✅' if client_ok else '❌'}")
    print(f"Trace创建: {'✅' if trace_ok else '❌'}")
    print(f"Handler创建: {'✅' if handler_ok else '❌'}")
    
    if all([config_ok, client_ok, trace_ok, handler_ok]):
        print("\n✅ 所有检查通过，Langfuse应该可以正常工作")
    else:
        print("\n❌ 部分检查失败，请检查配置和日志")


if __name__ == "__main__":
    test_full_diagnosis()

