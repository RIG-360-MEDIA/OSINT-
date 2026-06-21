"""Auth + profile + query history."""
from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.appdb.models import QueryHistory, Token, User
from app.auth import hash_password, new_token, verify_password
from app.deps import current_user, get_db
from app.schemas_account import (
    HistoryOut,
    LoginRequest,
    SettingsPatch,
    SignupRequest,
    TokenResponse,
    UserOut,
)

router = APIRouter(tags=["account"])


def _user_out(u: User) -> UserOut:
    return UserOut(
        user_id=u.id,
        username=u.username,
        default_languages=u.default_languages.split(",") if u.default_languages else None,
        home_geo=u.home_geo,
        created_at=u.created_at,
    )


@router.post("/auth/signup", response_model=TokenResponse)
async def signup(req: SignupRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    taken = await db.scalar(select(User).where(User.username == req.username))
    if taken:
        raise HTTPException(409, "username already taken")
    pwd_hash, salt = hash_password(req.password)
    uid = str(uuid4())
    raw, token_hash = new_token()
    db.add(User(id=uid, username=req.username, pwd_hash=pwd_hash, pwd_salt=salt))
    db.add(Token(token_hash=token_hash, user_id=uid, label="signup"))
    await db.commit()
    return TokenResponse(token=raw, user_id=uid, username=req.username)


@router.post("/auth/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    user = await db.scalar(select(User).where(User.username == req.username))
    if not user or not verify_password(req.password, user.pwd_hash, user.pwd_salt):
        raise HTTPException(401, "invalid credentials")
    raw, token_hash = new_token()
    db.add(Token(token_hash=token_hash, user_id=user.id, label="login"))
    await db.commit()
    return TokenResponse(token=raw, user_id=user.id, username=user.username)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(current_user)) -> UserOut:
    return _user_out(user)


@router.patch("/me", response_model=UserOut)
async def update_me(
    patch: SettingsPatch,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    if patch.default_languages is not None:
        user.default_languages = ",".join(patch.default_languages) or None
    if patch.home_geo is not None:
        user.home_geo = patch.home_geo or None
    db.add(user)
    await db.commit()
    return _user_out(user)


@router.get("/me/history", response_model=list[HistoryOut])
async def history(
    limit: int = 50,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[HistoryOut]:
    rows = await db.scalars(
        select(QueryHistory)
        .where(QueryHistory.user_id == user.id)
        .order_by(QueryHistory.created_at.desc())
        .limit(min(max(limit, 1), 200))
    )
    return [
        HistoryOut(
            id=r.id,
            query=r.query,
            languages=r.languages,
            n_results=r.n_results,
            used_web=bool(r.used_web),
            created_at=r.created_at,
        )
        for r in rows
    ]
