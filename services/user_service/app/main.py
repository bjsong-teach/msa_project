import os
import uuid
from typing import Annotated, Optional
from fastapi import FastAPI, Depends, HTTPException, status, Response, Cookie, UploadFile, File, Header
from fastapi.staticfiles import StaticFiles
from sqlmodel import select, col
from sqlmodel.ext.asyncio.session import AsyncSession
from redis.asyncio import Redis

# 같은 폴더에 있는 다른 .py 파일들을 임포트
from database import init_db, get_session
from redis_client import get_redis
from models import User, UserCreate, UserPublic, UserUpdate, PasswordUpdate,Userlogin
from auth import (
    get_password_hash, verify_password,
    create_session, delete_session, get_user_id_from_session
)

app = FastAPI(title="User Service")

# --- 정적 파일(이미지) 제공을 위한 설정 ---
STATIC_DIR = "/app/static"
PROFILE_IMAGE_DIR = f"{STATIC_DIR}/profiles"
os.makedirs(PROFILE_IMAGE_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

def create_user_public(user: User) -> UserPublic:
    """DB 모델(User)을 API 응답 모델(UserPublic)으로 변환하는 함수"""
    image_url = f"/static/profiles/{user.profile_image_filename}" if user.profile_image_filename else "https://www.w3schools.com/w3images/avatar_g.jpg"
    user_dict = user.model_dump()
    user_dict["profile_image_url"] = image_url
    return UserPublic.model_validate(user_dict)

@app.on_event("startup")
async def on_startup():
    """서버가 시작될 때 DB 테이블을 생성합니다."""
    await init_db()

@app.get("/")
async def root():
    """간단한 헬스 체크 엔드포인트"""
    return {"message": "User Service is running"}

@app.post("/api/auth/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
async def register_user(
    response: Response,
    user_data: UserCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)]
):
    """회원가입 처리 후, 바로 로그인까지 시켜 세션 쿠키를 발급합니다."""
    # 이메일만 중복되는지 확인
    statement = select(User).where(User.email == user_data.email)
    existing_user_result = await session.exec(statement)
    if existing_user_result.one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="이미 사용 중인 이메일입니다.")

    hashed_password = get_password_hash(user_data.password)
    # UserCreate 모델의 모든 데이터를 사용하여 User 객체 생성
    new_user = User.model_validate(user_data, update={"hashed_password": hashed_password})
    
    session.add(new_user)
    await session.commit()
    await session.refresh(new_user)

    # --- 자동 로그인 처리 ---
    session_id = await create_session(redis, new_user.id)
    response.set_cookie(key="session_id", value=session_id, httponly=True, samesite="lax", max_age=3600, path="/")
    
    return create_user_public(new_user)

@app.post("/api/auth/login")
async def login(
    response: Response,
    user_data: Userlogin,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)]
):
    statement = select(User).where(User.email==user_data.email)
    user_result = await session.exec(statement)
    user = user_result.one_or_none()
    
    if not user or not verify_password(user_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="이메일 또는 비밀번호가 틀립니다.")
    if user.id is not None:
        session_id = await create_session(redis, user.id)
    else:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="세션 번호가 저장되지 않았습니다.")
    response.set_cookie(key="session_id", value=session_id, httponly=True, samesite="lax", max_age=3600, path="/")
    return {"message":"Login 성공!"}

@app.post("/api/auth/logout")
async def logout(response: Response, session_id: Annotated[Optional[str], Cookie()] = None, redis: Annotated[Redis, Depends(get_redis)] = None):
    """로그아웃 처리"""
    if session_id:
        await delete_session(redis, session_id)
    response.delete_cookie("session_id", path="/")
    return {"message": "Logout successful"}

@app.get("/api/auth/me", response_model=UserPublic)
async def get_current_user_from_auth(
    response: Response, # <--- 응답 객체를 직접 다루기 위해 인자로 추가
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
    session_id: Annotated[Optional[str], Cookie()] = None,
):
    """쿠키로 사용자 정보를 확인하고, 유효하지 않은 쿠키는 삭제하도록 응답합니다."""
    if not session_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    
    user_id = await get_user_id_from_session(redis, session_id)
    
    # ▼▼▼ 바로 이 부분입니다 ▼▼▼
    if not user_id:
        # Redis에 세션이 없으면(만료 등), 쓸모없는 쿠키를 지우라고 응답 헤더에 추가합니다.
        response.delete_cookie("session_id", path="/")
        # 그 후, 인증 실패 오류를 반환합니다.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")
    
    user = await session.get(User, int(user_id))
    if not user:
        # DB에 사용자가 없는 경우에도 쿠키를 삭제해주는 것이 좋습니다.
        response.delete_cookie("session_id", path="/")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found for this session")
        
    return create_user_public(user)

@app.get("/api/users/{user_id}", response_model=UserPublic)
async def get_user_by_id(user_id: int, session: Annotated[AsyncSession, Depends(get_session)]):
    """ID로 특정 사용자 정보 반환"""
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return create_user_public(user)

@app.patch("/api/users/me", response_model=UserPublic)
async def update_my_profile(
    user_data: UserUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    user_id: Annotated[int, Header(alias="X-User-Id")],
):
    """로그인된 사용자의 프로필(이메일, 자기소개) 수정"""
    db_user = await session.get(User, user_id)
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404, detail="User not found")

    # 제공된 데이터만 업데이트
    update_data = user_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_user, key, value)
    
    await session.commit()
    await session.refresh(db_user)
    return create_user_public(db_user)

@app.post("/api/users/me/upload-image", response_model=UserPublic)
async def upload_my_profile_image(
    session: Annotated[AsyncSession, Depends(get_session)],
    user_id: Annotated[int, Header(alias="X-User-Id")],
    file: UploadFile,
):
    """로그인된 사용자의 프로필 이미지 업로드"""
    db_user = await session.get(User, user_id)
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404, detail="User not found")

    file_extension = os.path.splitext(file.filename)[1]
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    file_path = os.path.join(PROFILE_IMAGE_DIR, unique_filename)

    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())

    db_user.profile_image_filename = unique_filename
    await session.commit()
    await session.refresh(db_user)
    return create_user_public(db_user)

@app.post("/api/auth/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    password_data: PasswordUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
    user_id: Annotated[int, Header(alias="X-User-Id")],
    session_id: Annotated[str | None, Cookie()] = None,
):
    """현재 비밀번호를 확인하고 새 비밀번호로 변경합니다."""
    db_user = await session.get(User, user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    # 1. 현재 비밀번호가 맞는지 확인
    if not verify_password(password_data.current_password, db_user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect current password")

    # 2. 새 비밀번호를 해싱하여 저장
    db_user.hashed_password = get_password_hash(password_data.new_password)
    await session.commit()
    
    # 3. 비밀번호 변경 후, 현재 세션을 로그아웃 처리
    if session_id:
        await delete_session(redis, session_id)
    
    return Response(status_code=status.HTTP_204_NO_CONTENT)