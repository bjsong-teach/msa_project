# gateway/Dockerfile

FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 로컬의 app 폴더 내용을 컨테이너의 /app 폴더로 복사
COPY ./app .

# 실행 명령어 (게이트웨이는 8000번 포트)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]