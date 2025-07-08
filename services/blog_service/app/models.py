from typing import Optional
from sqlmodel import Field, SQLModel
from datetime import datetime, timezone

# BlogArticle 모델 정의
class BlogArticle(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(index=True)
    content: str
    category: str = Field(index=True, default="General")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    owner_id: int

# 데이터 전송 객체(DTO) 정의
class ArticleCreate(SQLModel):
    title: str
    content: str
    category: Optional[str] = "General"

class ArticleUpdate(SQLModel):
    title: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None