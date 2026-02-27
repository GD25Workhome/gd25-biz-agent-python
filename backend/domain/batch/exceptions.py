"""
批次任务领域异常定义。

设计文档：cursor_docs/022703-批次任务通用创建接口技术设计.md
"""


class BatchJobError(Exception):
    """批次任务领域基础异常。"""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class UnknownJobTypeError(BatchJobError):
    """未注册的 job_type 错误。"""

    def __init__(self, job_type: str) -> None:
        self.job_type = job_type
        super().__init__(f"未知的批次任务类型：{job_type}")


class InvalidJobParamsError(BatchJobError):
    """批次任务创建参数不合法。"""

    def __init__(self, message: str) -> None:
        super().__init__(message)

