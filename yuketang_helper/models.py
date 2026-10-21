"""Shared data structures for platform results."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


@dataclass(frozen=True)
class Course:
    course_name: str
    classroom_id: int
    course_sign: str
    sku_id: int
    course_id: int


class SubmitStatus(str, Enum):
    CORRECT = "correct"
    INCORRECT = "incorrect"
    RATE_LIMITED = "rate_limited"
    FAILED = "failed"


@dataclass(frozen=True)
class SubmitResult:
    status: SubmitStatus
    message: str = ""
    score: Optional[float] = None
    explanation: str = ""
    retry_after: Optional[float] = None
