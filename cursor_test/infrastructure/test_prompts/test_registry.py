"""
加载器注册表单元测试
"""
import pytest
from infrastructure.prompts.registry import LoaderRegistry
from infrastructure.prompts.data_loaders import (
    ConfigLoader,
    FileLoader,
    DynamicLoader,
    DatabaseLoader
)


class TestLoaderRegistry:
    """测试LoaderRegistry"""
    
    def test_get_loader_config(self):
        """测试获取ConfigLoader"""
        loader = LoaderRegistry.get_loader("config/prompts/test.txt")
        assert loader is not None
        assert isinstance(loader, ConfigLoader)
        
        # 测试普通文件路径应该使用FileLoader
        loader2 = LoaderRegistry.get_loader("path/to/file.txt")
        assert loader2 is not None
        assert isinstance(loader2, FileLoader)
    
    def test_get_loader_dynamic(self):
        """测试获取DynamicLoader"""
        loader = LoaderRegistry.get_loader("runtime")
        assert loader is not None
        assert isinstance(loader, DynamicLoader)
    
    def test_get_loader_database(self):
        """测试获取DatabaseLoader"""
        loader = LoaderRegistry.get_loader("database://prompts/test")
        assert loader is not None
        assert isinstance(loader, DatabaseLoader)
    
    def test_get_loader_file(self):
        """测试获取FileLoader"""
        loader = LoaderRegistry.get_loader("path/to/file.txt")
        assert loader is not None
        assert isinstance(loader, FileLoader)
    
    def test_get_loader_not_found(self):
        """测试获取不支持的加载器"""
        loader = LoaderRegistry.get_loader("http://example.com")
        assert loader is None
    
    def test_get_loader_by_name(self):
        """测试根据名称获取加载器"""
        loader = LoaderRegistry.get_loader_by_name("config")
        assert loader is not None
        assert isinstance(loader, ConfigLoader)
        
        loader = LoaderRegistry.get_loader_by_name("nonexistent")
        assert loader is None
    
    def test_register_custom_loader(self):
        """测试注册自定义加载器"""
        from infrastructure.prompts.data_loaders import DataLoader
        
        class CustomLoader(DataLoader):
            def load(self, source, context=None):
                return "custom"
            
            def supports(self, source):
                return source.startswith("custom://")
        
        # 注册自定义加载器
        # FileLoader不会匹配custom://开头的路径（因为FileLoader检查了特殊协议）
        LoaderRegistry.register("custom", CustomLoader())
        loader = LoaderRegistry.get_loader("custom://test")
        assert loader is not None
        # 验证是CustomLoader
        assert isinstance(loader, CustomLoader), f"Expected CustomLoader, got {type(loader).__name__}"
