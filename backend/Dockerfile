FROM docker.m.daocloud.io/library/python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies (use mirror for faster download in China)
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/ \
 && pip config set global.trusted-host mirrors.aliyun.com \
 && pip install torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install -r requirements.txt

# Copy project
COPY . .

# Collect static files
RUN python manage.py collectstatic --noinput 2>/dev/null || true

# Run gunicorn
EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "1", "--timeout", "600"]
