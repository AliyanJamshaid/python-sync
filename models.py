from pydantic import BaseModel, ConfigDict, computed_field
from sqlalchemy import String, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

engine = create_engine("sqlite:///sync.db", echo=False)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Pokemon(Base):
    __tablename__ = "pokemon"
    __table_args__ = (UniqueConstraint("external_id", name="uq_pokemon_external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[int] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String(100))
    url: Mapped[str] = mapped_column(String(255))


class PokemonIn(BaseModel):
    """What the external API gives us."""

    name: str
    url: str

    @computed_field
    @property
    def external_id(self) -> int:
        return int(self.url.rstrip("/").split("/")[-1])


class PokemonOut(BaseModel):
    """What our API gives back."""

    model_config = ConfigDict(from_attributes=True)

    external_id: int
    name: str


def init_db() -> None:
    Base.metadata.create_all(engine)
