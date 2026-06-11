"""
上下文缓存加载器

从数据库将 Token / Session 缓存恢复到内存 ContextManager。
"""
import logging

from backend.domain.context.context_manager import get_context_manager
from backend.domain.context.user_info import UserInfo
from backend.infrastructure.database.connection import get_session_factory
from backend.infrastructure.database.repository.session_cache_repository import (
    SessionCacheRepository,
)
from backend.infrastructure.database.repository.token_cache_repository import (
    TokenCacheRepository,
)

logger = logging.getLogger(__name__)

# 启动时单次加载上限
_CACHE_LOAD_LIMIT = 10000


async def load_context_cache() -> None:
    """
    从数据库加载 Token 和 Session 缓存到 ContextManager。

    服务重启后恢复内存缓存，加载失败不阻断启动。
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            context_manager = get_context_manager()

            token_repo = TokenCacheRepository(session)
            token_records = await token_repo.get_all(limit=_CACHE_LOAD_LIMIT)

            for token_record in token_records:
                token_id = token_record.id
                user_info = UserInfo(user_id=token_id)
                if token_record.data_info:
                    user_info.update(token_record.data_info)
                context_manager.restore_token_context(token_id, user_info)

            logger.info("   ✓ 加载了 %s 个Token缓存", len(token_records))

            session_repo = SessionCacheRepository(session)
            session_records = await session_repo.get_all(limit=_CACHE_LOAD_LIMIT)

            for session_record in session_records:
                context_manager.restore_session_context(
                    session_record.id,
                    session_record.data_info,
                )

            logger.info("   ✓ 加载了 %s 个Session缓存", len(session_records))

        except Exception as e:
            logger.error("加载缓存失败: %s", e, exc_info=True)
