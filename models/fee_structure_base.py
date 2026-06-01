from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, UniqueConstraint

from db.base import Base


class FeeStructureSchema(Base):
    """Monthly fee configuration for a batch.

    One FeeStructure per Batch (enforced by unique constraint on batch_id).
    Note: due_day lives on Enrollment (not here) because students joining
    mid-month each have their own payment cycle.
    """

    __tablename__ = "FeeStructure"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    batch_id = Column(Integer, ForeignKey("Batch.id"), nullable=False)
    monthly_amount = Column(Numeric(10, 2), nullable=False)
    created_at = Column(DateTime, default=datetime.now, nullable=False)

    __table_args__ = (
        UniqueConstraint("batch_id", name="uq_fee_structure_batch"),
    )
