from datetime import datetime, timezone 
from typing import List, Optional
from sqlmodel import Field, SQLModel

# 1. 이미지 정보를 저장할 새 테이블 모델
class ArticleImage(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    image_filename: str
    
    # 외래 키 제약 조건 및 Relationship 제거
    article_id: Optional[int] = Field(default=None, index=True)


# 2. 기존 BlogArticle 모델 수정
class BlogArticle(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(index=True)
    content: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    owner_id: int
    tags: Optional[str] = Field(default=None)
    
    # Relationship 제거
    # images: List["ArticleImage"] = Relationship(back_populates="article")


class ArticleCreate(SQLModel):
    title: str
    content: str
    tags: Optional[str] = Field(default=None)

class ArticleUpdate(SQLModel):
    title: Optional[str] = Field(default=None)
    content: Optional[str] = Field(default=None)
    tags: Optional[str] = Field(default=None)