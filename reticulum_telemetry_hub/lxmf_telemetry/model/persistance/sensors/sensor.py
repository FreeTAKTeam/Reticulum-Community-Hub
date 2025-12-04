from sqlalchemy import Column, ForeignKey, Integer, Float, Boolean, BLOB
from msgpack import packb, unpackb
from sqlalchemy.orm import DeclarativeMeta, relationship, Mapped, mapped_column

from .. import Base


class SensorDeclarativeMeta(DeclarativeMeta):
    """Custom declarative metaclass that fills in mapper defaults."""

    def __init__(cls, classname, bases, dict_, **kwargs):
        if classname != "Sensor":
            mapper_args = dict_.get("__mapper_args__")
            if mapper_args is None or "polymorphic_identity" not in mapper_args:
                mapper_args = dict(mapper_args or {})
                mapper_args.setdefault("with_polymorphic", "*")
                mapper_args.setdefault("polymorphic_identity", classname)
                cls.__mapper_args__ = mapper_args
        super().__init__(classname, bases, dict_, **kwargs)


class Sensor(Base, metaclass=SensorDeclarativeMeta):
    __tablename__ = "Sensor"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sid = Column(Integer, nullable=False, default=0x00)
    stale_time = Column(Float, nullable=True)
    data = Column(BLOB, nullable=True)
    synthesized = Column(Boolean, default=False)
    telemeter_id: Mapped[int] = mapped_column(ForeignKey("Telemeter.id"))
    telemeter = relationship("Telemeter", back_populates="sensors")

    def __init__(
        self,
        stale_time=None,
        data=None,
        active=False,
        synthesized=False,
        last_update=0,
        last_read=0,
    ):
        self.stale_time = stale_time
        self.data = data
        self.active = active
        self.synthesized = synthesized
        self.last_update = last_update
        self.last_read = last_read

    def packb(self):
        return packb(self.pack())

    def unpackb(self, packed):
        return unpackb(self.unpack(packed))

    def pack(self):
        return self.data

    def unpack(self, packed):
        return packed

    __mapper_args__ = {
        "polymorphic_identity": "Sensor",
        "with_polymorphic": "*",
        "polymorphic_on": sid,
    }
