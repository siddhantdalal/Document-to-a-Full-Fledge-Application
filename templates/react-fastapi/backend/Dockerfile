FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

COPY pyproject.toml ./
RUN pip install \
    "fastapi>=0.115" \
    "uvicorn[standard]>=0.30" \
    "sqlmodel>=0.0.22" \
    "pydantic>=2.8" \
    "pydantic-settings>=2.5" \
    "passlib[bcrypt]>=1.7" \
    "python-jose[cryptography]>=3.3" \
    "python-multipart>=0.0.9"

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
