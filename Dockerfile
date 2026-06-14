FROM python:3.10-slim

# 系统依赖
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN python --version && node --version && npm --version

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    # 修复 protobuf-to-dict 在 Python 3.10+ 的兼容问题
    sed -i -e 's/\blong\b/int/g' -e 's/\bunicode\b/str/g' /usr/local/lib/python3.10/site-packages/protobuf_to_dict.py

COPY . .

EXPOSE 5000

ENV PYTHONUNBUFFERED=1
ENV NODE_ENV=production

CMD ["python", "web_listener.py"]
