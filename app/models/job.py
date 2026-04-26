from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id:               Mapped[int]          = mapped_column(Integer, primary_key=True, index=True)
    user_id:          Mapped[int | None]   = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    tool_slug:        Mapped[str]          = mapped_column(String(80),  nullable=False)
    tool_name:        Mapped[str]          = mapped_column(String(120), nullable=False)
    category:         Mapped[str]          = mapped_column(String(50),  nullable=False, index=True)
    filename:         Mapped[str]          = mapped_column(String(255), nullable=False)
    file_size_bytes:  Mapped[int]          = mapped_column(Integer, default=0)
    output_size_bytes:Mapped[int | None]   = mapped_column(Integer, nullable=True)
    status:           Mapped[str]          = mapped_column(String(20),  default="success")  # success | error | processing
    created_at:       Mapped[datetime]     = mapped_column(DateTime, server_default=func.now(), index=True)

    user = relationship("User", back_populates="jobs", lazy="noload")
