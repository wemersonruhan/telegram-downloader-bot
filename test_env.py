from dotenv import load_dotenv
import os

print("Iniciando teste de variáveis de ambiente...")

# Carrega as variáveis de ambiente
load_dotenv()

# Tenta ler o token
token = os.getenv('TELEGRAM_BOT_TOKEN')

print(f"Arquivo .env existe? {os.path.exists('.env')}")
print(f"Conteúdo do arquivo .env:")
with open('.env', 'r') as f:
    print(f.read())
print(f"Token lido: {token}")