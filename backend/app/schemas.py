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


class CreateSubmitterResponse(SubmitterOut):
    # Only ever populated on the create response, straight after generation --
    # never stored anywhere but the password_hash column, never returned by
    # GET /admin/submitters. Shown once because it can't be retrieved again.
    temporary_password: str
    email_sent: bool


class AssistantChatRequest(BaseModel):
    message: str
    page: Optional[str] = ""
    submission_id: Optional[int] = None
    exception_id: Optional[int] = None
