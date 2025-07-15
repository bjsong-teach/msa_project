@app.get("/api/blog/articles/{article_id}")
async def get_article(article_id: int, session: Annotated[AsyncSession, Depends(get_session)]):
    """특정 블로그 게시글의 상세 정보를 반환합니다."""
    # 1. 먼저 게시글 정보만 가져옵니다.
    article = await session.get(BlogArticle, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    author_info = {}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{USER_SERVICE_URL}/api/users/{article.owner_id}")
            if resp.status_code == 200:
                author_info = resp.json()
    except Exception:
        author_info = {"username": "Unknown"}

    # 2. 별도의 쿼리를 실행하여 이 게시글에 속한 이미지 파일명들을 가져옵니다.
    image_query = select(ArticleImage.image_filename).where(ArticleImage.article_id == article_id)
    image_results = await session.exec(image_query)
    image_filenames = image_results.all()
    
    # 3. 가져온 파일명들로 전체 이미지 URL 목록을 생성합니다.
    image_urls = [f"/static/images/{filename}" for filename in image_filenames]
    
    return {"article": article, "author": author_info, "image_urls": image_urls}

@app.delete("/api/blog/articles/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_article(
    article_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    x_user_id: Annotated[int, Header(alias="X-User-Id")],
):
    """게시글과 연결된 모든 이미지를 삭제하고, 게시글 자체를 삭제합니다."""
    db_article = await session.get(BlogArticle, article_id)

    if not db_article:
        raise HTTPException(status_code=404, detail="Article not found")
    if db_article.owner_id != x_user_id:
        raise HTTPException(status_code=403, detail="Not authorized")

    # 1. 삭제할 게시글에 연결된 이미지들을 DB에서 찾습니다.
    image_query = select(ArticleImage).where(ArticleImage.article_id == article_id)
    images_to_delete = (await session.exec(image_query)).all()

    # 2. 찾은 이미지들을 서버 디스크와 DB에서 모두 삭제합니다.
    for image in images_to_delete:
        file_path = os.path.join(IMAGE_DIR, image.image_filename)
        if os.path.exists(file_path):
            os.remove(file_path)
        await session.delete(image)

    # 3. 마지막으로 게시글을 삭제합니다.
    await session.delete(db_article)
    await session.commit()
    return
