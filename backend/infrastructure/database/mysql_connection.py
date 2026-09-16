"""
exhibition MySQL 连接与查询封装（雷达新闻知识库写链路专用）。

设计文档：exhibition `projectDocs/技术设计-260915/02-知识库的构建/01-Claude的思考.md`
          §3.1（gd25 常驻 worker 直连 MySQL 扫表抢锁）/ §3.2（写入链）

⚠️ 访问边界（硬性）
    本模块只服务 `radar_news_content_task` / `radar_company_news_document` 两张表。
    其余 exhibition 表零接触；DDL 归 exhibition Java SQL 脚本，本侧绝不执行 DDL/DCL。
    与 gd25 主库（PostgreSQL，`connection.py`）完全独立，互不影响。

依赖选择说明（为什么是同步 pymysql 而不是 aiomysql）
    gd25 主库 PG 走 psycopg 异步；但 exhibition 这条链路的**现网已验证同构参照**
    全部是「pymysql 同步连接 + 条件 UPDATE 抢锁」：
      - exhibition_py/db/repository.py  claim_one_task / claim_docs_for_pdf
      - gd25 radar_crawl/db/repository.py（巨潮线，同库同模式）
    且本链路是「一条一条领、一条一条回写」的短事务，没有高并发需求；
    pymysql 已在 `py311_GD25_base` 环境内，不引入新的驱动栈。

    代价是：pymysql 是阻塞 IO，直接放在 async worker 里会卡住事件循环。
    因此**对外只暴露 async 接口**：`run_in_thread()` = `asyncio.to_thread`，
    所有 DB 调用都丢到线程池执行，事件循环不被阻塞（Agent 兜底是异步的，必须让路）。
"""
from __future__ import annotations

import asyncio
import logging
import queue
import socket
import threading
from contextlib import contextmanager
from typing import Any, Callable, Iterator, Optional, Sequence, TypeVar

import pymysql
from pymysql.cursors import DictCursor

from backend.app.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T")

# 连接池默认上限（settings.EXHIBITION_MYSQL_POOL_SIZE 可覆盖）
_DEFAULT_POOL_SIZE = 4
# 借出连接时的探活等待（秒）；超时说明池被占满，属于异常态
_BORROW_TIMEOUT_SECONDS = 30.0


class ExhibitionMysqlError(RuntimeError):
    """exhibition MySQL 连接/查询异常（业务层按失败处理，不抛出原始 pymysql 异常）。"""


