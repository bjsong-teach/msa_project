from typing import Annotated
from fastapi import FastAPI, Depends, HTTPException, status, Response, Cookie
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from redis.asyncio import Redis

from database import init_db, get_session
from redis_client import get_redis
from models import User, UserCreate, UserPublic
from auth import get_password_hash, verify_password, create_session, delete_session, get_user_id_from_session

app = FastAPI(title="User Service")

@app.on_event("startup")
async def on_startup():
    await init_db()

# ▼▼▼ 이 부분이 @app.post로 되어 있는지 반드시 확인 ▼▼▼
@app.post("/api/auth/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
async def register_user(user_data: UserCreate, session: Annotated[AsyncSession, Depends(get_session)]):
    user_exists_result = await session.exec(select(User).where(User.username == user_data.username))
    if user_exists_result.one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")
    
    hashed_password = get_password_hash(user_data.password)
    new_user = User(username=user_data.username, hashed_password=hashed_password)
    session.add(new_user)
    await session.commit()
    await session.refresh(new_user)
    return new_user
@app.post("/api/auth/login")
async def login(
    response: Response, 
    user_data: UserCreate, 
    session: Annotated[AsyncSession, Depends(get_session)], 
    redis: Annotated[Redis, Depends(get_redis)]
):
    user_result = await session.exec(select(User).where(User.username == user_data.username))
    user = user_result.one_or_none()
    if not user or not verify_password(user_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    
    session_id = await create_session(redis, user.id)
    response.set_cookie(key="session_id", value=session_id, httponly=True, samesite="lax", max_age=3600, path="/")
    return {"message": "Login successful"}

@app.post("/api/auth/logout")
async def logout(response: Response, session_id: Annotated[str | None, Cookie()] = None, redis: Annotated[Redis, Depends(get_redis)] = None):
    if session_id:
        await delete_session(redis, session_id)
    response.delete_cookie("session_id", path="/")
    return {"message": "Logout successful"}

@app.get("/api/auth/me", response_model=UserPublic)
async def get_current_user_from_auth(
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
    session_id: Annotated[str | None, Cookie()] = None,
):
    if not session_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    
    user_id = await get_user_id_from_session(redis, session_id)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    
    user = await session.get(User, int(user_id)) # user_id를 int로 변환
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user
@app.get("/api/users/{user_id}", response_model=UserPublic)
async def get_user_by_id(user_id: int, session: Annotated[AsyncSession, Depends(get_session)]):
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user