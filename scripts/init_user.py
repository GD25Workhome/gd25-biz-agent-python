#!/usr/bin/env python
"""
用户初始化脚本

功能：
- 从 Markdown 文档中解析用户数据
- 根据 username 查询用户，存在则更新 user_info，不存在则创建新用户

使用方式：
    python scripts/init_user.py
    python scripts/init_user.py --file doc/设计V6.0/V6.1\ 提示词升级/0201-测试用例数据枚举.md
"""

import argparse
import sys
import os
import re
from typing import List, Dict, Optional
from datetime import datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from infrastructure.database.models.user import User


def ensure_psycopg3_sync_url(database_url: str) -> str:
    """
    确保数据库 URL 使用 psycopg3 驱动（同步模式）
    
    Args:
        database_url: 原始数据库 URL
        
    Returns:
        str: 确保使用 psycopg3 驱动的 URL
    """
    if database_url.startswith("postgresql+psycopg://"):
        return database_url
    
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    
    if "+" in database_url and "://" in database_url:
        scheme, rest = database_url.split("://", 1)
        if scheme.startswith("postgresql+"):
            return f"postgresql+psycopg://{rest}"
    
    return database_url


def parse_markdown_file(file_path: str) -> List[Dict[str, str]]:
    """
    解析 Markdown 文件，提取用户数据
    
    Args:
        file_path: Markdown 文件路径
        
    Returns:
        List[Dict[str, str]]: 用户数据列表，每个字典包含 username 和 user_info
    """
    users = []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 找到 "## 1. 用户例子" 部分，到 "## 2." 之前
    pattern = r'## 1\. 用户例子(.*?)(?=## 2\.)'
    match = re.search(pattern, content, re.DOTALL)
    
    if not match:
        print("✗ 未找到 '## 1. 用户例子' 部分")
        return users
    
    section_content = match.group(1)
    
    # 匹配每个用户块：从 #### username 开始，到下一个 #### 或文件结束
    # 用户块格式：
    # #### user_xxx
    # 
    # **username**: user_xxx
    # 
    # **user_info**:
    # ```
    # ...内容...
    # ```
    
    # 使用正则表达式匹配用户块
    # 匹配格式：
    # #### user_xxx（可能有中文说明）
    # 
    # **username**: user_xxx
    # 
    # **user_info**:
    # ```
    # ...内容...
    # ```
    # 注意：使用非贪婪匹配 (.*?) 来匹配代码块内容，直到遇到 ```
    # 代码块可能紧跟在 **user_info**: 后面，也可能有空行
    user_pattern = r'####\s+[^\n]+\s*\n\s*\*\*username\*\*:\s*(\S+)\s*\n\s*\*\*user_info\*\*:\s*\n```\s*\n?(.*?)```'
    matches = re.finditer(user_pattern, section_content, re.DOTALL | re.MULTILINE)
    
    for match in matches:
        username = match.group(1).strip()
        user_info = match.group(2).strip()
        
        users.append({
            'username': username,
            'user_info': user_info
        })
    
    return users


def init_users(users: List[Dict[str, str]], database_url: str) -> None:
    """
    初始化用户数据到数据库
    
    Args:
        users: 用户数据列表
        database_url: 数据库连接 URL
    """
    # 确保使用 psycopg3 驱动
    sync_url = ensure_psycopg3_sync_url(database_url)
    engine = create_engine(sync_url)
    
    created_count = 0
    updated_count = 0
    error_count = 0
    
    with Session(engine) as session:
        for user_data in users:
            username = user_data['username']
            user_info = user_data['user_info']
            
            try:
                # 查询用户是否存在
                result = session.execute(
                    select(User).where(User.username == username)
                )
                user = result.scalar_one_or_none()
                
                if user:
                    # 用户存在，更新 user_info
                    user.user_info = user_info
                    user.user_info_updated_at = datetime.now()
                    session.commit()
                    updated_count += 1
                    print(f"✓ 更新用户: {username}")
                else:
                    # 用户不存在，创建新用户
                    new_user = User(
                        username=username,
                        user_info=user_info,
                        is_active=True,
                        user_info_updated_at=datetime.now()
                    )
                    session.add(new_user)
                    session.commit()
                    created_count += 1
                    print(f"✓ 创建用户: {username}")
                    
            except Exception as e:
                session.rollback()
                error_count += 1
                print(f"✗ 处理用户 {username} 时出错: {e}")
    
    engine.dispose()
    
    print()
    print("=" * 60)
    print("用户初始化完成")
    print("=" * 60)
    print(f"总计: {len(users)} 个用户")
    print(f"创建: {created_count} 个")
    print(f"更新: {updated_count} 个")
    print(f"错误: {error_count} 个")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="用户初始化脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 使用默认文件路径
  python scripts/init_user.py
  
  # 指定文件路径
  python scripts/init_user.py --file doc/设计V6.0/V6.1\\ 提示词升级/0201-测试用例数据枚举.md
        """
    )
    parser.add_argument(
        "--file",
        type=str,
        default="doc/设计V6.0/V6.1 提示词升级/0201-测试用例数据枚举.md",
        help="Markdown 文件路径（默认: doc/设计V6.0/V6.1 提示词升级/0201-测试用例数据枚举.md）"
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("用户初始化脚本")
    print("=" * 60)
    print()
    
    # 获取文件路径（相对于项目根目录）
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    file_path = os.path.join(project_root, args.file)
    
    if not os.path.exists(file_path):
        print(f"✗ 文件不存在: {file_path}")
        sys.exit(1)
    
    print(f"读取文件: {file_path}")
    
    # 解析 Markdown 文件
    print("正在解析 Markdown 文件...")
    users = parse_markdown_file(file_path)
    
    if not users:
        print("✗ 未找到任何用户数据")
        sys.exit(1)
    
    print(f"✓ 解析完成，找到 {len(users)} 个用户")
    print()
    
    # 获取数据库配置
    try:
        database_url = settings.DB_URI
    except Exception as e:
        print(f"✗ 配置错误: {e}")
        print()
        print("请检查数据库配置，确保以下环境变量已设置或在 .env 文件中配置：")
        print("  DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME")
        sys.exit(1)
    
    if not database_url:
        print("✗ 数据库 URL 配置为空")
        print("请检查数据库配置")
        sys.exit(1)
    
    print("正在连接数据库...")
    print()
    
    # 初始化用户
    init_users(users, database_url)


if __name__ == "__main__":
    main()

