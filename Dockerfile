FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
COPY growo_edge growo_edge
COPY examples examples
RUN pip install --no-cache-dir -e . uvicorn fastapi
EXPOSE 8080
CMD ["python", "examples/avito_bot.py"]
