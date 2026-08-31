FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY code ./code

WORKDIR /app/code/web_application

ENV OLLAMA_HOST=http://host.docker.internal:11434

EXPOSE 8817

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8817"]
