from typing import Optional, List
from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    name: str
    initials: str
    email: str
    department: Optional[str] = None
    department_id: Optional[int] = None


class ExceptionDecisionRequest(BaseModel):
    note: Optional[str] = None


class QueryDraftRequest(BaseModel):
    department_id: int
    exception_ids: Optional[List[int]] = None


class QuerySendRequest(BaseModel):
    to_emails: str
    subject: str
    body: str
    exception_ids: List[int]


class QueryAnswerRequest(BaseModel):
    answer_type: str  # "correct" | "wrong" | "not_sure"
    note: Optional[str] = None


class ExportRequest(BaseModel):
    submission_ids: List[int]
    file_format: str = "csv"


class DepartmentOut(BaseModel):
    id: int
    name: str


class CreateSubmitterRequest(BaseModel):
    name: str
    email: str
    department_id: int


class SubmitterOut(BaseModel):
    id: int
    name: str
    email: str
    department: Optional[str] = None
    department_id: Optional[int] = None
