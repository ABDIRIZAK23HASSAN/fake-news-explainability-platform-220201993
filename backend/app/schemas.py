"""Request bodies. Validation messages are written to be shown directly to users."""
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

NAME = Field(min_length=1, max_length=100)


class RegisterIn(BaseModel):
    first_name: str = NAME
    last_name: str = NAME
    email: EmailStr
    password: str = Field(max_length=128)

    @field_validator("first_name", "last_name")
    @classmethod
    def strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name cannot be empty")
        return v


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class ForgotIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    token: str
    new_password: str = Field(max_length=128)


class ProfileUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = None


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(max_length=128)


class DeleteAccountIn(BaseModel):
    password: str


class SettingsIn(BaseModel):
    theme: Literal["Light", "Dark"] | None = None
    language: Literal["en", "tr", "ar"] | None = None
    email_notification: bool | None = None
    default_export_format: Literal["PDF", "CSV"] | None = None


class AnalyzeIn(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    text: str = Field(min_length=1, max_length=300_000)


class DeletePredictionsIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=500)


# -------- admin --------
class AdminUserUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = None
    role: Literal["User", "Administrator"] | None = None
    is_active: bool | None = None


class AdminResetPasswordIn(BaseModel):
    new_password: str = Field(max_length=128)


class NewsUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    content: str | None = Field(default=None, min_length=1)
    subject: str | None = Field(default=None, min_length=1, max_length=100)
    publication_date: str | None = None
    label: Literal["Fake", "Real"] | None = None


class SubjectRename(BaseModel):
    new_name: str = Field(min_length=1, max_length=100)


class TrainIn(BaseModel):
    algorithm: str
    vectorizer: str = "tfidf_bigram"
    name: str | None = Field(default=None, max_length=150)
    wait: bool = False


class TrainBatchIn(BaseModel):
    algorithms: list[str] = Field(min_length=1, max_length=10)
    vectorizer: str = "tfidf_bigram"


class StopwordsIn(BaseModel):
    words: list[str] = Field(max_length=5000)


class KeywordEntryIn(BaseModel):
    term: str = Field(min_length=1, max_length=100)
    list_type: Literal["include", "exclude"]


class SettingsUpdate(BaseModel):
    values: dict[str, str]


class AdminCreateUser(BaseModel):
    first_name: str = NAME
    last_name: str = NAME
    email: EmailStr
    password: str = Field(max_length=128)
    role: Literal["User", "Administrator"] = "User"
