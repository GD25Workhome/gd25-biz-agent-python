"""
数据加载器单元测试
"""
import pytest
import tempfile
import os
from pathlib import Path

from infrastructure.prompts.data_loaders import (
    ConfigLoader,
    FileLoader,
    DynamicLoader,
    DatabaseLoader
)


class TestConfigLoader:
    """测试ConfigLoader"""
    
    def test_supports_config_path(self):
        """测试支持config/路径"""
        loader = ConfigLoader()
        assert loader.supports("config/prompts/test.txt")
        assert loader.supports("config/test.yaml")
        assert loader.supports("config/test.json")
        # ConfigLoader只支持config/开头的路径，不支持单独的文件名
        assert not loader.supports("test.txt")
        assert not loader.supports("http://example.com")
    
    def test_load_file(self):
        """测试加载文件"""
        loader = ConfigLoader()
        
        # 创建临时文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
            test_content = "这是测试内容"
            f.write(test_content)
            temp_path = f.name
        
        try:
            content = loader.load(temp_path)
            assert content == test_content
        finally:
            os.unlink(temp_path)
    
    def test_load_nonexistent_file(self):
        """测试加载不存在的文件"""
        loader = ConfigLoader()
        with pytest.raises(FileNotFoundError):
            loader.load("nonexistent_file.txt")


class TestFileLoader:
    """测试FileLoader"""
    
    def test_supports_file_path(self):
        """测试支持文件路径"""
        loader = FileLoader()
        assert loader.supports("path/to/file.txt")
        assert loader.supports("C:\\path\\to\\file.txt")
        assert not loader.supports("http://example.com")
        assert not loader.supports("database://test")
        assert not loader.supports("runtime")
    
    def test_load_file(self):
        """测试加载文件"""
        loader = FileLoader()
        
        # 创建临时文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
            test_content = "这是测试内容"
            f.write(test_content)
            temp_path = f.name
        
        try:
            content = loader.load(temp_path)
            assert content == test_content
        finally:
            os.unlink(temp_path)


class TestDynamicLoader:
    """测试DynamicLoader"""
    
    def test_supports_runtime(self):
        """测试支持runtime"""
        loader = DynamicLoader()
        assert loader.supports("runtime")
        assert not loader.supports("config/test.txt")
    
    def test_load_with_user_id(self):
        """测试加载用户ID"""
        loader = DynamicLoader()
        context = {"user_id": "user123"}
        content = loader.load("runtime", context)
        assert "user123" in content
        assert "系统提供的用户ID" in content
    
    def test_load_with_form_context(self):
        """测试加载表单上下文"""
        loader = DynamicLoader()
        context = {
            "user_id": "user123",
            "collected_fields": "收缩压=120；舒张压=80",
            "missing_fields": "无"
        }
        content = loader.load("runtime", context)
        assert "user123" in content
        assert "已收集字段" in content
        assert "待补全字段" in content
    
    def test_load_without_context(self):
        """测试无上下文加载"""
        loader = DynamicLoader()
        content = loader.load("runtime", None)
        assert content == ""


class TestDatabaseLoader:
    """测试DatabaseLoader"""
    
    def test_supports_database_uri(self):
        """测试支持database://URI"""
        loader = DatabaseLoader()
        assert loader.supports("database://prompts/test")
        assert not loader.supports("config/test.txt")
    
    def test_load_not_implemented(self):
        """测试加载未实现"""
        loader = DatabaseLoader()
        with pytest.raises(NotImplementedError):
            loader.load("database://prompts/test")
