"""Pydantic schemas for request/response validation."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, field_validator


# ── Auth ──────────────────────────────────────────────
class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, v: str) -> str:
        """Validate email is non-empty and has a basic email shape."""
        value = v.strip() if isinstance(v, str) else ""
        if not value:
            raise ValueError("Email cannot be empty")
        if "@" not in value or "." not in value.rsplit("@", 1)[-1]:
            raise ValueError("Invalid email format")
        return value

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Validate password meets minimum security requirements."""
        if not v or len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return v


class CookieLoginRequest(BaseModel):
    access_token: str
    client_id: str
    csrf_token: str


class LoginResponse(BaseModel):
    success: bool = False
    status: str  # "success" | "error"
    message: str
    display_name: Optional[str] = None
    currency: Optional[str] = None


# ── Settings ──────────────────────────────────────────
class SitesConfig(BaseModel):
    real_discount: bool = True
    courson: bool = True
    idownloadcoupons: bool = True
    e_next: bool = True
    discudemy: bool = True
    udemy_freebies: bool = True
    course_joiner: bool = True
    course_vania: bool = True


class SettingsUpdate(BaseModel):
    sites: Optional[dict] = None
    languages: Optional[dict] = None
    categories: Optional[dict] = None
    instructor_exclude: Optional[list[str]] = None
    title_exclude: Optional[list[str]] = None
    min_rating: Optional[float] = None
    course_update_threshold_months: Optional[int] = None
    save_txt: Optional[bool] = None
    discounted_only: Optional[bool] = None
    proxy_url: Optional[str] = None
    enable_headless: Optional[bool] = None

    @field_validator("proxy_url")
    @classmethod
    def validate_proxy_url(cls, v: Optional[str]) -> Optional[str]:
        """Validate proxy URL format if provided."""
        if not v:
            return v
        from app.security import validate_proxy_url
        if not validate_proxy_url(v):
            raise ValueError("Invalid proxy URL format")
        return v

    @field_validator("min_rating")
    @classmethod
    def validate_min_rating(cls, v: Optional[float]) -> Optional[float]:
        """Validate min_rating is between 0 and 5."""
        if v is not None and not (0.0 <= v <= 5.0):
            raise ValueError("min_rating must be between 0 and 5")
        return v

    @field_validator("course_update_threshold_months")
    @classmethod
    def validate_threshold(cls, v: Optional[int]) -> Optional[int]:
        """Validate threshold is positive."""
        if v is not None and v < 0:
            raise ValueError("course_update_threshold_months must be non-negative")
        return v


class SettingsResponse(BaseModel):
    sites: dict
    languages: dict
    categories: dict
    instructor_exclude: list[str]
    title_exclude: list[str]
    min_rating: float
    course_update_threshold_months: int
    save_txt: bool
    discounted_only: bool
    proxy_url: Optional[str]
    enable_headless: bool

    model_config = ConfigDict(from_attributes=True)


# ── Enrollment ────────────────────────────────────────
class EnrollmentStartRequest(BaseModel):
    """Request to start an enrollment run."""
    pass  # Uses current user settings


class EnrollmentStatus(BaseModel):
    run_id: int
    status: str
    total_courses_found: int
    total_processed: int
    successfully_enrolled: int
    already_enrolled: int
    expired: int
    excluded: int
    amount_saved: float
    currency: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class CourseInfo(BaseModel):
    title: str
    url: str
    slug: Optional[str] = None
    course_id: Optional[str] = None
    coupon_code: Optional[str] = None
    price: Optional[float] = None
    category: Optional[str] = None
    language: Optional[str] = None
    rating: Optional[float] = None
    site_source: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    enrolled_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ── Dashboard ─────────────────────────────────────────
class DashboardStats(BaseModel):
    total_runs: int
    total_enrolled: int
    total_amount_saved: float
    currency: str
    total_already_enrolled: int
    total_expired: int
    total_excluded: int
    recent_runs: list[EnrollmentStatus]


class ScrapingProgress(BaseModel):
    site: str
    progress: int
    total: int
    done: bool
    error: Optional[str] = None


class EnrollmentProgress(BaseModel):
    run_id: int
    status: str
    total_courses: int
    processed: int
    successfully_enrolled: int
    already_enrolled: int
    expired: int
    excluded: int
    amount_saved: float
    current_course_title: Optional[str] = None
    current_course_url: Optional[str] = None
    scraping_progress: list[ScrapingProgress] = []
