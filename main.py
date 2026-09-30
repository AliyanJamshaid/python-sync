from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from client import iter_pokemon
from models import Pokemon, PokemonIn, PokemonOut, SessionLocal, init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Pokemon Sync", lifespan=lifespan)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.post("/sync")
def sync(limit: int = 40, db: Session = Depends(get_db)) -> dict:
    """Pull records from the external API and upsert them."""
    created = updated = 0

    for raw in iter_pokemon(max_items=limit):
        item = PokemonIn.model_validate(raw)

        existing = db.scalar(
            select(Pokemon).where(Pokemon.external_id == item.external_id)
        )

        if existing:
            existing.name = item.name
            existing.url = item.url
            updated += 1
        else:
            db.add(Pokemon(external_id=item.external_id, name=item.name, url=item.url))
            created += 1

    db.commit()
    return {"created": created, "updated": updated}


@app.get("/items")
def list_items(db: Session = Depends(get_db)) -> list[PokemonOut]:
    rows = db.scalars(select(Pokemon).order_by(Pokemon.external_id)).all()
    return [PokemonOut.model_validate(row) for row in rows]