class _ConnectionPool:
    """
    pymysql 连接池（极简实现）。

    - `queue.LifoQueue` 缓存空闲连接，后进先出，天然带并发上限；
    - 借出时 `ping(reconnect=True)` 探活，坏连接直接丢弃重建；
    - 归还时先 `rollback()` 清干净事务状态，避免把未提交事务带进下一次使用；
    - 连接用 `autocommit=False`：抢锁/回写都要求显式 `commit()`，语义与现网一致。

    线程安全：连接在同一时刻只被一个调用方持有（queue 保证），
    池本身只在 borrow/return 时短暂持锁。
    """

    def __init__(self, params: dict[str, Any], size: int) -> None:
        self._params = params
        self._size = max(1, int(size))
        self._idle: "queue.LifoQueue[pymysql.connections.Connection]" = queue.LifoQueue(
            maxsize=self._size
        )
        self._lock = threading.Lock()
        self._created = 0
        self._closed = False

    # ------------------------------------------------------------ 建连
    def _new_connection(self) -> pymysql.connections.Connection:
        """建立一条新连接（password 不落日志）。"""
        return pymysql.connect(
            host=self._params["host"],
            port=self._params["port"],
            user=self._params["user"],
            password=self._params["password"],
            database=self._params["database"],
            charset=self._params.get("charset", "utf8mb4"),
            connect_timeout=self._params.get("connect_timeout", 10),
            cursorclass=DictCursor,
            autocommit=False,
        )

    def borrow(self) -> pymysql.connections.Connection:
        """
        借出一条可用连接。

        Returns:
            pymysql 连接（DictCursor，autocommit=False）

        Raises:
            ExhibitionMysqlError: 池已关闭 / 借出超时 / 建连失败
        """
        if self._closed:
            raise ExhibitionMysqlError("exhibition MySQL 连接池已关闭")

        conn: Optional[pymysql.connections.Connection] = None
        try:
            conn = self._idle.get_nowait()
        except queue.Empty:
            with self._lock:
                if self._created < self._size:
                    self._created += 1
                    may_create = True
                else:
                    may_create = False
            if may_create:
                try:
                    return self._new_connection()
                except Exception as exc:
                    with self._lock:
                        self._created -= 1
                    raise ExhibitionMysqlError(
                        f"exhibition MySQL 建连失败: {type(exc).__name__}"
                    ) from exc
            # 池满：等别人归还
            try:
                conn = self._idle.get(timeout=_BORROW_TIMEOUT_SECONDS)
            except queue.Empty as exc:
                raise ExhibitionMysqlError(
                    f"exhibition MySQL 连接池借出超时（>{_BORROW_TIMEOUT_SECONDS}s，size={self._size}）"
                ) from exc

        # 探活：坏连接不归还，直接替换
        try:
            conn.ping(reconnect=True)
            return conn
        except Exception:
            logger.warning("exhibition MySQL 空闲连接探活失败，重建连接")
            try:
                conn.close()
            except Exception:
                pass
            try:
                return self._new_connection()
            except Exception as exc:
                with self._lock:
                    self._created = max(0, self._created - 1)
                raise ExhibitionMysqlError(
                    f"exhibition MySQL 重连失败: {type(exc).__name__}"
                ) from exc

    def release(self, conn: Optional[pymysql.connections.Connection]) -> None:
        """归还连接；脏事务回滚，坏连接丢弃。"""
        if conn is None:
            return
        if self._closed:
            try:
                conn.close()
            except Exception:
                pass
            return
        try:
            conn.rollback()
            self._idle.put_nowait(conn)
        except queue.Full:
            try:
                conn.close()
            except Exception:
                pass
            with self._lock:
                self._created = max(0, self._created - 1)
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            with self._lock:
                self._created = max(0, self._created - 1)

    def close_all(self) -> None:
        """关闭池内所有空闲连接（进程退出 / fork 后重置用）。"""
        self._closed = True
        while True:
            try:
                conn = self._idle.get_nowait()
            except queue.Empty:
                break
            try:
                conn.close()
            except Exception:
                pass
        with self._lock:
            self._created = 0


_pool: Optional[_ConnectionPool] = None
_pool_pid: Optional[int] = None
_pool_lock = threading.Lock()


def get_pool() -> _ConnectionPool:
    """
    获取 exhibition MySQL 连接池（单例，按进程隔离）。

    ⚠️ 记录创建时的 pid：fork 出来的子进程会拿到父进程的池副本，
    检测到 pid 变化时重建，避免多进程共用同一批 socket。

    Raises:
        RuntimeError: 未配置 exhibition MySQL（见 EXHIBITION_MYSQL_* 环境变量）
    """
    global _pool, _pool_pid
    pid = __import__("os").getpid()
    with _pool_lock:
        if _pool is None or _pool_pid != pid or _pool._closed:  # noqa: SLF001
            params = settings.require_exhibition_mysql()
            _pool = _ConnectionPool(params, settings.EXHIBITION_MYSQL_POOL_SIZE or _DEFAULT_POOL_SIZE)
            _pool_pid = pid
            logger.info(
                "exhibition MySQL 连接池就绪 host=%s port=%s db=%s size=%s",
                params["host"], params["port"], params["database"], settings.EXHIBITION_MYSQL_POOL_SIZE,
            )
        return _pool


def close_pool() -> None:
    """关闭连接池（worker 优雅退出时调用）。"""
    global _pool, _pool_pid
    with _pool_lock:
        if _pool is not None:
            _pool.close_all()
        _pool = None
        _pool_pid = None


@contextmanager
def mysql_connection() -> Iterator[pymysql.connections.Connection]:
    """
    借出一条连接（上下文管理器，退出自动归还）。

    用法：
        with mysql_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(...)
            conn.commit()
    """
    pool = get_pool()
    conn = pool.borrow()
    try:
        yield conn
    finally:
        pool.release(conn)


