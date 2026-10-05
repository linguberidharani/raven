"""Request and response shapes of the auth endpoints (see docs/api-contract.md)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, SecretStr, field_validator

from raven.services.auth import validate_email, validate_name, validate_organization, validate_password


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    email: str
    organization: str | None = None
    password: SecretStr

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return validate_name(value)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return validate_email(value)

    @field_validator("organization")
    @classmethod
    def _organization(cls, value: str | None) -> str | None:
        return validate_organization(value)

    @field_validator("password")
    @classmethod
    def _password(cls, value: SecretStr) -> SecretStr:
        validate_password(value.get_secret_value())
        return value


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str
    password: SecretStr


class ForgotPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return validate_email(value)


class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str
    password: SecretStr

    @field_validator("token")
    @classmethod
    def _token(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("token must not be empty")
        return cleaned

    @field_validator("password")
    @classmethod
    def _password(cls, value: SecretStr) -> SecretStr:
        validate_password(value.get_secret_value())
        return value


class MessageOut(BaseModel):
    detail: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    organization: str | None
    created_at: str
