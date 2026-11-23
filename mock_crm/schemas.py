import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class BookingResponse(BaseModel):
    id: str
    customer_id: str
    route: str
    departs_at: str
    seat: str
    amount: float
    status: str


class CancellationResponse(BaseModel):
    booking: BookingResponse
    fee: float
    refund_amount: float


class TicketCreate(BaseModel):
    customer_id: str = Field(min_length=1)
    subject: str = Field(min_length=1, max_length=120)
    details: str = Field(max_length=2000)

    @field_validator("subject")
    @classmethod
    def subject_must_not_be_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("subject must not be blank")
        return normalized


class TicketResponse(BaseModel):
    ticket_id: str
    customer_id: str
    subject: str
    details: str
    status: str
    created_at: str


class ContactUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str | None = None
    phone: str | None = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is not None:
            normalized = value.strip()
            if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
                raise ValueError("invalid email address")
            return normalized
        return value

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        if value is not None:
            normalized = value.strip()
            digits = re.sub(r"\D", "", normalized)
            if not 7 <= len(digits) <= 15:
                raise ValueError("phone must contain between 7 and 15 digits")
            return normalized
        return value

    @model_validator(mode="after")
    def require_contact_value(self) -> "ContactUpdate":
        if self.email is None and self.phone is None:
            raise ValueError("at least one of email or phone is required")
        return self


class CustomerContactResponse(BaseModel):
    id: str
    name: str
    email: str | None
    phone: str | None
