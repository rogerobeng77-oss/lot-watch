FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./backend/
WORKDIR /app/backend
ENV PORT=8080
EXPOSE 8080
CMD ["sh","-c","uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
