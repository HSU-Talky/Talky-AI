# --- 1단계: 빌드(Builder) 스테이지 ---
FROM python:3.11-slim as builder

WORKDIR /app

# requirements.txt를 먼저 복사하여 Docker 캐시 활용
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 코드 복사
COPY . .

ENV TZ=ASIA/SEOUL

EXPOSE 8000

# uvicorn 서버 실행
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
