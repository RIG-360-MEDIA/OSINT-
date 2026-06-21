import sys
from pathlib import Path

# Make the `app` package importable when running pytest from products/ask-rig.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.appdb.models import Base  # noqa: E402
from app.deps import get_db  # noqa: E402


@pytest_asyncio.fixture
async def client(tmp_path):
    """ASGI client backed by an isolated temp SQLite app DB.

    The corpus (read-only Postgres) is NOT touched here — account/CRUD tests are
    corpus-free; corpus-dependent flows are validated live, separately.
    """
    db_url = f"sqlite+aiosqlite:///{tmp_path.as_posix()}/test_app.db"
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async def _override_get_db():
        async with sessionmaker() as session:
            yield session

    import app.main as main_module

    main_module.app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=main_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    main_module.app.dependency_overrides.clear()
    await engine.dispose()


async def signup(client: AsyncClient, username: str, password: str = "secret123") -> str:
    resp = await client.post("/auth/signup", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
