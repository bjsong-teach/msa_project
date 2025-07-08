import secrets
from typing import Optional
from passlib.context import CryptContext
from redis.asyncio import Redis

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SESSION_TTL_SECONDS = 3600

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

async def create_session(redis: Redis, user_id: int) -> str:
    session_id = secrets.token_hex(16)
    await redis.setex(f"session:{session_id}", SESSION_TTL_SECONDS, user_id)
    return session_id

async def get_user_id_from_session(redis: Redis, session_id: str) -> Optional[int]:
    user_id = await redis.get(f"session:{session_id}")
    return int(user_id) if user_id else None

async def delete_session(redis: Redis, session_id: str):
    await redis.delete(f"session:{session_id}")