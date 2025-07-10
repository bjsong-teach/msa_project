import os
import math
import asyncio
import uuid
from typing import Annotated, List, Set
from fastapi import FastAPI, Depends, HTTPException, Header, Query, status, UploadFile, File
from fastapi.staticfiles import StaticFiles
from sqlmodel import select, func, SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import selectinload
import httpx


from database import init_db, get_session
from models import BlogArticle, ArticleCreate, ArticleUpdate, ArticleImage

app = FastAPI(title="Blog Service")
USER_SERVICE_URL = os.getenv("USER_SERVICE_URL")

STATIC_DIR = "/app/static"
IMAGE_DIR = f"{STATIC_DIR}/images"
os.makedirs(IMAGE_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

class PaginatedResponse(SQLModel):
    total: int
    page: int
    size: int
    pages: int
    items: List[dict] = []

@app.on_event("startup")
async def on_startup():
    await init_db()

@app.post("/api/blog/articles", response_model=BlogArticle, status_code=status.HTTP_201_CREATED)
async def create_article(
    article_data: ArticleCreate, 
    session: Annotated[AsyncSession, Depends(get_session)],
    x_user_id: Annotated[int, Header(alias="X-User-Id")],
):
    """새로운 블로그 게시글을 생성합니다."""
    new_article = BlogArticle.model_validate(article_data, update={"owner_id": x_user_id})
    session.add(new_article)
    await session.commit()
    await session.refresh(new_article)
    return new_article

@app.get("/api/blog/articles", response_model=PaginatedResponse)
async def list_articles(
    session: Annotated[AsyncSession, Depends(get_session)],
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100)
):
    """블로그 게시글 목록을 페이지네이션하여 반환합니다."""
    offset = (page - 1) * size
    count_query = select(func.count(BlogArticle.id))
    total_result = await session.exec(count_query)
    total = total_result.one()

    articles_query = select(BlogArticle).order_by(BlogArticle.id.desc()).offset(offset).limit(size)
    articles_result = await session.exec(articles_query)
    articles = articles_result.all()

    author_ids = {p.owner_id for p in articles}
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
        except Exception: pass
    
    article_ids = [a.id for a in articles]
    thumbnails = {}
    if article_ids:
        image_query = select(ArticleImage).where(ArticleImage.article_id.in_(article_ids))
        image_results = await session.exec(image_query)
        for img in image_results.all():
            if img.article_id not in thumbnails:
                thumbnails[img.article_id] = f"/static/images/{img.image_filename}"

    items_with_details = []
    for article in articles:
        article_dict = article.model_dump()
        article_dict["author_username"] = authors.get(article.owner_id, "Unknown")
        article_dict["image_url"] = thumbnails.get(article.id)
        items_with_details.append(article_dict)
        
    return PaginatedResponse(
        total=total, page=page, size=size,
        pages=math.ceil(total / size), items=items_with_details
    )

@app.get("/api/blog/articles/{article_id}")
async def get_article(article_id: int, session: Annotated[AsyncSession, Depends(get_session)]):
    """특정 블로그 게시글의 상세 정보를 반환합니다."""
    query = select(BlogArticle).where(BlogArticle.id == article_id).options(selectinload(BlogArticle.images))
    results = await session.exec(query)
    article = results.one_or_none()
    
    if not article: raise HTTPException(status_code=404, detail="Article not found")
    
    author_info = {}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{USER_SERVICE_URL}/api/users/{article.owner_id}")
            if resp.status_code == 200: author_info = resp.json()
    except Exception:
        author_info = {"username": "Unknown"}

    image_urls = [f"/static/images/{img.image_filename}" for img in article.images]
    
    return {"article": article, "author": author_info, "image_urls": image_urls}

@app.patch("/api/blog/articles/{article_id}", response_model=BlogArticle)
async def update_article(
    article_id: int,
    article_data: ArticleUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    x_user_id: Annotated[int, Header(alias="X-User-Id")],
):
    """게시글의 텍스트 정보(제목, 내용, 태그)를 부분 수정합니다."""
    db_article = await session.get(BlogArticle, article_id)
    if not db_article:
        raise HTTPException(status_code=404, detail="Article not found")
    if db_article.owner_id != x_user_id:
        raise HTTPException(status_code=403, detail="Not authorized")

    update_data = article_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_article, key, value)
    
    await session.commit()
    await session.refresh(db_article)
    return db_article

@app.delete("/api/blog/articles/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_article(
    article_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    x_user_id: Annotated[int, Header(alias="X-User-Id")],
):
    """게시글과 연결된 모든 이미지를 삭제하고, 게시글 자체를 삭제합니다."""
    # 게시글과 이미지들을 함께 불러옵니다.
    query = select(BlogArticle).where(BlogArticle.id == article_id).options(selectinload(BlogArticle.images))
    results = await session.exec(query)
    db_article = results.one_or_none()

    if not db_article:
        raise HTTPException(status_code=404, detail="Article not found")
    if db_article.owner_id != x_user_id:
        raise HTTPException(status_code=403, detail="Not authorized")

    # 연결된 이미지 파일들을 서버에서 삭제
    for image in db_article.images:
        file_path = os.path.join(IMAGE_DIR, image.image_filename)
        if os.path.exists(file_path):
            os.remove(file_path)
        # 이미지 DB 레코드 삭제
        await session.delete(image)

    # 게시글 DB 레코드 삭제
    await session.delete(db_article)
    await session.commit()
    return

@app.post("/api/blog/articles/{article_id}/upload-images", response_model=List[str])
async def upload_article_images(
    article_id: int,
    files: List[UploadFile],
    session: Annotated[AsyncSession, Depends(get_session)],
    x_user_id: Annotated[int, Header(alias="X-User-Id")],
):
    """게시글에 여러 이미지를 업로드하고 파일명을 DB에 저장합니다."""
    db_article = await session.get(BlogArticle, article_id)
    if not db_article:
        raise HTTPException(status_code=404, detail="Article not found")
    if db_article.owner_id != x_user_id:
        raise HTTPException(status_code=403, detail="Not authorized")

    saved_filenames = []
    for file in files:
        file_extension = os.path.splitext(file.filename)[1]
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        file_path = os.path.join(IMAGE_DIR, unique_filename)

        with open(file_path, "wb") as buffer:
            buffer.write(await file.read())

        new_image = ArticleImage(image_filename=unique_filename, article_id=article_id)
        session.add(new_image)
        saved_filenames.append(unique_filename)
    
    await session.commit()
    return saved_filenames

@app.get("/api/blog/tags", response_model=List[str])
async def get_all_tags(session: Annotated[AsyncSession, Depends(get_session)]):
    """모든 게시물의 태그를 수집하여 중복 없이 반환합니다."""
    query = select(BlogArticle.tags).where(BlogArticle.tags != None)
    results = await session.exec(query)
    all_tags: Set[str] = set()
    for tags_str in results.all():
        tags = [tag.strip() for tag in tags_str.split(',') if tag.strip()]
        all_tags.update(tags)
    return sorted(list(all_tags))