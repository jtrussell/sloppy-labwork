FROM python:3.12
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
COPY pyproject.toml uv.lock /app/
RUN uv sync --frozen --no-dev
COPY . /app/
