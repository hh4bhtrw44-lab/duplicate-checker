FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -r requirements.txt
CMD gunicorn wsgi:app --bind 0.0.0.0:5000 --workers 2 --timeout 120
