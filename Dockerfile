FROM python:3.9-slim

# Criar usuário não-root
RUN useradd -m -u 1000 botuser

# Criar e definir diretório de trabalho
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

# Mudar proprietário dos arquivos
RUN chown -R botuser:botuser /app

# Mudar para usuário não-root
USER botuser

# Executar o bot
CMD ["python", "bot_telegram.py"] 