# python-sync

A small FastAPI service that syncs records from a paginated, rate-limited third-party API into a database. Built as a focused exercise in the parts of integration work that actually break in production.

## Run it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Then open http://127.0.0.1:8000/docs

| Endpoint | Does |
|---|---|
| `POST /sync?limit=40` | Pulls from the external API and upserts into the database |
| `GET /items` | Returns what's stored |

```bash
pytest -q
```

## Layout

| File | Responsibility |
|---|---|
| `client.py` | Talking to the external API: retries, rate limits, pagination |
| `models.py` | SQLAlchemy table + Pydantic schemas + session factory |
| `main.py` | HTTP layer: two endpoints, DB session per request |
| `test_sync.py` | Retry behaviour and sync idempotency |

## Design decisions

**Retry as a decorator, not inline.** Backoff belongs to every outbound call, not to one function. `@retry(times=3, delay=0.5)` with `functools.wraps` keeps the retry policy declarative and the fetch logic readable. It catches only network exceptions — retrying a `TypeError` would just hide a bug.

**`429` handled separately from the retry loop.** The retry decorator backs off on *errors*; a `429` is the server explicitly telling you how long to wait via `Retry-After`. Inventing your own delay when you've been given one is wrong. This is the same contract Microsoft Graph and most enterprise APIs use.

**Pagination follows the API's `next` link, not computed offsets.** Offset pagination silently skips or repeats rows when records are inserted mid-run. Cursor/link pagination doesn't. Same pattern as `@odata.nextLink`.

**Fetching is a generator.** `iter_pokemon` yields one record at a time, so memory stays flat whether the source has 40 records or 400,000. Loading a full page list into memory works until the day it doesn't.

**Idempotency in two places.** The sync upserts on `external_id`, and the database has a `UniqueConstraint` on that column. Application logic can race; the constraint can't. Running `/sync` ten times leaves the same rows.

**`external_id` is separate from the primary key.** The external system's identifier is the only stable way to match records across two systems. Every real integration needs this column.

**Two Pydantic models, not one.** `PokemonIn` validates what the upstream API sends; `PokemonOut` defines what this service returns. Keeping them separate means an upstream change doesn't leak into this API's public contract.

**One transaction per sync, not per row.** Fewer round trips, at the cost of all-or-nothing semantics. For a batch sync that's the right trade; for a long-running one I'd commit in batches with a resume cursor.

**DB session via FastAPI dependency with `yield`.** One session per request, closed in `finally` even on error. Leaked sessions exhaust the connection pool.

## Known limitations

Deliberately scoped small. What I'd change for production:

- **The upsert is read-then-write, so it races.** Two concurrent syncs could both find nothing and both insert. The unique constraint means the loser gets an error rather than a duplicate, but the correct fix is a real upsert — `INSERT ... ON CONFLICT DO UPDATE` in Postgres.
- **SQLite and `create_all()`.** Production means Postgres and Alembic migrations — the ORM should never create or alter schema against a real database.
- **No jitter on the backoff.** With many clients, synchronised retries stampede. Backoff should be randomised.
- **No resume cursor.** A crash mid-sync restarts from the beginning instead of resuming from a watermark.
- **Retries are synchronous and block.** For volume, this belongs behind a queue with a dead-letter queue after N failures, rather than retrying inline.
- **No structured logging, metrics or correlation IDs.** Sync lag and DLQ depth are what you'd actually alert on.
