import os
import math
import asyncio
import time # time 모듈 추가
from typing import Annotated, List, Optional
from fastapi import FastAPI, Depends, HTTPException, Header, Query, status, Response
from sqlmodel import select, func, SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
import httpx
import redis.asyncio as redis

# 같은 폴더에 있는 다른 .py 파일들을 임포트합니다.
from database import init_db, get_session
from redis_client import get_redis
from models import Post, PostCreate, PostUpdate

app = FastAPI(title="Board Service")

# 환경 변수에서 User Service의 주소를 가져옵니다.
USER_SERVICE_URL = os.getenv("USER_SERVICE_URL")

# 페이지네이션 응답을 위한 데이터 모델
class PaginatedResponse(SQLModel):
    total: int
    page: int
    size: int
    pages: int
    items: List[dict] = []

@app.on_event("startup")
async def on_startup():
    """서버가 시작될 때 DB 테이블을 생성합니다."""
    await init_db()

@app.post("/api/board/posts", response_model=Post, status_code=status.HTTP_201_CREATED)
async def create_post(
    post_data: PostCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    x_user_id: Annotated[int, Header(alias="X-User-Id")],
):
    """새로운 게시글을 생성합니다."""
    new_post = Post.model_validate(post_data, update={"owner_id": x_user_id})
    session.add(new_post)
    await session.commit()
    await session.refresh(new_post)
    return new_post

@app.get("/api/board/posts", response_model=PaginatedResponse)
async def list_posts(
    session: Annotated[AsyncSession, Depends(get_session)],
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    owner_id: Optional[int] = None,
):
    """게시글 목록을 페이지네이션하여 반환합니다."""
    offset = (page - 1) * size
    
    # 필터링 조건에 따라 전체 개수와 목록 쿼리를 준비합니다.
    count_query = select(func.count(Post.id))
    posts_query = select(Post).order_by(Post.id.desc())

    if owner_id:
        count_query = count_query.where(Post.owner_id == owner_id)
        posts_query = posts_query.where(Post.owner_id == owner_id)

    # 전체 개수를 먼저 조회합니다.
    total_result = await session.exec(count_query)
    total = total_result.one()

    # 현재 페이지에 해당하는 목록을 조회합니다.
    paginated_query = posts_query.offset(offset).limit(size)
    posts_result = await session.exec(paginated_query)
    posts = posts_result.all()

    # User Service에 작성자 정보를 한 번에 문의합니다.
    author_ids = {p.owner_id for p in posts}
    authors = {}
    if author_ids:
        try:
            async with httpx.AsyncClient() as client:
                tasks = [client.get(f"{USER_SERVICE_URL}/api/users/{uid}") for uid in author_ids]
                results = await asyncio.gather(*tasks)
                for resp in results:
                    if resp.status_code == 200:
                        data = resp.json()
                        authors[data['id']] = data.get('username', 'Unknown')
        except Exception as e:
            print(f"Error fetching authors: {e}")

    # 최종 응답 데이터를 조립합니다.
    items_with_details = []
    for post in posts:
        post_dict = post.model_dump(mode='json')
        post_dict["author_username"] = authors.get(post.owner_id, "Unknown")
        items_with_details.append(post_dict)
        
    return PaginatedResponse(
        total=total, page=page, size=size,
        pages=math.ceil(total / size), items=items_with_details
    )

@app.get("/api/board/posts/{post_id}")
async def get_post(
    post_id: int, 
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
):
    """특정 게시글의 상세 정보와 함께, Redis로 조회수를 1 올리고 동기화 작업을 등록합니다."""
    # Redis에서 해당 게시물의 조회수를 1 증가시킵니다.
    redis_key = f"views:post:{post_id}"
    view_count = await redis.incr(redis_key)
    
    # ▼▼▼ 동기화 작업 등록 로직 추가 ▼▼▼
    # 'view_sync_queue'라는 작업 큐에 post_id를 현재 시간 점수와 함께 추가합니다.
    await redis.zadd("view_sync_queue", {str(post_id): time.time()})
    
    post = await session.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    author_info = {}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{USER_SERVICE_URL}/api/users/{post.owner_id}")
            if resp.status_code == 200:
                author_info = resp.json()
    except Exception:
        author_info = {"username": "Unknown"}

    return {"post": post.model_dump(mode='json'), "author": author_info, "views": view_count}

@app.patch("/api/board/posts/{post_id}", response_model=Post)
async def update_post(
    post_id: int,
    post_data: PostUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    x_user_id: Annotated[int, Header(alias="X-User-Id")],
):
    """게시글의 제목과 내용을 수정합니다."""
    db_post = await session.get(Post, post_id)
    if not db_post:
        raise HTTPException(status_code=404, detail="Post not found")
    if db_post.owner_id != x_user_id:
        raise HTTPException(status_code=403, detail="Not authorized")

    update_data = post_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_post, key, value)
    
    await session.commit()
    await session.refresh(db_post)
    return db_post

@app.delete("/api/board/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(
    post_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    x_user_id: Annotated[int, Header(alias="X-User-Id")],
):
    """게시글을 삭제합니다."""
    db_post = await session.get(Post, post_id)
    if not db_post:
        raise HTTPException(status_code=404, detail="Post not found")
    if db_post.owner_id != x_user_id:
        raise HTTPException(status_code=403, detail="Not authorized")

    await session.delete(db_post)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
