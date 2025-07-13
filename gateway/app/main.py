import os
import httpx
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware # CORS 미들웨어 임포트
from auth_middleware import AuthMiddleware

app = FastAPI(title="API Gateway")

# ▼▼▼ CORS 미들웨어 추가 ▼▼▼
origins = [
    "http://localhost",
    "http://127.0.0.1",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,  # 쿠키를 포함한 요청을 허용하려면 반드시 True
    allow_methods=["*"],     # 모든 HTTP 메서드 허용
    allow_headers=["*"],     # 모든 HTTP 헤더 허용
)

# 인증 미들웨어는 CORS 미들웨어 뒤에 추가
app.add_middleware(AuthMiddleware)

USER_SERVICE_URL = os.getenv("USER_SERVICE_URL")
BOARD_SERVICE_URL = os.getenv("BOARD_SERVICE_URL")
BLOG_SERVICE_URL = os.getenv("BLOG_SERVICE_URL")

@app.on_event("startup")
async def startup_event():
    timeout = httpx.Timeout(10.0, connect=5.0)
    app.state.client = httpx.AsyncClient(timeout=timeout)

@app.on_event("shutdown")
async def shutdown_event():
    await app.state.client.aclose()


# ▼▼▼ 이 데코레이터에 methods를 추가하여 모든 요청 방식을 허용하도록 변경합니다. ▼▼▼
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def reverse_proxy(request: Request):
    path = request.url.path
    client: httpx.AsyncClient = request.app.state.client
    print(path)
    print(USER_SERVICE_URL)
    if path.startswith("/api/users") or path.startswith("/api/auth"):
        base_url = USER_SERVICE_URL
    elif path.startswith("/api/board"):
        base_url = BOARD_SERVICE_URL
    elif path.startswith("/api/blog"):
        base_url = BLOG_SERVICE_URL
    else:
        raise HTTPException(status_code=404, detail="Endpoint not found")

    url = f"{base_url}{path}?{request.url.query}"
    
    try:
        rp_resp = await client.request(
            method=request.method,
            url=url,
            headers=request.headers.raw,
            content=await request.body()
        )
        
        response_headers = dict(rp_resp.headers)
        response_headers.pop("content-length", None)
        response_headers.pop("content-encoding", None)
        
        return Response(
            content=rp_resp.content,
            status_code=rp_resp.status_code,
            headers=response_headers,
        )
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail=f"Service unavailable: {base_url}")
    except httpx.ReadTimeout:
        raise HTTPException(status_code=504, detail=f"Request timeout: {base_url}")