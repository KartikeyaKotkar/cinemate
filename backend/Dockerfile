FROM python:3.13-slim

WORKDIR /app

# Install uv
RUN pip install uv

# Copy package config and lockfile
COPY pyproject.toml uv.lock ./

# Install dependencies using a temporary build cache mount
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen

# Copy the rest of the application (ignoring files defined in .dockerignore)
COPY . .

# Expose port
EXPOSE 8000

# Run uvicorn using uv run
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]