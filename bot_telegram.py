import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import TimedOut, NetworkError
import yt_dlp
import asyncio

# Carrega variáveis de ambiente do arquivo .env se existir
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Obtém o token da variável de ambiente
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TOKEN:
    raise ValueError("Nenhum token fornecido. Configure a variável de ambiente TELEGRAM_BOT_TOKEN")

# Dicionário para armazenar URLs e informações temporariamente
user_urls = {}

def identify_platform(url: str) -> str:
    """Identifica a plataforma com base na URL"""
    url = url.lower()
    
    if 'youtube.com' in url or 'youtu.be' in url:
        return 'youtube'
    elif 'tiktok.com' in url:
        return 'tiktok'
    elif 'instagram.com' in url:
        return 'instagram'
    else:
        return 'unknown'

def get_video_formats(formats):
    if not formats:  # Verifica se formats é None ou vazio
        return []
        
    video_formats = []
    seen_formats = set()
    
    # Primeiro, encontra o melhor formato de áudio disponível
    best_audio = None
    for f in formats:
        if not isinstance(f, dict):  # Verifica se f é um dicionário válido
            continue
        if f.get('acodec') != 'none' and f.get('vcodec') == 'none':
            if best_audio is None or (f.get('abr', 0) or 0) > (best_audio.get('abr', 0) or 0):
                best_audio = f
    
    # Processa os formatos de vídeo
    for f in formats:
        if not isinstance(f, dict):
            continue
            
        # Verifica se é um formato de vídeo válido
        if (f.get('vcodec') != 'none' and 
            f.get('height') is not None and 
            'storyboard' not in str(f.get('format_note', '')).lower()):
            
            height = f.get('height', 0)
            if height > 0:  # Verifica se a altura é válida
                format_key = f"{height}p"
                
                if format_key not in seen_formats:
                    seen_formats.add(format_key)
                    
                    # Define o format_id baseado na presença de áudio
                    if f.get('acodec') != 'none':
                        format_id = f['format_id']
                    elif best_audio:
                        format_id = f"{f['format_id']}+{best_audio['format_id']}"
                    else:
                        format_id = f['format_id']
                    
                    video_formats.append({
                        'format_id': format_id,
                        'resolution': format_key,
                        'ext': 'mp4',
                        'filesize': f.get('filesize', 0),
                        'height': height,
                        'fps': f.get('fps', 0) or 30  # Valor padrão para fps
                    })
    
    # Ordena por altura (qualidade) em ordem decrescente
    return sorted(video_formats, key=lambda x: x.get('height', 0), reverse=True)

