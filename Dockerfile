FROM python:3.9-slim

WORKDIR /app

# Instalar FFmpeg
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copiar arquivos do projeto
COPY requirements.txt .
COPY bot_telegram.py .

# Instalar dependências
RUN pip install --no-cache-dir -r requirements.txt

# Executar o bot
CMD ["python", "bot_telegram.py"] 