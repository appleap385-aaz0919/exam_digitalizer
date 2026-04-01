from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class SuccessResponse(BaseModel, Generic[T]):
    success: bool = True
    data: T
    message: Optional[str] = None


class ErrorResponse(BaseModel):
    success: bool = False
    error_code: str
    message: str
    detail: Optional[Any] = None


class PageMeta(BaseModel):
    total: int
    page: int
    limit: int
    total_pages: int


class PagedResponse(BaseModel, Generic[T]):
    success: bool = True
    data: list[T]
    meta: PageMeta


# ─── 에러 코드 ────────────────────────────────────────────────────
class ErrorCode:
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    QUESTION_NOT_FOUND = "QUESTION_NOT_FOUND"
    EXAM_NOT_FOUND = "EXAM_NOT_FOUND"
    CLASSROOM_NOT_FOUND = "CLASSROOM_NOT_FOUND"
    USER_NOT_FOUND = "USER_NOT_FOUND"
    DUPLICATE_FILE = "DUPLICATE_FILE"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    EXAM_ALREADY_CONFIRMED = "EXAM_ALREADY_CONFIRMED"
    EXAM_NOT_ACTIVE = "EXAM_NOT_ACTIVE"
    ALREADY_SUBMITTED = "ALREADY_SUBMITTED"
    STUDENT_NOT_FOUND = "STUDENT_NOT_FOUND"
