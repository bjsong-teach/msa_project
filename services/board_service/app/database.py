import os
from dotenv import load_dotenv
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

# create_async_engine과 AsyncEngine은 sqlalchemy.ext.asyncio에서 직접 가져옵니다.
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine 

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# 타입 힌트를 위해 AsyncEngine 사용
engine: AsyncEngine = create_async_engine(DATABASE_URL)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

async def get_session():
    async with AsyncSession(engine) as session:
        yield session