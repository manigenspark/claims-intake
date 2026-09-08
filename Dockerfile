# Claims intake API image.
# Built for the deployment architecture (linux/amd64), which may differ from the
# laptop or Codespace CPU. See README.md for why --platform is required.

FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY data ./data

RUN pip install --no-cache-dir uv \
    && uv sync --frozen --no-dev \
    && rm -rf /root/.cache

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"

EXPOSE 8000

CMD ["uvicorn", "claims.api.routes:app", "--host", "0.0.0.0", "--port", "8000"]
