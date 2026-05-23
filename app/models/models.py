from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, ForeignKey, Enum
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func
import enum, uuid

Base = declarative_base()

def gen_id():
    return str(uuid.uuid4())

class PlanType(str, enum.Enum):
    free       = "free"
    business   = "business"
    enterprise = "enterprise"

class User(Base):
    __tablename__ = "users"

    id           = Column(String, primary_key=True, default=gen_id)
    email        = Column(String, unique=True, nullable=False, index=True)
    name         = Column(String)
    password_hash= Column(String, nullable=False)
    plan         = Column(Enum(PlanType), default=PlanType.free)
    is_active    = Column(Boolean, default=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    datasets     = relationship("Dataset", back_populates="owner", cascade="all, delete")
    dashboards   = relationship("Dashboard", back_populates="owner", cascade="all, delete")

class Dataset(Base):
    __tablename__ = "datasets"

    id           = Column(String, primary_key=True, default=gen_id)
    user_id      = Column(String, ForeignKey("users.id"), nullable=False)
    name         = Column(String, nullable=False)
    rows         = Column(Integer, default=0)
    columns      = Column(Integer, default=0)
    size_bytes   = Column(Integer, default=0)
    storage_path = Column(String)           # путь к файлу на диске / S3
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    owner        = relationship("User", back_populates="datasets")

class Dashboard(Base):
    __tablename__ = "dashboards"

    id           = Column(String, primary_key=True, default=gen_id)
    user_id      = Column(String, ForeignKey("users.id"), nullable=False)
    dataset_id   = Column(String, ForeignKey("datasets.id"))
    title        = Column(String, nullable=False)
    config       = Column(Text)   # JSON: chart configs
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    owner        = relationship("User", back_populates="dashboards")

class WaitlistEntry(Base):
    __tablename__ = "waitlist"

    id           = Column(String, primary_key=True, default=gen_id)
    email        = Column(String, unique=True, nullable=False, index=True)
    source       = Column(String, default="landing")   # откуда пришёл
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id           = Column(String, primary_key=True, default=gen_id)
    user_id      = Column(String, ForeignKey("users.id"), nullable=False)
    dataset_id   = Column(String, ForeignKey("datasets.id"))
    role         = Column(String)   # "user" | "assistant"
    content      = Column(Text)
    tokens_used  = Column(Integer, default=0)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

class Subscription(Base):
    __tablename__ = "subscriptions"

    id               = Column(String, primary_key=True, default=gen_id)
    user_id          = Column(String, ForeignKey("users.id"), unique=True)
    plan             = Column(Enum(PlanType))
    stripe_sub_id    = Column(String)
    status           = Column(String)   # active | canceled | past_due
    current_period_end = Column(DateTime(timezone=True))
    created_at       = Column(DateTime(timezone=True), server_default=func.now())
