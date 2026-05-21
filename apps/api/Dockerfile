FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1

COPY pyproject.toml ./
COPY packages ./packages
RUN pip install .

COPY apps ./apps

EXPOSE 8000
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
