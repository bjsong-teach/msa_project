FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN apt-get update && apt-get install -y default-libmysqlclient-dev build-essential
RUN pip install --no-cache-dir -r requirements.txt
COPY ./app .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8003", "--reload"]