def get_audio_formats(formats):
    target_bitrates = [128, 256, 320]
    audio_formats = []
    
    best_audio = None
    for f in formats:
        if (f.get('vcodec') == 'none' and 
            f.get('acodec') != 'none' and 
            f.get('abr') is not None):
            
            if best_audio is None or f.get('abr', 0) > best_audio.get('abr', 0):
                best_audio = f
    
    if best_audio:
        for bitrate in target_bitrates:
            audio_formats.append({
                'format_id': best_audio['format_id'],
                'abr': bitrate,
                'ext': 'mp3',
                'filesize': best_audio.get('filesize', 0)
            })
    
    return audio_formats

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        'Olá! Bem-vindo ao Downloader Bot! 🤖\n\n'
        'Envie-me um link do YouTube, TikTok ou Instagram para baixar o vídeo.'
    )

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    
    try:
        processing_message = await update.message.reply_text(
            "⏳ Analisando o link, por favor aguarde..."
        )
        
        platform = identify_platform(url)
        if platform == 'unknown':
            await processing_message.edit_text(
                "❌ Link não suportado.\n"
                "Por favor, envie um link do YouTube, TikTok ou Instagram."
            )
            return
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False if platform in ['tiktok', 'instagram'] else True,
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best' if platform in ['tiktok', 'instagram'] else None,
            'socket_timeout': 60,
            'retries': 3,
            'nocheckcertificate': True,
            'headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Connection': 'keep-alive',
            }
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            title = info.get('title', 'Video')
            duration = info.get('duration', 0)
            # Garante que duration seja um número inteiro
            if isinstance(duration, float):
                duration = int(duration)
            channel = info.get('uploader', info.get('channel', 'Unknown'))
            
            # Garante que os formatos estejam disponíveis para YouTube
            formats = []
            if platform == 'youtube':
                if isinstance(info.get('formats'), list):
                    formats = info['formats']
                elif isinstance(info.get('entries'), list) and len(info['entries']) > 0:
                    formats = info['entries'][0].get('formats', [])
            
            user_urls[update.effective_user.id] = {
                'url': url,
                'title': title,
                'platform': platform,
                'formats': formats
            }
            
            if platform == 'youtube':
                keyboard = [
                    [
                        InlineKeyboardButton("📹 Baixar Vídeo", callback_data='select_video'),
                        InlineKeyboardButton("🎵 Baixar Áudio", callback_data='select_audio')
                    ]
                ]
            else:
                keyboard = [
                    [
                        InlineKeyboardButton("📹 Baixar em HD (1080p)", callback_data='video_best'),
                        InlineKeyboardButton("🎵 Extrair Áudio MP3", callback_data='audio_best')
                    ]
                ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            platform_emojis = {
                'youtube': '▶️',
                'tiktok': '📱',
                'instagram': '📸'
            }
            platform_emoji = platform_emojis.get(platform, '🎥')
            
            # Formatação da duração
            if duration:
                minutes = duration // 60
                seconds = duration % 60
                duration_text = f"{minutes}:{seconds:02d}"
            else:
                duration_text = "N/A"
            
            await processing_message.edit_text(
                f"✅ Link processado com sucesso!\n\n"
                f"{platform_emoji} Título: {title}\n"
                f"👤 Canal: {channel}\n"
                f"⏱ Duração: {duration_text}\n\n"
                f"Escolha uma opção:",
                reply_markup=reply_markup
            )
            
    except Exception as e:
        print(f"Erro: {str(e)}")
        await processing_message.edit_text(
            "❌ Erro ao processar o link. Verifique se o link é válido e tente novamente."
        )

async def show_video_qualities(query, formats):
    keyboard = []
    for fmt in formats:
        try:
            label = f"📹 {fmt['resolution']}"
            fps = fmt.get('fps', 0)
            if fps and fps > 30:  # Verifica se fps existe e é maior que 30
                label += f" {fps}fps"
            keyboard.append([InlineKeyboardButton(label, callback_data=f"video_{fmt['format_id']}")])
        except Exception as e:
            print(f"Erro ao processar formato: {str(e)}")
            continue
    
    if not keyboard:  # Se nenhum formato foi adicionado
        await query.edit_message_text(
            "❌ Não foi possível obter os formatos de vídeo. Tente novamente."
        )
        return
    
    keyboard.append([InlineKeyboardButton("↩️ Voltar", callback_data="back")])
    await query.edit_message_text(
        "Selecione a qualidade do vídeo:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_audio_qualities(query, formats):
    keyboard = []
    for fmt in formats:
        keyboard.append([
            InlineKeyboardButton(
                f"🎵 MP3 {fmt['abr']}kbps",
                callback_data=f"audio_{fmt['format_id']}_{fmt['abr']}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("↩️ Voltar", callback_data="back")])
    await query.edit_message_text(
        "Selecione a qualidade do áudio:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def download_video(url: str, format_id: str, query):
    try:
        await query.edit_message_text("⏳ Baixando o vídeo...")
        
        is_instagram = 'instagram.com' in url.lower()
        is_tiktok = 'tiktok.com' in url.lower()
        
        video_opts = {
            'format': format_id if not (is_tiktok or is_instagram) else 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best',
            'outtmpl': f'video_{query.message.message_id}.%(ext)s',
            'merge_output_format': 'mp4',
            'socket_timeout': 60,
            'retries': 3,
            'nocheckcertificate': True,
            'headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Connection': 'keep-alive',
            }
        }
        
        if is_tiktok:
            video_opts.update({
                'extract_flat': False,
                'force_generic_extractor': False,
            })
        elif is_instagram:
            video_opts.update({
                'extract_flat': False,
            })
        
        with yt_dlp.YoutubeDL(video_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info)
            
            if not os.path.exists(file_path):
                file_path = file_path.rsplit('.', 1)[0] + '.mp4'
            
            await query.edit_message_text("⏳ Enviando o vídeo...")
            
            try:
                file_size = os.path.getsize(file_path) / (1024 * 1024)  # Converte para MB
                with open(file_path, 'rb') as video_file:
                    await query.message.reply_video(
                        video=video_file,
                        caption=f"🎥 {info['title']}\n"
                                f"📊 Qualidade: HD\n"
                                f"💾 Tamanho: {file_size:.1f}MB"
                    )
            finally:
                if os.path.exists(file_path):
                    os.remove(file_path)
            
            await query.edit_message_text("✅ Download concluído!")
            
    except Exception as e:
        print(f"Erro no download: {str(e)}")
        await query.edit_message_text(
            "❌ Erro ao baixar o vídeo. Tente novamente."
        )

async def download_audio(url: str, format_id: str, query):
    try:
        await query.edit_message_text("⏳ Baixando o áudio...")
        
        target_bitrate = format_id.split('_')[-1] if '_' in format_id else '128'
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'audio_{query.message.message_id}.%(ext)s',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': target_bitrate,
            }],
            'socket_timeout': 60,
            'retries': 3,
            'nocheckcertificate': True
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = f'audio_{query.message.message_id}.mp3'
            
            await query.edit_message_text("⏳ Enviando o áudio...")
            
            try:
                with open(file_path, 'rb') as audio_file:
                    await query.message.reply_audio(
                        audio=audio_file,
                        title=info['title'],
                        performer=info.get('uploader', 'Unknown'),
                        caption=f"🎵 {info['title']}"
                    )
            finally:
                if os.path.exists(file_path):
                    os.remove(file_path)
            
            await query.edit_message_text("✅ Download concluído!")
            
    except Exception as e:
        print(f"Erro no download: {str(e)}")
        await query.edit_message_text(
            "❌ Erro ao baixar o áudio. Tente novamente."
        )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in user_urls:
        await query.edit_message_text('Sessão expirada. Por favor, envie o link novamente.')
        return
    
    user_data = user_urls[user_id]
    platform = user_data['platform']
    
    try:
        if query.data == "back":
            if platform == 'youtube':
                keyboard = [
                    [
                        InlineKeyboardButton("📹 Baixar Vídeo", callback_data='select_video'),
                        InlineKeyboardButton("🎵 Baixar Áudio", callback_data='select_audio')
                    ]
                ]
            else:
                keyboard = [
                    [
                        InlineKeyboardButton("📹 Baixar em HD (1080p)", callback_data='video_best'),
                        InlineKeyboardButton("🎵 Extrair Áudio MP3", callback_data='audio_best')
                    ]
                ]
            
            await query.edit_message_text(
                f"🎥 {user_data['title']}\n\nEscolha uma opção:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        elif platform == 'youtube':
            if query.data == "select_video":
                video_formats = get_video_formats(user_data['formats'])
                await show_video_qualities(query, video_formats)
            elif query.data == "select_audio":
                audio_formats = get_audio_formats(user_data['formats'])
                await show_audio_qualities(query, audio_formats)
            elif query.data.startswith("video_"):
                format_id = query.data[6:]
                await download_video(user_data['url'], format_id, query)
                del user_urls[user_id]
            elif query.data.startswith("audio_"):
                format_id = query.data[6:]
                await download_audio(user_data['url'], format_id, query)
                del user_urls[user_id]
        
        else:  # Instagram ou TikTok
            if query.data == 'video_best':
                await download_video(user_data['url'], 'best', query)
                del user_urls[user_id]
            elif query.data == 'audio_best':
                await download_audio(user_data['url'], 'bestaudio/best', query)
                del user_urls[user_id]
    
    except Exception as e:
        print(f"Erro no callback: {str(e)}")
        await query.edit_message_text(
            "❌ Ocorreu um erro. Por favor, tente novamente enviando o link."
        )
        if user_id in user_urls:
            del user_urls[user_id]

def main():
    """Função principal do bot"""
    application = (
        Application.builder()
        .token(TOKEN)
        .connect_timeout(60.0)
        .read_timeout(60.0)
        .write_timeout(60.0)
        .pool_timeout(60.0)
        .build()
    )
    
    # Adicionar handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    print('Bot iniciado! Aguardando mensagens...')
    
    # Iniciar o bot
    application.run_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES
    )

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nBot encerrado pelo usuário.')
    except Exception as e:
        print(f'Erro ao executar o bot: {e}')
