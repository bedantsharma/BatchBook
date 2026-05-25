from sqlalchemy import Column, ForeignKey, Integer, UniqueConstraint

from db.base import Base


class BatchTeacherSchema(Base):
    __tablename__ = "BatchTeacher"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    batch_id = Column(Integer, ForeignKey("Batch.id"), nullable=False)
    teacher_id = Column(Integer, ForeignKey("Teacher.id"), nullable=False)

    __table_args__ = (
        UniqueConstraint("batch_id", "teacher_id", name="uq_batch_teacher"),
    )