def ping() -> bool:
    """
    连通性探测（只读，`SELECT 1`）。

    Returns:
        是否连通；未配置 exhibition MySQL 时返回 False
    """
    if not settings.is_exhibition_mysql_enabled:
        return False
    try:
        with mysql_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 AS ok")
                row = cur.fetchone()
            conn.commit()
        return bool(row and int(row.get("ok") or 0) == 1)
    except Exception as exc:
        logger.error("exhibition MySQL 连通性探测失败: %s: %s", type(exc).__name__, exc)
        return False


# ---------------------------------------------------------------- 同步查询封装

def query_all(sql: str, params: Sequence[Any] | None = None) -> list[dict[str, Any]]:
    """执行 SELECT，返回全部行（dict 列表）。"""
    with mysql_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, list(params or ()))
            rows = list(cur.fetchall() or [])
        conn.commit()
        return rows


def query_one(sql: str, params: Sequence[Any] | None = None) -> Optional[dict[str, Any]]:
    """执行 SELECT，返回首行或 None。"""
    with mysql_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, list(params or ()))
            row = cur.fetchone()
        conn.commit()
        return row


def execute(sql: str, params: Sequence[Any] | None = None) -> int:
    """
    执行 INSERT/UPDATE/DELETE，返回受影响行数。

    ⚠️ 抢锁场景必须校验返回值（rowcount），不要忽略。
    """
    with mysql_connection() as conn:
        with conn.cursor() as cur:
            affected = cur.execute(sql, list(params or ()))
        conn.commit()
        return int(affected or 0)


def execute_returning_id(sql: str, params: Sequence[Any] | None = None) -> int:
    """
    执行 INSERT，返回自增主键（`cursor.lastrowid`）。

    upsert 场景请在 SQL 内用 `id = LAST_INSERT_ID(id)`，
    否则命中唯一键走 UPDATE 分支时 lastrowid 不可靠。
    """
    with mysql_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, list(params or ()))
            new_id = int(cur.lastrowid or 0)
        conn.commit()
        return new_id


def execute_many(sql: str, params_seq: Sequence[Sequence[Any]]) -> int:
    """批量执行同一条 SQL，返回受影响行数合计。"""
    if not params_seq:
        return 0
    with mysql_connection() as conn:
        with conn.cursor() as cur:
            affected = cur.executemany(sql, [list(p) for p in params_seq])
        conn.commit()
        return int(affected or 0)


def run_in_transaction(fn: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    """
    在**单条连接、单个事务**内执行自定义逻辑（抢锁等多语句原子操作用）。

    fn 的第一个参数是 pymysql 连接，其余透传；fn 内部自行决定 commit/rollback，
    异常时统一 rollback 并归还连接。

    用法：
        run_in_transaction(_claim_tasks_sync, worker_id, limit)

    Args:
        fn: 形如 `fn(conn, *args, **kwargs)` 的回调
        *args / **kwargs: 透传给 fn

    Returns:
        fn 的返回值
    """
    with mysql_connection() as conn:
        try:
            return fn(conn, *args, **kwargs)
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise


# ---------------------------------------------------------------- 异步门面

async def run_db(fn: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    """
    在线程池中执行同步 DB 调用，避免阻塞 worker 事件循环。

    用法：
        rows = await run_db(query_all, "SELECT ...", [1])

    Args:
        fn: 同步函数（通常是本模块或 repository 里的查询函数）
        *args / **kwargs: 透传给 fn

    Returns:
        fn 的返回值
    """
    return await asyncio.to_thread(fn, *args, **kwargs)


def default_worker_id() -> str:
    """
    生成默认 worker 实例标识（写入 task.locked_by）。

    形如 `gd25-news-content-<hostname>-<pid>`，多实例互不覆盖；
    超长时截断到 64 字符以内（列定义 varchar(64)）。
    """
    host = ""
    try:
        host = socket.gethostname()
    except Exception:
        host = "unknown"
    return f"gd25-news-{host}-{__import__('os').getpid()}"[:64]
