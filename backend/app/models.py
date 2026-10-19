"""ORM models - one class per table required by spec section 5 (+ a few support tables)."""
from datetime import datetime

from sqlalchemy import (Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text,
                        UniqueConstraint, text)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.utcnow()


class User(Base):
    __tablename__ = "users"
    user_id: Mapped[int] = mapped_column("UserID", primary_key=True)
    first_name: Mapped[str] = mapped_column("FirstName", String(100))
    last_name: Mapped[str] = mapped_column("LastName", String(100))
    email: Mapped[str] = mapped_column("Email", String(255), unique=True, index=True)
    password: Mapped[str] = mapped_column("Password", String(255))      # bcrypt hash
    role: Mapped[str] = mapped_column("Role", String(20), default="User")  # User / Administrator
    profile_image: Mapped[str | None] = mapped_column("ProfileImage", String(255), nullable=True)
    registration_date: Mapped[datetime] = mapped_column("RegistrationDate", DateTime, default=utcnow)
    last_login: Mapped[datetime | None] = mapped_column("LastLogin", DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column("IsActive", Boolean, default=True)

    predictions = relationship("PredictionHistory", back_populates="user", cascade="all, delete-orphan")
    settings = relationship("UserSetting", back_populates="user", uselist=False, cascade="all, delete-orphan")


class DatasetImport(Base):
    __tablename__ = "dataset_imports"
    dataset_id: Mapped[int] = mapped_column("DatasetID", primary_key=True)   # = dataset version
    dataset_name: Mapped[str] = mapped_column("DatasetName", String(255))
    uploaded_by: Mapped[int | None] = mapped_column("UploadedBy", ForeignKey("users.UserID", ondelete="SET NULL"), nullable=True)
    upload_date: Mapped[datetime] = mapped_column("UploadDate", DateTime, default=utcnow)
    total_records: Mapped[int] = mapped_column("TotalRecords", Integer, default=0)
    imported_records: Mapped[int] = mapped_column("ImportedRecords", Integer, default=0)
    rejected_records: Mapped[int] = mapped_column("RejectedRecords", Integer, default=0)
    duplicate_records: Mapped[int] = mapped_column("DuplicateRecords", Integer, default=0)
    status: Mapped[str] = mapped_column("Status", String(20), default="Processing")  # Processing/Success/Failed
    progress: Mapped[int] = mapped_column("Progress", Integer, default=0)            # 0-100
    message: Mapped[str | None] = mapped_column("Message", Text, nullable=True)

    articles = relationship("NewsArticle", back_populates="dataset", cascade="all, delete-orphan")


class NewsArticle(Base):
    __tablename__ = "news_articles"
    news_id: Mapped[int] = mapped_column("NewsID", primary_key=True)
    title: Mapped[str] = mapped_column("Title", Text)
    content: Mapped[str] = mapped_column("Content", Text)
    subject: Mapped[str] = mapped_column("Subject", String(100), index=True)
    publication_date: Mapped[str | None] = mapped_column("PublicationDate", String(50), nullable=True)
    label: Mapped[str] = mapped_column("Label", String(10), index=True)       # Fake / Real
    source_file: Mapped[str] = mapped_column("SourceFile", String(255))
    import_date: Mapped[datetime] = mapped_column("ImportDate", DateTime, default=utcnow)
    dataset_id: Mapped[int] = mapped_column("DatasetID", ForeignKey("dataset_imports.DatasetID", ondelete="CASCADE"), index=True)
    content_hash: Mapped[str] = mapped_column("ContentHash", String(64), unique=True)  # duplicate guard
    processed_text: Mapped[str | None] = mapped_column("ProcessedText", Text, nullable=True)
    prep_signature: Mapped[str | None] = mapped_column("PrepSignature", String(16), nullable=True)

    dataset = relationship("DatasetImport", back_populates="articles")


class MLModel(Base):
    __tablename__ = "models"
    model_id: Mapped[int] = mapped_column("ModelID", primary_key=True)
    model_name: Mapped[str] = mapped_column("ModelName", String(150), index=True)
    algorithm: Mapped[str] = mapped_column("Algorithm", String(60))
    vectorizer: Mapped[str] = mapped_column("Vectorizer", String(40), default="tfidf_bigram")
    dataset_version: Mapped[str | None] = mapped_column("DatasetVersion", String(100), index=True, nullable=True)
    training_date: Mapped[datetime | None] = mapped_column("TrainingDate", DateTime, nullable=True)
    training_duration: Mapped[float | None] = mapped_column("TrainingDuration", Float, nullable=True)
    accuracy: Mapped[float | None] = mapped_column("Accuracy", Float, nullable=True)
    precision: Mapped[float | None] = mapped_column("Precision", Float, nullable=True)
    recall: Mapped[float | None] = mapped_column("Recall", Float, nullable=True)
    f1_score: Mapped[float | None] = mapped_column("F1Score", Float, nullable=True)
    roc_auc: Mapped[float | None] = mapped_column("RocAuc", Float, nullable=True)
    confusion_matrix: Mapped[str | None] = mapped_column("ConfusionMatrix", Text, nullable=True)  # JSON
    artifact_path: Mapped[str | None] = mapped_column("ArtifactPath", String(500), nullable=True)
    status: Mapped[str] = mapped_column("Status", String(20), default="Training")  # Training/Ready/Failed
    is_active: Mapped[bool] = mapped_column("IsActive", Boolean, default=False)

    __table_args__ = (
        # "Only one model shall be active at any given time" enforced by the DB itself.
        Index("uq_single_active_model", "IsActive", unique=True,
              sqlite_where=text('"IsActive" = 1'), postgresql_where=text('"IsActive" = true')),
    )
    runs = relationship("TrainingRun", back_populates="model", cascade="all, delete-orphan")


class TrainingRun(Base):
    """Training history (FR-10)."""
    __tablename__ = "training_runs"
    run_id: Mapped[int] = mapped_column("RunID", primary_key=True)
    model_id: Mapped[int] = mapped_column("ModelID", ForeignKey("models.ModelID", ondelete="CASCADE"), index=True)
    started_at: Mapped[datetime] = mapped_column("StartedAt", DateTime, default=utcnow)
    duration: Mapped[float | None] = mapped_column("Duration", Float, nullable=True)
    dataset_version: Mapped[str | None] = mapped_column("DatasetVersion", String(100), nullable=True)
    n_train: Mapped[int | None] = mapped_column("NTrain", Integer, nullable=True)
    n_test: Mapped[int | None] = mapped_column("NTest", Integer, nullable=True)
    status: Mapped[str] = mapped_column("Status", String(20), default="Running")
    metrics_json: Mapped[str | None] = mapped_column("MetricsJson", Text, nullable=True)
    log: Mapped[str | None] = mapped_column("Log", Text, nullable=True)

    model = relationship("MLModel", back_populates="runs")


class PredictionHistory(Base):
    __tablename__ = "prediction_history"
    prediction_id: Mapped[int] = mapped_column("PredictionID", primary_key=True)
    user_id: Mapped[int] = mapped_column("UserID", ForeignKey("users.UserID", ondelete="CASCADE"), index=True)
    submitted_title: Mapped[str | None] = mapped_column("SubmittedTitle", Text, nullable=True)
    submitted_content: Mapped[str] = mapped_column("SubmittedContent", Text)
    prediction_result: Mapped[str] = mapped_column("PredictionResult", String(10))
    confidence_score: Mapped[float] = mapped_column("ConfidenceScore", Float)
    prob_fake: Mapped[float] = mapped_column("ProbFake", Float)
    prob_real: Mapped[float] = mapped_column("ProbReal", Float)
    processing_time: Mapped[float] = mapped_column("ProcessingTime", Float)
    prediction_date: Mapped[datetime] = mapped_column("PredictionDate", DateTime, default=utcnow, index=True)
    model_id: Mapped[int | None] = mapped_column("ModelID", ForeignKey("models.ModelID", ondelete="SET NULL"), nullable=True)

    user = relationship("User", back_populates="predictions")
    model = relationship("MLModel")
    keywords = relationship("Keyword", back_populates="prediction", cascade="all, delete-orphan")
    explanations = relationship("ExplainabilityResult", back_populates="prediction", cascade="all, delete-orphan")
    similar = relationship("SimilarNews", back_populates="prediction", cascade="all, delete-orphan")


class Keyword(Base):
    __tablename__ = "keywords"
    keyword_id: Mapped[int] = mapped_column("KeywordID", primary_key=True)
    prediction_id: Mapped[int] = mapped_column("PredictionID", ForeignKey("prediction_history.PredictionID", ondelete="CASCADE"), index=True)
    keyword: Mapped[str] = mapped_column("Keyword", String(200), index=True)
    importance_score: Mapped[float] = mapped_column("ImportanceScore", Float)
    frequency: Mapped[int | None] = mapped_column("Frequency", Integer, nullable=True)
    prediction = relationship("PredictionHistory", back_populates="keywords")


class ExplainabilityResult(Base):
    __tablename__ = "explainability_results"
    explanation_id: Mapped[int] = mapped_column("ExplanationID", primary_key=True)
    prediction_id: Mapped[int] = mapped_column("PredictionID", ForeignKey("prediction_history.PredictionID", ondelete="CASCADE"), index=True)
    word: Mapped[str] = mapped_column("Word", String(200), index=True)
    contribution_value: Mapped[float] = mapped_column("ContributionValue", Float)
    contribution_type: Mapped[str] = mapped_column("ContributionType", String(10))   # Positive / Negative
    method: Mapped[str] = mapped_column("Method", String(10), default="lime")        # lime / shap
    prediction = relationship("PredictionHistory", back_populates="explanations")


class SimilarNews(Base):
    __tablename__ = "similar_news"
    similar_news_id: Mapped[int] = mapped_column("SimilarNewsID", primary_key=True)
    prediction_id: Mapped[int] = mapped_column("PredictionID", ForeignKey("prediction_history.PredictionID", ondelete="CASCADE"), index=True)
    news_id: Mapped[int | None] = mapped_column("NewsID", ForeignKey("news_articles.NewsID", ondelete="SET NULL"), nullable=True)
    similarity_score: Mapped[float] = mapped_column("SimilarityScore", Float)
    rank: Mapped[int] = mapped_column("Rank", Integer)
    prediction = relationship("PredictionHistory", back_populates="similar")
    news = relationship("NewsArticle")


class SystemLog(Base):
    __tablename__ = "system_logs"
    log_id: Mapped[int] = mapped_column("LogID", primary_key=True)
    user_id: Mapped[int | None] = mapped_column("UserID", ForeignKey("users.UserID", ondelete="SET NULL"), nullable=True)
    event_type: Mapped[str] = mapped_column("EventType", String(30), index=True)  # Login, Prediction, Training, Import, Error...
    description: Mapped[str] = mapped_column("Description", Text)
    ip_address: Mapped[str | None] = mapped_column("IPAddress", String(64), nullable=True)
    log_date: Mapped[datetime] = mapped_column("LogDate", DateTime, default=utcnow, index=True)


class UserSetting(Base):
    __tablename__ = "user_settings"
    setting_id: Mapped[int] = mapped_column("SettingID", primary_key=True)
    user_id: Mapped[int] = mapped_column("UserID", ForeignKey("users.UserID", ondelete="CASCADE"), unique=True)
    theme: Mapped[str] = mapped_column("Theme", String(10), default="Light")
    language: Mapped[str] = mapped_column("Language", String(10), default="en")
    email_notification: Mapped[bool] = mapped_column("EmailNotification", Boolean, default=False)
    default_export_format: Mapped[str] = mapped_column("DefaultExportFormat", String(5), default="PDF")
    user = relationship("User", back_populates="settings")


# ---- support tables (not in the spec's list, needed by FR-1 / 7.2.8 / 7.2.2 / 8.1) ----
class RevokedToken(Base):
    """JWT blacklist so that logout really invalidates the token."""
    __tablename__ = "revoked_tokens"
    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    token_id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.UserID", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used: Mapped[bool] = mapped_column(Boolean, default=False)


class AppSetting(Base):
    """Key/value system-wide settings edited by the administrator (7.2.8)."""
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class KeywordDictionaryEntry(Base):
    """Admin-managed keyword dictionary: 'include' terms are always surfaced, 'exclude' never."""
    __tablename__ = "keyword_dictionary"
    __table_args__ = (UniqueConstraint("term", "list_type", name="uq_term_type"),)
    entry_id: Mapped[int] = mapped_column(primary_key=True)
    term: Mapped[str] = mapped_column(String(100), index=True)
    list_type: Mapped[str] = mapped_column(String(10))   # include / exclude
