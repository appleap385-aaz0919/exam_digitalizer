FROM python:3.12-slim

WORKDIR /app

# 시스템 의존성
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python 의존성 (pyproject.toml + 소스 복사 후 설치)
COPY pyproject.toml .
COPY . .
RUN pip install --no-cache-dir ".[dev]"

EXPOSE 8000

# 기본 커맨드 (docker-compose에서 오버라이드)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
