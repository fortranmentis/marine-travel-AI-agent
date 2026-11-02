FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && python -m playwright install --with-deps chromium && apt-get update && apt-get install -y --no-install-recommends fonts-nanum && rm -rf /var/lib/apt/lists/*
COPY marine_agent ./marine_agent
COPY scripts ./scripts
COPY web ./web
RUN useradd -m -u 10001 marine && mkdir -p /app/data /app/.tmp && chown -R marine:marine /app/data /app/.tmp && chmod -R a+rX /ms-playwright
USER marine
ENV MARINE_DATA_DIR=/app/data PDF_FONT_PATH=/usr/share/fonts/truetype/nanum/NanumGothic.ttf
CMD ["python","-m","uvicorn","marine_agent.app:app","--host","0.0.0.0","--port","8001","--workers","1"]
