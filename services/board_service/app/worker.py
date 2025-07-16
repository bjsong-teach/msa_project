import asyncio
import os
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
import redis.asyncio as redis

# models.py에서 Post 모델을 가져옵니다.
from models import Post

# 환경 변수 로드
load_dotenv()

# 워커를 위한 별도의 DB 및 Redis 연결 설정
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_async_engine(DATABASE_URL)
REDIS_URL = os.getenv("REDIS_URL")
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

async def sync_redis_to_mysql():
    """
    1분마다 실행되며, Redis의 조회수를 MySQL에 동기화하는 메인 함수입니다.
    """
    print("--- [Worker] 조회수 동기화 작업 시작 ---")
    
    # 1. 'view_sync_queue'에서 처리해야 할 모든 게시물 ID를 가져옵니다.
    post_ids_to_sync = await redis_client.zrange("view_sync_queue", 0, -1)
    if not post_ids_to_sync:
        print("--- [Worker] 동기화할 게시물이 없습니다. ---")
        return

    async with AsyncSession(engine) as session:
        for post_id_str in post_ids_to_sync:
            try:
                post_id = int(post_id_str)
                
                # 2. Redis에서 해당 게시물의 최종 조회수를 가져옵니다.
                redis_key = f"views:post:{post_id}"
                view_count = await redis_client.get(redis_key)
                if view_count is None:
                    continue

                # 3. MySQL에서 해당 게시물을 찾습니다.
                db_post = await session.get(Post, post_id)
                
                if db_post:
                    # 4. MySQL의 views 컬럼을 Redis의 값으로 업데이트합니다.
                    db_post.views = int(view_count)
                    session.add(db_post) # 세션에 변경사항 등록
                    print(f"--- [Worker] Post ID: {post_id}, 조회수: {view_count}로 DB 업데이트 준비 ---")
            except Exception as e:
                print(f"--- [Worker] 동기화 중 오류 발생 (Post ID: {post_id_str}): {e} ---")

        # 5. 모든 변경사항을 DB에 한 번에 커밋합니다.
        await session.commit()
        print("--- [Worker] DB 동기화 완료 ---")

    # 6. 처리된 작업들을 큐에서 제거합니다.
    await redis_client.zrem("view_sync_queue", *post_ids_to_sync)
    print(f"--- [Worker] {len(post_ids_to_sync)}개 작업 큐에서 제거 ---")


async def main():
    scheduler = AsyncIOScheduler()
    # 1분마다 sync_redis_to_mysql 함수를 실행하도록 스케줄을 등록합니다.
    scheduler.add_job(sync_redis_to_mysql, 'interval', minutes=1)
    scheduler.start()
    print("--- [Worker] 백그라운드 워커 시작. 1분마다 조회수를 동기화합니다. (Ctrl+C로 종료) ---")
    
    try:
        # 워커가 계속 실행되도록 무한 루프를 유지합니다.
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
