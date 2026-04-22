"""SQLAlchemy database setup and models."""

from datetime import UTC, datetime, timedelta
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text, JSON,
    create_engine, ForeignKey
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from config.settings import get_settings

settings = get_settings()

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
    pool_pre_ping=True,
)

# Enable WAL mode for SQLite
if "sqlite" in settings.DATABASE_URL:
    from sqlalchemy import event
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def _utcnow_naive() -> datetime:
    """Return current UTC timestamp without tzinfo for DB compatibility."""
    return datetime.now(UTC).replace(tzinfo=None)


def get_db():
    """Dependency to get DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=True)  # Bcrypt hashed password
    udemy_display_name = Column(String(255), nullable=True)
    udemy_cookies = Column(JSON, nullable=True)
    currency = Column(String(10), default="usd")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_utcnow_naive)
    updated_at = Column(DateTime, default=_utcnow_naive, onupdate=_utcnow_naive)

    # Lifetime aggregate stats — incremented after every course regardless of whether
    # a run completes, so metrics are always accurate even after disconnects.
    total_enrolled = Column(Integer, default=0, nullable=False)
    total_already_enrolled = Column(Integer, default=0, nullable=False)
    total_expired = Column(Integer, default=0, nullable=False)
    total_excluded = Column(Integer, default=0, nullable=False)
    total_amount_saved = Column(Float, default=0.0, nullable=False)

    # Relationships
    settings = relationship("UserSettings", back_populates="user", uselist=False)
    enrollment_runs = relationship("EnrollmentRun", back_populates="user")
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")


class UserSession(Base):
    """Persistent session — maps a secure token (stored in browser cookie) to a user."""
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, index=True)
    token = Column(String(64), unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=_utcnow_naive)
    expires_at = Column(DateTime, default=lambda: _utcnow_naive() + timedelta(days=30))

    user = relationship("User", back_populates="sessions")


class UserSettings(Base):
    __tablename__ = "user_settings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)

    @staticmethod
    def default_sites():
        return {
            "Real Discount": True,
            "Courson": True,
            "IDownloadCoupons": True,
            "E-next": True,
            "Discudemy": True,
            "Udemy Freebies": True,
            "Course Joiner": True,
            "Course Vania": True,
            "Course Coupon Club": True,
            "Coupon Scorpion": True,
            "Reddit /r/udemyfreebies": True,
            "TutorialBar": True,
            "FreeWebCart": True,
            "Easy Learn": True,
        }

    @staticmethod
    def default_languages():
        return {
            "Arabic": True, "Chinese": True, "Dutch": True, "English": True,
            "French": True, "German": True, "Hindi": True, "Indonesian": True,
            "Italian": True, "Japanese": True, "Korean": True, "Nepali": True,
            "Polish": True, "Portuguese": True, "Romanian": True, "Russian": True,
            "Spanish": True, "Thai": True, "Turkish": True, "Urdu": True, "Vietnamese": True,
        }

    @staticmethod
    def default_categories():
        return {
            "Business": True, "Design": True, "Development": True,
            "Finance & Accounting": True, "Health & Fitness": True,
            "IT & Software": True, "Lifestyle": True, "Marketing": True,
            "Music": True, "Office Productivity": True, "Personal Development": True,
            "Photography & Video": True, "Teaching & Academics": True,
        }

    # Sites to scrape
    sites = Column(JSON, default=default_sites)

    # Language filters
    languages = Column(JSON, default=default_languages)

    # Category filters
    categories = Column(JSON, default=default_categories)

    # Exclusions
    instructor_exclude = Column(JSON, default=list)
    title_exclude = Column(JSON, default=list)
    min_rating = Column(Float, default=0.0)
    course_update_threshold_months = Column(Integer, default=24)

    # Preferences
    save_txt = Column(Boolean, default=False)
    discounted_only = Column(Boolean, default=False)

    # Advanced Features
    proxy_url = Column(String(500), nullable=True)
    enable_headless = Column(Boolean, default=False)
    firecrawl_api_key = Column(String(255), nullable=True)

    created_at = Column(DateTime, default=_utcnow_naive)
    updated_at = Column(DateTime, default=_utcnow_naive, onupdate=_utcnow_naive)

    # Relationships
    user = relationship("User", back_populates="settings")


class EnrollmentRun(Base):
    __tablename__ = "enrollment_runs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    status = Column(String(50), default="pending")  # pending, scraping, enrolling, completed, failed
    total_courses_found = Column(Integer, default=0)
    total_processed = Column(Integer, default=0)
    successfully_enrolled = Column(Integer, default=0)
    already_enrolled = Column(Integer, default=0)
    expired = Column(Integer, default=0)
    excluded = Column(Integer, default=0)
    amount_saved = Column(Float, default=0.0)
    currency = Column(String(10), default="usd")

    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, default=_utcnow_naive)
    completed_at = Column(DateTime, nullable=True)
    progress_data = Column(JSON, default=dict)

    # Relationships
    user = relationship("User", back_populates="enrollment_runs")
    courses = relationship("EnrolledCourse", back_populates="enrollment_run")


class EnrolledCourse(Base):
    __tablename__ = "enrolled_courses"

    id = Column(Integer, primary_key=True, index=True)
    enrollment_run_id = Column(Integer, ForeignKey("enrollment_runs.id"), nullable=False)

    title = Column(String(500), nullable=False)
    url = Column(String(1000), nullable=False)
    slug = Column(String(255), nullable=True)
    course_id = Column(String(50), nullable=True)
    coupon_code = Column(String(100), nullable=True)
    price = Column(Float, nullable=True)
    category = Column(String(100), nullable=True)
    language = Column(String(50), nullable=True)
    rating = Column(Float, nullable=True)
    site_source = Column(String(100), nullable=True)
    status = Column(String(50), default="enrolled")  # enrolled, failed, excluded, expired
    error_message = Column(Text, nullable=True)
    enrolled_at = Column(DateTime, default=_utcnow_naive)

    # Relationships
    enrollment_run = relationship("EnrollmentRun", back_populates="courses")


def create_tables():
    """Create all database tables."""
    Base.metadata.create_all(bind=engine)
