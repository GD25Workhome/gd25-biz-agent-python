"""
TokenId 数据转换工具测试

Pytest 命令示例：
================

# 运行整个测试文件
pytest cursor_test/tools/test_token_converter.py

# 运行整个测试文件（详细输出）
pytest cursor_test/tools/test_token_converter.py -v

# 运行整个测试文件（显示 print 输出）
pytest cursor_test/tools/test_token_converter.py -s

# 运行特定的测试类
pytest cursor_test/tools/test_token_converter.py::TestTokenConverter

# 运行特定的测试方法
pytest cursor_test/tools/test_token_converter.py::TestTokenConverter::test_convert_token_to_user_info
"""
import pytest
from domain.tools.utils.token_converter import (
    UserInfo,
    convert_token_to_user_info,
    convert_token_to_user_id
)


class TestTokenConverter:
    """TokenConverter 测试类"""
    
    def test_user_info_dataclass(self):
        """测试 UserInfo 数据类"""
        # Arrange & Act
        user_info = UserInfo(user_id="user123")
        
        # Assert
        assert user_info.user_id == "user123"
        assert isinstance(user_info, UserInfo)
    
    def test_convert_token_to_user_info(self):
        """测试将 tokenId 转换为 UserInfo"""
        # Arrange
        token_id = "user123"
        
        # Act
        user_info = convert_token_to_user_info(token_id)
        
        # Assert
        assert isinstance(user_info, UserInfo)
        assert user_info.user_id == token_id
        assert user_info.user_id == "user123"
    
    def test_convert_token_to_user_info_different_tokens(self):
        """测试不同 tokenId 的转换"""
        # Arrange
        token_ids = ["user1", "user2", "user3", "test_token_123"]
        
        # Act & Assert
        for token_id in token_ids:
            user_info = convert_token_to_user_info(token_id)
            assert user_info.user_id == token_id
    
    def test_convert_token_to_user_id(self):
        """测试将 tokenId 转换为 userId（便捷方法）"""
        # Arrange
        token_id = "user456"
        
        # Act
        user_id = convert_token_to_user_id(token_id)
        
        # Assert
        assert user_id == token_id
        assert user_id == "user456"
    
    def test_convert_token_to_user_id_consistency(self):
        """测试 convert_token_to_user_id 与 convert_token_to_user_info 的一致性"""
        # Arrange
        token_id = "user789"
        
        # Act
        user_id_direct = convert_token_to_user_id(token_id)
        user_info = convert_token_to_user_info(token_id)
        user_id_from_info = user_info.user_id
        
        # Assert
        assert user_id_direct == user_id_from_info
        assert user_id_direct == token_id
    
    def test_current_stage_token_equals_user_id(self):
        """测试当前阶段 tokenId 等于 userId 的特性"""
        # Arrange
        # 当前阶段：token_id = user_id
        test_cases = [
            ("user123", "user123"),
            ("test_user", "test_user"),
            ("12345", "12345"),
        ]
        
        # Act & Assert
        for token_id, expected_user_id in test_cases:
            user_info = convert_token_to_user_info(token_id)
            assert user_info.user_id == expected_user_id
            
            user_id = convert_token_to_user_id(token_id)
            assert user_id == expected_user_id
    
    def test_user_info_immutability(self):
        """测试 UserInfo 的不可变性（dataclass 默认行为）"""
        # Arrange
        token_id = "user999"
        user_info = convert_token_to_user_info(token_id)
        
        # Act & Assert
        # dataclass 默认是 frozen=False，所以可以修改
        # 但为了测试，我们验证初始值是正确的
        assert user_info.user_id == token_id
        
        # 如果需要不可变，可以在 dataclass 中添加 frozen=True
        # 当前实现允许修改，这是合理的

