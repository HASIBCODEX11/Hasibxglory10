FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Railway / Render give the port in $PORT, main.py reads it automatically
EXPOSE 25567
CMD ["python", "app.py"]
