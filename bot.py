import os
import logging
import asyncio
import tempfile
import random
import re
import json
from datetime import datetime, timedelta, time
from pydub import AudioSegment
from gtts import gTTS
from telegram import Update, Voice, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, CommandHandler, filters, ConversationHandler, CallbackQueryHandler
from openai import OpenAI
import matplotlib.pyplot as plt
import numpy as np
import requests
import csv
import io
from io import StringIO
from telegram import Update
from telegram.ext import ContextTypes

# Importar classes do banco de dados
from sqlalchemy import create_engine, and_, or_, func, desc
from sqlalchemy.orm import sessionmaker
from models import (
    Base, Usuario, PerfilUsuario, HistoricoErros,
    PontosUsuario, StreakUsuario, UltimaInteracao,
    CodigosUtilizados, InteracoesUsuario, ConversasUsuario
)
# Importar funções de banco de dados
from db_functions import (
    iniciar_bd, obter_usuario, criar_usuario, atualizar_usuario,
    obter_perfil, criar_perfil, atualizar_perfil,
    obter_pontos, adicionar_pontos_db, obter_streak, atualizar_streak_db,
    adicionar_erro, obter_historico_erros, obter_contador_interacoes, 
    adicionar_interacao, registrar_pergunta, obter_perguntas_usadas,
    verificar_codigo_usado, registrar_uso_codigo, verificar_assinatura_premium,
    ativar_assinatura, listar_assinaturas_expiradas, migrar_dados_json_para_db
)

from dotenv import load_dotenv
load_dotenv()

# Configuração do banco de dados
db_url = os.getenv("DATABASE_URL")
SessionLocal = iniciar_bd(db_url)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Chaves de acesso
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai_client = OpenAI(api_key=OPENAI_API_KEY)
URL_PLANILHA = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSQqQxElIhtdIiFYWPlz6SSXH6UUcsHqFxLWi_fhmv-h4-SM8Q7KB8M2DCooYTZRZU0pLNcfNAyzsQN/pub?gid=0&single=true&output=csv"

# Webhook do Make que você criou
MAKE_WEBHOOK_URL = "https://hook.us2.make.com/oc44mwkxo2jx2x08o9shgrxjcn8a72gr"

CSV_URL = 'https://docs.google.com/spreadsheets/d/e/2PACX-1vSQqQxElIhtdIiFYWPlz6SSXH6UUcsHqFxLWi_fhmv-h4-SM8Q7KB8M2DCooYTZRZU0pLNcfNAyzsQN/pub?gid=0&single=true&output=csv'

# Configuração de logs
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Estados de conversa
NOME, NIVEL, MENU, TEMA, TRADUCAO = range(5)

# Dicionários para controle
estagio_usuario = {}  # Mantido em memória para gerenciar o fluxo de conversas
tempo_usuarios = {}  # Para controle de tempo
ultimas_mensagens = {}  # Para armazenar as últimas mensagens e permitir tradução

LINK_PAGAMENTO = "https://pay.hotmart.com/C99134085F"

# Limite de interações gratuitas
LIMITE_INTERACOES_FREE = 3

# Temas disponíveis
TEMAS = {
    "daily_life": "Daily Life & Routines",
    "travel": "Travel & Tourism",
    "business": "Business & Work",
    "food": "Food & Cooking",
    "entertainment": "Movies & Entertainment",
    "technology": "Technology & Gadgets",
    "health": "Health & Fitness",
    "education": "Education & Learning"
}

# Perguntas por tema
perguntas_por_tema = {
    "daily_life": [
        "What's your morning routine like?",
        "Do you prefer working from home or at an office?",
        "How do you usually spend your weekends?",
        "What's your favorite part of the day?",
        "Do you have any daily habits you never skip?"
    ],
    "travel": [
        "What's your dream travel destination?",
        "Do you prefer beaches or mountains when traveling?",
        "What's the most interesting place you've visited?",
        "What do you enjoy most about traveling?",
        "Do you prefer to plan trips in detail or be spontaneous?"
    ],
    "business": [
        "What skills are most important in your job?",
        "How do you handle work stress?",
        "What's your ideal work environment?",
        "How do you balance work and personal life?",
        "What's the most challenging part of your work?"
    ],
    # ... outros temas e perguntas

"food": [
        "What's your favorite cuisine?",
        "Do you enjoy cooking at home?",
        "What's a dish you'd like to learn how to cook?",
        "Do you prefer eating out or home-cooked meals?",
        "What's the most exotic food you've tried?"
    ],
    "entertainment": [
        "What kind of movies do you enjoy watching?",
        "Who's your favorite actor or actress?",
        "What TV shows are you currently watching?",
        "Do you prefer movies or TV series?",
        "What was the last film that really impressed you?"
    ],
    "technology": [
        "What gadget can't you live without?",
        "How do you feel technology has changed your life?",
        "What's a technology trend you're excited about?",
        "Do you think AI will improve our lives?",
        "What's your favorite app and why?"
    ],
    "health": [
        "How do you stay active during the week?",
        "What's your favorite way to exercise?",
        "How do you maintain a healthy lifestyle?",
        "What healthy habits would you like to develop?",
        "How do you manage stress in your life?"
    ],
    "education": [
        "What's something new you've learned recently?",
        "How do you prefer to learn new skills?",
        "What languages would you like to learn?",
        "What subject were you best at in school?",
        "Do you prefer learning alone or in groups?"
    ]
}

# Função para migrar dados do JSON para o banco de dados
def migrar_dados_do_json():
    try:
        # Verificar se o arquivo de dados existe
        if os.path.exists("dados_bot.json"):
            with open("dados_bot.json", "r") as f:
                dados_json = json.load(f)
            
            # Criar uma sessão do banco de dados
            db = SessionLocal()
            try:
                # Chamar função de migração
                migrar_dados_json_para_db(db, dados_json)
                logging.info("Dados migrados com sucesso do JSON para o PostgreSQL")
                
                # Renomear o arquivo original para backup
                os.rename("dados_bot.json", "dados_bot.json.bak")
            finally:
                db.close()
        else:
            logging.info("Arquivo de dados JSON não encontrado, nada para migrar")
    except Exception as e:
        logging.error(f"Erro ao migrar dados: {e}")

# Funções para gamificação
def adicionar_pontos(user_id, pontos):
    # Criar uma sessão do banco de dados
    db = SessionLocal()
    try:
        # Adicionar pontos e retornar o total
        total_pontos = adicionar_pontos_db(db, user_id, pontos)
        return total_pontos
    finally:
        db.close()

# Essa função não é mais necessária, pois agora usamos o banco de dados
# Mantida apenas para compatibilidade e para facilitar a migração
def salvar_dados():
    # Como agora usamos banco de dados, não precisamos salvar em JSON
    # Esta função está mantida só para evitar erros em chamadas existentes
    pass

# Verificar acesso premium
def verificar_acesso(user_id):
    agora = datetime.now()
    
    # Criar uma sessão do banco de dados
    db = SessionLocal()
    try:
        # Verificar se o usuário tem assinatura premium ativa
        if verificar_assinatura_premium(db, user_id):
            return True
        
        # Se não tem premium, verificar se está dentro do limite gratuito
        interacoes = obter_contador_interacoes(db, user_id)
        if interacoes >= LIMITE_INTERACOES_FREE:
            return False
        
        # Se chegou aqui, o usuário está dentro do limite gratuito
        # Verificação de tempo (para limites diários)
        inicio = tempo_usuarios.get(user_id)
        if not inicio:
            tempo_usuarios[user_id] = agora
        elif agora - inicio >= timedelta(hours=24):
            # Reset do contador após 24 horas
            tempo_usuarios[user_id] = agora
            # Não precisamos resetar o contador no banco, pois faremos consulta por data
        
        return True
    finally:
        db.close()

# Função para verificar assinaturas expiradas e enviar notificação
async def verificar_assinaturas_expiradas(context: ContextTypes.DEFAULT_TYPE):
    # Criar uma sessão do banco de dados
    db = SessionLocal()
    try:
        # Obter usuários com assinaturas expiradas nas últimas 24 horas
        usuarios_expirados = listar_assinaturas_expiradas(db, horas=24)
        
        # Enviar notificações
        for usuario in usuarios_expirados:
            try:
                # Obter perfil do usuário para pegar o nome
                perfil = obter_perfil(db, usuario.user_id)
                nome = perfil.nivel if perfil else ""
                
                # Se não tiver perfil, tenta pegar o nome direto do usuário
                if not nome and usuario.nome:
                    nome = usuario.nome
                
                mensagem = (
                    f"Olá {nome}! 🧸\n\n"
                    f"Seu acesso premium ao Lana English expirou hoje. 😢\n\n"
                    f"Se você já renovou sua assinatura, use o comando /ativar com o novo código recebido.\n\n"
                    f"Para continuar evoluindo seu inglês sem interrupções, renove sua assinatura aqui:\n"
                    f"{LINK_PAGAMENTO}\n\n"
                    f"Estou ansiosa para continuar nossa jornada juntos! 💛"
                )
                await context.bot.send_message(chat_id=usuario.user_id, text=mensagem)
            except Exception as e:
                logging.error(f"Erro ao enviar notificação para {usuario.user_id}: {e}")
    finally:
        db.close()

# Função para traduzir texto para português
async def traduzir_para_portugues(texto):
    prompt = f"Translate the following English text to Portuguese. Keep it natural and conversational:\n\n{texto}"
    
    resposta = openai_client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )
    
    return resposta.choices[0].message.content.strip()

# Funções para análise de áudio
async def transcrever_audio(caminho):
    with open(caminho, "rb") as f:
        transcript = openai_client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="text"
        )
    return transcript

def ogg_para_mp3(ogg_path):
    mp3_path = ogg_path.replace(".ogg", ".mp3")
    AudioSegment.from_ogg(ogg_path).export(mp3_path, format="mp3")
    return mp3_path

async def corrigir_texto_por_partes(texto, nivel):
    frases = re.split(r'[.!?\n]', texto)
    frases = [f.strip() for f in frases if f.strip()]
    respostas = []
    explicacoes = []
    houve_erros = False

    for frase in frases:
        # Adapta a profundidade da correção com base no nível
        if nivel == "beginner":
            prompt = (
                "You are an English teacher helping a BEGINNER student. "
                "TASK: Check if the sentence has grammar or spelling mistakes. "
                "If there are mistakes, provide the corrected version. "
                "If the sentence is correct, respond ONLY with 'CORRECT'. "
                "Then, if there are mistakes, IN A NEW LINE starting with 'EXPLANATION:', "
                "provide a SIMPLE, BASIC explanation IN PORTUGUESE about what was wrong. "
                "Remember this is for a BEGINNER, so focus on fundamental errors only.\n\n"
                "IMPORTANT: Your explanation MUST be in Portuguese, but provide the corrected sentence in English.\n\n"
                f"Student sentence: {frase}\n\n"
                "Your response:"
            )
        elif nivel == "intermediate":
            prompt = (
                "You are an English teacher helping an INTERMEDIATE student. "
                "TASK: Check if the sentence has grammar, vocabulary or syntax mistakes. "
                "If there are mistakes, provide the corrected version. "
                "If the sentence is correct, respond ONLY with 'CORRECT'. "
                "provide a SIMPLE, BASIC explanation IN PORTUGUESE about what was wrong. "
                "Then, if there are mistakes, IN A NEW LINE starting with 'EXPLANATION:', "
                "provide a concise explanation in Portuguese about what was wrong.\n\n"
                f"Student sentence: {frase}\n\n"
                "Your response:"
            )
        else:  # advanced
            prompt = (
                "You are an English teacher helping an ADVANCED student. "
                "TASK: Check if the sentence has grammar, vocabulary, idiom usage, or nuance mistakes. "
                "Suggest more natural or sophisticated alternatives even if technically correct. "
                "If there are mistakes, provide the corrected version. "
                "If the sentence is perfect and native-like, respond ONLY with 'CORRECT'. "
                "Then, if there are suggestions, IN A NEW LINE starting with 'EXPLANATION:', "
                "provide a SIMPLE, BASIC explanation IN PORTUGUESE about what was wrong. "
                "provide a detailed explanation in Portuguese about the nuances.\n\n"
                f"Student sentence: {frase}\n\n"
                "Your response:"
            )

        try:
            resposta = openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )
            resposta_completa = resposta.choices[0].message.content.strip()
            
            # Processar a resposta para extrair correção e explicação
            partes = resposta_completa.split("EXPLANATION:", 1)
            correcao = partes[0].strip()
            
            # Se houver explicação, guarde-a
            explicacao = partes[1].strip() if len(partes) > 1 else ""
            
            # Verificação mais rigorosa se a resposta indica que a frase está correta
            if correcao.upper() == "CORRECT" or correcao == frase:
                # A frase está correta, não fazer nada
                continue
            else:
                houve_erros = True
                respostas.append(f" {correcao}\n")
                if explicacao:
                    explicacoes.append(f"📝 {explicacao}\n")
        except Exception as e:
            logging.error(f"Erro ao processar frase: {frase}. Erro: {e}")
            continue  # Pular esta frase e continuar com as outras
    
    # Retornar resultados - certificar que temos algo válido para retornar
    if not houve_erros or not respostas:
        return "Perfect ✨", frases, []
    
    # Garantir que temos pelo menos uma resposta válida
    if not respostas:
        respostas = ["Não foi possível identificar correções específicas."]
        
    return "\n\n".join(respostas), frases, explicacoes

# Mensagem do sistema que define o comportamento da IA
system_message = """
Você é uma professora de inglês experiente, especializada em ensinar alunos brasileiros. Sua função é analisar a fala do aluno (em inglês) e oferecer uma correção clara e objetiva.

1. Corrija a frase do aluno, de forma objetiva ajustando:
   - Gramática
   - Vocabulário
   - Conjugação verbal
   - Estrutura da frase
   Use linguagem clara e objetiva. Para explicar, diga algo como: "Sua frase precisa de algumas correções:

⚠️ Use sempre essa **mesma frase corrigida** em todos os trechos do feedback. Não crie versões diferentes.

2. Liste de 1 a 4 palavras ou expressões mal pronunciadas ou com sotaque forte que afete a clareza. Analise a frase dita pelo aluno e forneça **apenas uma frase** com a correção natural e gramaticalmente correta. Use o seguinte formato:

1. Palavra: {{palavra dita pelo aluno}} (Em inglês)
2. Como foi pronunciada: {{forma percebida}}
3. Pronúncia correta: {{ex: /ˈæb.sə.luːt.li/}}
4. Dica prática: {{dica para melhorar articulação ou entonação}} (dica em português)

⚠️ Se o aluno tiver sotaque brasileiro ou britânico, mas a fala for compreensível, **não corrija**.
**Somente se não tiver palavras para correção** diga: A pronuncia das palavras está correta.

3. Escolha apenas **uma** forma corrigida da frase do aluno e use essa mesma versão ao longo de toda a explicação, inclusive na seção final de correção. Priorize estruturas naturais, comuns no inglês falado, considerando o nível do aluno.
Finalize com:
✅ Frase Corrigida: {{frase correta, natural e completa}} Apresente a frase corrigida completa conforme sua coreção.

4. Nunca traduza automaticamente frases em português. Se o áudio estiver em português, diga:
"Por favor, envie um áudio em inglês para que eu possa analisar sua fala."

⚠️ Muito importante: 
Nunca inclua frases genéricas ou exemplos externos como "Student sentence: ..." ou "Your response: ...".
Corrija **somente** a frase do aluno, sem comparações ou exemplos adicionais.

Seja clara, encorajadora e objetiva e envie a Frase corrigida somente uma vez no final.
"""

# Função que gera o prompt com base na transcrição
def gerar_prompt(transcricao, nivel):
    return f"""
🗣️ Esta foi a frase falada pelo aluno em inglês (nível {nivel}):

\"{transcricao.strip()}\"

Por favor, analise e corrija possíveis erros gramaticais, de vocabulário, de conjugação verbal e estrutura da frase.

Em seguida, identifique até 4 palavras ou expressões mal pronunciadas ou com forte sotaque brasileiro que afete a compreensão. Utilize o formato solicitado anteriormente para cada uma delas.

Finalize mostrando a frase corrigida com clareza, iniciando com: ✅ Frase Corrigida:

Importante: Se não tiver palavras mal pronunciadas para corrigir, só fale: A pronuncia das palavras está correta.
"""

# Função para detectar problemas de pronúncia
async def analisar_pronuncia(transcricao, audio_path, nivel):
    try:
        # Gera o prompt com base na transcrição
        user_prompt = gerar_prompt(transcricao, nivel)

        # Chamada à API da OpenAI
        modelo = "gpt-3.5-turbo"  
        response = openai_client.chat.completions.create(
            model=modelo,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=1000
        )

        # Conteúdo da resposta
        return response.choices[0].message.content

    except Exception as e:
        return f"❌ Erro ao processar a análise: {str(e)}"
    
# Função para recomendar material de estudo baseado nos erros
async def recomendar_material(user_id):
    # Buscar histórico de erros no banco de dados
    db = SessionLocal()
    try:
        historico = obter_historico_erros(db, user_id, limite=10)
        
        if len(historico) < 3:
            return "Keep practicing more to get personalized recommendations! 🌱"
        
        # Compilar erros
        erros = [erro for _, erro in historico]
        erros_texto = "\n".join(erros)
        
        # Obter nível do usuário
        perfil = obter_perfil(db, user_id)
        nivel = perfil.nivel if perfil else "intermediate"
        
        prompt = (
            f"You are an English teacher helping a {nivel} level student. "
            "Based on these errors the student made recently, recommend specific learning materials, "
            "videos, or exercises that would help them improve. Be specific and concise. "
            "Provide 2-3 recommendations maximum.\n\n"
            f"Recent errors:\n{erros_texto}"
        )
        
        resposta = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        
        return resposta.choices[0].message.content.strip()
    finally:
        db.close()

# Função para gerar áudio
def gerar_audio_fala(texto, slow=False):
    tts = gTTS(text=texto, lang="en", slow=slow)
    caminho = tempfile.mktemp(suffix=".mp3")
    tts.save(caminho)
    return caminho

# Função para conversar com base no tema e nível
async def conversar_sobre_tema(texto, tema, nivel):
    prompt = f"You are a friendly English conversation partner for a {nivel} level English learner. The conversation theme is '{TEMAS.get(tema, 'general conversation')}'. Based on their message: '{texto}', respond in a natural, engaging way that's appropriate for their level. Be brief but conversational. Avoid complex language for beginners, use moderate vocabulary for intermediate learners, and feel free to use more sophisticated expressions for advanced learners."
    
    resposta = openai_client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8
    )
    
    return resposta.choices[0].message.content.strip()

async def puxar_conversa(texto, tema, nivel):
    prompt = f"You are a friendly English conversation partner for a {nivel} level English learner. The conversation theme is '{TEMAS.get(tema, 'general conversation')}'. Based on their message: '{texto}', ask a follow-up question that's appropriate for their level to keep the conversation going. Make sure your question is friendly, engaging, and not too complex for their level."
    
    resposta = openai_client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8
    )
    
    return resposta.choices[0].message.content.strip()

# Função para escolher pergunta temática
def escolher_proxima_pergunta(user_id, tema=None):
    # Criar uma sessão do banco de dados
    db = SessionLocal()
    try:
        # Se não especificou tema, obter do perfil
        if not tema:
            perfil = obter_perfil(db, user_id)
            tema = perfil.objetivo if perfil and perfil.objetivo else "daily_life"
        
        # Obter perguntas já usadas para este tema
        perguntas_usadas = obter_perguntas_usadas(db, user_id, tema)
        perguntas_tema = perguntas_por_tema.get(tema, perguntas_por_tema["daily_life"])
        
        # Filtrar perguntas não usadas
        restantes = list(set(perguntas_tema) - set(perguntas_usadas))
        if not restantes:
            # Se todas as perguntas do tema foram usadas, usar todas novamente
            restantes = perguntas_tema
        
        # Escolher pergunta aleatória
        pergunta = random.choice(restantes)
        
        # Registrar a pergunta usada
        registrar_pergunta(db, user_id, pergunta)
        
        return pergunta
    finally:
        db.close()

# Função para processar os botões de tradução
async def traduzir_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    partes = query.data.split("_")
    if len(partes) >= 2 and partes[0] == "traducao":
        mensagem_id = partes[1]
        user_id = query.from_user.id
        
        # Verificar se temos a mensagem original
        if user_id in ultimas_mensagens and mensagem_id in ultimas_mensagens[user_id]:
            texto_original = ultimas_mensagens[user_id][mensagem_id]
            
            # Informar que está traduzindo
            await query.edit_message_caption(
                caption=f"💭 {texto_original}\n\n🔄 Traduzindo para português...",
                reply_markup=None
            )
            
            # Traduzir o texto
            traducao = await traduzir_para_portugues(texto_original)
            
            # Enviar a tradução
            keyboard = [
                [InlineKeyboardButton("🇺🇸 Mostrar original", callback_data=f"original_{mensagem_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_caption(
                caption=f"💭 {texto_original}\n\n🇧🇷 {traducao}",
                reply_markup=reply_markup
            )
        else:
            await query.edit_message_caption(
                caption="Desculpe, não consegui recuperar a mensagem original para tradução.",
                reply_markup=None
            )
    elif len(partes) >= 2 and partes[0] == "original":
        mensagem_id = partes[1]
        user_id = query.from_user.id
        
        # Mostrar mensagem original
        if user_id in ultimas_mensagens and mensagem_id in ultimas_mensagens[user_id]:
            texto_original = ultimas_mensagens[user_id][mensagem_id]
            
            keyboard = [
                [InlineKeyboardButton("🇧🇷 Traduzir para Português", callback_data=f"traducao_{mensagem_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_caption(
                caption=f"💭 {texto_original}",
                reply_markup=reply_markup
            )

async def exibir_historico(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if isinstance(update.callback_query, type(None)):
        user_id = update.effective_user.id
        is_command = True
    else:
        user_id = update.callback_query.from_user.id
        is_command = False
    
    # Buscar histórico no banco de dados
    db = SessionLocal()
    try:
        historico = obter_historico_erros(db, user_id, limite=5)
        
        if not historico:
            if is_command:
                await update.message.reply_text("📭 No corrections history found yet! Keep talking to build your progress!")
            else:
                await update.callback_query.edit_message_text(
                    "📭 No corrections history found yet! Keep talking to build your progress!",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_menu")]])
                )
            return
        
        resposta = "📚 **Your Recent Corrections**\n\n"
        for idx, (original, correcao) in enumerate(historico, 1):
            resposta += f"**{idx}.**\n🗣️ You: {original}\n Fixed: {correcao}\n\n"
        
        if is_command:
            await update.message.reply_text(resposta, parse_mode='Markdown')
        else:
            await update.callback_query.edit_message_text(
                resposta,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_menu")]]),
                parse_mode='Markdown'
            )
    finally:
        db.close()

async def comando_dicas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    recomendacoes = await recomendar_material(user_id)
    
    await update.message.reply_text(
        "📚 **Personalized Study Recommendations**\n\n" + recomendacoes,
        parse_mode='Markdown'
    )

async def comando_progresso(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Buscar dados no banco de dados
    db = SessionLocal()
    try:
        # Obter pontos, streak e contagens
        pontos = obter_pontos(db, user_id)
        streak = obter_streak(db, user_id)
        interacoes = obter_contador_interacoes(db, user_id)
        erros_count = db.query(HistoricoErros).filter(HistoricoErros.user_id == user_id).count()
        
        progresso_texto = (
            f"📊 **Your Progress Stats**\n\n"
            f"✨ Points: {pontos}\n"
            f"🔥 Streak: {streak} days\n"
            f"💬 Conversations: {interacoes}\n"
            f"📝 Corrections: {erros_count}\n\n"
        )
        
        # Verificar status da assinatura
        usuario = obter_usuario(db, user_id)
        if usuario and usuario.assinaturas_ativas and usuario.expiracao:
            data_formatada = usuario.expiracao.strftime("%d/%m/%Y")
            progresso_texto += f"🌟 Premium active until: {data_formatada}\n\n"
        
        if erros_count > 5:
            progresso_texto += "Your learning is looking great! Keep practicing regularly for best results! 🌱"
        else:
            progresso_texto += "Keep practicing to see more detailed progress stats! 🌱"
        
        await update.message.reply_text(progresso_texto, parse_mode='Markdown')
    finally:
        db.close()

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    try:
        await query.answer()
    except Exception as e:
        # Se não conseguir responder ao callback query, apenas registrar o erro e continuar
        logging.error(f"Erro ao responder callback query: {e}")
    
    user_id = query.from_user.id
    escolha = query.data
    
    # Garantir que o usuário não está em nenhum estágio de cadastro
    if user_id in estagio_usuario:
        del estagio_usuario[user_id]
    
    # Criar sessão do banco de dados
    db = SessionLocal()
    
    try:
        if escolha == "practice":
            # Mostrar opções de temas
            keyboard = []
            row = []
            
            for i, (tema_id, tema_nome) in enumerate(TEMAS.items()):
                emoji = "🌟" if i % 8 == 0 else "🔸" if i % 8 == 1 else "🎭" if i % 8 == 2 else "🍽️" if i % 8 == 3 else "🎬" if i % 8 == 4 else "📱" if i % 8 == 5 else "🏃" if i % 8 == 6 else "📚"
                row.append(InlineKeyboardButton(f"{emoji} {tema_nome}", callback_data=f"tema_{tema_id}"))
                
                if len(row) == 2 or i == len(TEMAS) - 1:
                    keyboard.append(row)
                    row = []
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "Choose a conversation theme you'd like to practice:",
                reply_markup=reply_markup
            )
            
            return TEMA

        elif escolha == "progress":
            # Mostrar progresso do usuário
            pontos = obter_pontos(db, user_id)
            streak = obter_streak(db, user_id)
            interacoes = obter_contador_interacoes(db, user_id)
            erros_count = db.query(HistoricoErros).filter(HistoricoErros.user_id == user_id).count()
            
            progresso_texto = (
                f"📊 **Your Progress Stats**\n\n"
                f"✨ Points: {pontos}\n"
                f"🔥 Streak: {streak} days\n"
                f"💬 Conversations: {interacoes}\n"
                f"📝 Corrections: {erros_count}\n\n"
            )
            
            # Verificar status da assinatura
            usuario = obter_usuario(db, user_id)
            if usuario and usuario.assinaturas_ativas and usuario.expiracao:
                data_formatada = usuario.expiracao.strftime("%d/%m/%Y")
                progresso_texto += f"🌟 Premium active until: {data_formatada}\n\n"
            
            if erros_count > 5:
                # Gerar gráfico de progresso
                progresso_texto += "Your learning is looking great! Keep practicing regularly for best results! 🌱"
            else:
                progresso_texto += "Keep practicing to see more detailed progress stats! 🌱"
            
            keyboard = [
                [InlineKeyboardButton("📜 Correction History", callback_data="history")],
                [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(progresso_texto, reply_markup=reply_markup, parse_mode='Markdown')
            
            return MENU

elif escolha == "tips":
            # Gerar dicas personalizadas
            recomendacoes = await recomendar_material(user_id)
            
            keyboard = [
                [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "📚 **Personalized Study Recommendations**\n\n" + recomendacoes,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
            return MENU

        elif escolha == "settings":
            # Mostrar configurações
            keyboard = [
                [InlineKeyboardButton("🔤 Change Level", callback_data="change_level")],
                [InlineKeyboardButton("👤 Change Name", callback_data="change_name")],
                [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "⚙️ **Settings**\n\nWhat would you like to change?",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
            return MENU
        
        elif escolha == "back_menu":
            # Voltar ao menu principal
            keyboard = [
                [InlineKeyboardButton("🎯 Start Practice", callback_data="practice")],
                [InlineKeyboardButton("📊 My Progress", callback_data="progress")],
                [InlineKeyboardButton("📚 Study Tips", callback_data="tips")],
                [InlineKeyboardButton("🔄 Change Settings", callback_data="settings")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Obter informações do usuário
            usuario = obter_usuario(db, user_id)
            perfil = obter_perfil(db, user_id)
            
            nome = usuario.nome if usuario else "there"
            nivel = perfil.nivel if perfil else "intermediate"
            
            await query.edit_message_text(
                f"Ótimo, {nome}! Ajustado para o {nivel}\n\n"
                "O que deseja agora?",
                reply_markup=reply_markup
            )
            
            return MENU
        
        elif escolha == "history":
            # Mostrar histórico de correções
            await exibir_historico(update, context)
            return MENU

elif escolha == "change_level":
            # Mudar nível
            keyboard = [
                [InlineKeyboardButton("👶 Beginner", callback_data="nivel_beginner")],
                [InlineKeyboardButton("👍 Intermediate", callback_data="nivel_intermediate")],
                [InlineKeyboardButton("🚀 Advanced", callback_data="nivel_advanced")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "Qual o seu nível de inglês?",
                reply_markup=reply_markup
            )
            
            return NIVEL
        
        elif escolha == "change_name":
            # Mudar nome
            await query.edit_message_text(
                "Por favor, envie o seu nome abaixo."
            )
            
            estagio_usuario[user_id] = NOME
            return NOME
        
        # Tratamento para callbacks de "nivel_X"
        elif escolha.startswith("nivel_"):
            nivel = escolha.split("_")[1]
            
            # Atualizar o nível no banco de dados
            atualizar_perfil(db, user_id, nivel=nivel)
            
            # Verificar se o usuário tem assinatura premium ativa
            tem_premium = verificar_assinatura_premium(db, user_id)
            
            # Buscar nome do usuário
            usuario = obter_usuario(db, user_id)
            nome = usuario.nome if usuario else "there"
            
            # Texto adicional para usuários premium
            texto_premium = ""
            if tem_premium:
                data_expiracao = usuario.expiracao.strftime("%d/%m/%Y")
                texto_premium = f"\n\n🌟 Você tem acesso premium ativo até {data_expiracao}!"
            
            # Mostrar o menu principal após a mudança de nível
            keyboard = [
                [InlineKeyboardButton("🎯 Start Practice", callback_data="practice")],
                [InlineKeyboardButton("📊 My Progress", callback_data="progress")],
                [InlineKeyboardButton("📚 Study Tips", callback_data="tips")],
                [InlineKeyboardButton("🔄 Change Settings", callback_data="settings")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"Great, {nome}! I'll adjust my feedback for {nivel} level speakers.{texto_premium}\n\n"
                "What would you like to do?",
                reply_markup=reply_markup
            )
            
            return MENU
        
        return MENU
    finally:
        db.close()

# Handlers para o bot
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Resetar o estado do usuário para iniciar fluxo
    estagio_usuario[user_id] = NOME
    
    # Verificar se existe usuário no banco
    db = SessionLocal()
    try:
        # Verificar se o usuário tem assinatura premium ativa
        premium_status = verificar_assinatura_premium(db, user_id)
    finally:
        db.close()
    
    await update.message.reply_text(
        "🌟 Welcome to Lana English 🧸 🌟\n"
        "Olá! Estou aqui para te ajudar a praticar inglês de forma leve e divertida, com conversas naturais! 🧸💬🇬🇧\n\n"
        "Antes de começarmos...\n\n"
         "Aqui são alguns Comandos pra você interagir:\n\n"
        "🧸 Comandos Básicos:\n"
        "• /start - Inicia ou reinicia o bot\n"
        "• /reset - Reseta seus dados\n"
        "• /cancel - Cancela o fluxo atual\n"
        "• /help - Mostra esta mensagem de ajuda\n"
        "• /theme - Altera o tema da conversa\n"
        "• /question - Novo tópico de conversa\n\n"
        
        "🧸 Comandos Avançados:\n"
        "• /progress -Progresso de aprendizagem\n"
        "• /history - Histórico de correções\n"
        "• /tips - Recomendações de estudo\n"
        "• /ativar [código] - Ativa sua assinatura premium\n\n"
        "💬 Agora...Qual o seu nome?\n\n"
    )
    
    return NOME

# NOVO! Função para exibir o menu principal (o comando /menu)
async def comando_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Verificar se o usuário já existe no banco de dados
    db = SessionLocal()
    try:
        usuario = obter_usuario(db, user_id)
        if not usuario:
            await update.message.reply_text(
                "Parece que você ainda não está cadastrado. Vamos começar com /start!"
            )
            return ConversationHandler.END
        
        # Obter informações do usuário
        perfil = obter_perfil(db, user_id)
        nome = usuario.nome if usuario else "there"
        nivel = perfil.nivel if perfil else "intermediate"
        
        # Mostrar o menu principal
        keyboard = [
            [InlineKeyboardButton("🎯 Start Practice", callback_data="practice")],
            [InlineKeyboardButton("📊 My Progress", callback_data="progress")],
            [InlineKeyboardButton("📚 Study Tips", callback_data="tips")],
            [InlineKeyboardButton("🔄 Change Settings", callback_data="settings")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"Olá, {nome}! (Nível atual: {nivel})\n\n"
            "O que você gostaria de fazer?",
            reply_markup=reply_markup
        )
        
        return MENU
    finally:
        db.close()

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Limpar o estágio atual do usuário
    if user_id in estagio_usuario:
        del estagio_usuario[user_id]
        await update.message.reply_text("Operação cancelada! O que você gostaria de fazer agora?")
    else:
        await update.message.reply_text("Não há nenhuma operação ativa para cancelar.")
    
    return ConversationHandler.END

async def resetar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Criar uma sessão do banco de dados
    db = SessionLocal()
    try:
        # Obter status de assinatura antes de resetar
        premium_status = verificar_assinatura_premium(db, user_id)
        
        # Remover perfil (mas manter usuário e assinatura)
        perfil = obter_perfil(db, user_id)
        if perfil:
            db.delete(perfil)
            db.commit()
        
        # Limpar estágio
        if user_id in estagio_usuario:
            del estagio_usuario[user_id]
        
        await update.message.reply_text(
            "Seus dados foram resetados com sucesso!\n"
            "Use /start para começar novamente."
        )
    finally:
        db.close()
    
    return ConversationHandler.END

async def nome_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    nome = update.message.text
    
    # Guardar o nome no banco de dados
    db = SessionLocal()
    try:
        # Atualizar/criar usuário
        atualizar_usuario(db, user_id, nome=nome)
    finally:
        db.close()
    
    # Limpar o estágio após processar o nome
    if user_id in estagio_usuario and estagio_usuario[user_id] == NOME:
        del estagio_usuario[user_id]
    
    # Perguntar sobre o nível
    keyboard = [
        [InlineKeyboardButton("👶 Beginner", callback_data="nivel_beginner")],
        [InlineKeyboardButton("👍 Intermediate", callback_data="nivel_intermediate")],
        [InlineKeyboardButton("🚀 Advanced", callback_data="nivel_advanced")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"Prazer te conhecer, {nome}! 😊\n\n"
        "Qual é o seu nível de inglês?",
        reply_markup=reply_markup
    )
    
    return NIVEL

async def nivel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    nivel = query.data.split("_")[1]
    
    # Guardar o nível no banco de dados
    db = SessionLocal()
    try:
        # Atualizar/criar perfil
        atualizar_perfil(db, user_id, nivel=nivel)
        
        # Verificar se o usuário tem assinatura premium ativa
        tem_premium = verificar_assinatura_premium(db, user_id)
        
        # Buscar nome do usuário
        usuario = obter_usuario(db, user_id)
        nome = usuario.nome if usuario else "there"
        
        # Texto adicional para usuários premium
        texto_premium = ""
        if tem_premium:
            data_expiracao = usuario.expiracao.strftime("%d/%m/%Y")
            texto_premium = f"\n\n🌟 Você tem acesso premium ativo até {data_expiracao}!"
    finally:
        db.close()
    
    # Garantir que o usuário não está mais no estágio de cadastro
    if user_id in estagio_usuario:
        del estagio_usuario[user_id]
    
    # Mostrar o menu principal
    keyboard = [
        [InlineKeyboardButton("🎯 Start Practice", callback_data="practice")],
        [InlineKeyboardButton("📊 My Progress", callback_data="progress")],
        [InlineKeyboardButton("📚 Study Tips", callback_data="tips")],
        [InlineKeyboardButton("🔄 Change Settings", callback_data="settings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"Great, {nome}! I'll adjust my feedback for {nivel} level speakers.{texto_premium}\n\n"
        "What would you like to do?",
        reply_markup=reply_markup
    )
    
    return MENU

# [...vários outros handlers omitidos para brevidade]

# Função principal (versão para webhook no Render)
def main():
    # Inicializar o banco de dados e criar tabelas
    engine = create_engine(db_url)
    Base.metadata.create_all(engine)
    
    # Migrar dados do JSON para o PostgreSQL
    migrar_dados_do_json()
    
    # URL do webhook fornecida pelo Render
    PORT = int(os.environ.get('PORT', 8080))
    WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
    
    # Criar aplicação
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # MODIFICADO: Tratar a possível ausência do JobQueue
    if application.job_queue is None:
        logging.warning("JobQueue não está disponível. As verificações automáticas de assinatura serão desativadas.")
    else:
        try:
            application.job_queue.run_daily(
                verificar_assinaturas_expiradas,
                time=time(hour=10, minute=0, second=0)
            )
            logging.info("Verificação diária de assinaturas agendada com sucesso.")
        except Exception as e:
            logging.error(f"Erro ao configurar job_queue: {e}")
    
    # Adicionar handlers de conversa
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            NOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, nome_handler)],
            NIVEL: [CallbackQueryHandler(nivel_handler, pattern="^nivel_")],
            MENU: [CallbackQueryHandler(menu_handler)],
            TEMA: [CallbackQueryHandler(tema_handler, pattern="^tema_")]
        },
        fallbacks=[CommandHandler("start", start)]
    )
    
    application.add_handler(conv_handler)
    
    # Adicionar comando handlers
    application.add_handler(CommandHandler("help", comando_ajuda))
    application.add_handler(CommandHandler("theme", comando_tema))
    application.add_handler(CommandHandler("question", comando_pergunta))
    application.add_handler(CommandHandler("progress", comando_progresso))
    application.add_handler(CommandHandler("history", exibir_historico))
    application.add_handler(CommandHandler("tips", comando_dicas))
    application.add_handler(CommandHandler("premium", comando_premium))
    application.add_handler(CommandHandler("liberar", comando_liberar))
    application.add_handler(CommandHandler("graph", comando_grafico))
    application.add_handler(CommandHandler("cancel", cancelar))
    application.add_handler(CommandHandler("reset", resetar))
    application.add_handler(CommandHandler("ativar", comando_ativar))
    application.add_handler(CommandHandler("status", comando_status))
    application.add_handler(CommandHandler("resetarquel", resetarquel))
    application.add_handler(CommandHandler("meuid", meuid))
    # NOVO: Adicionar handler para o comando /menu
    application.add_handler(CommandHandler("menu", comando_menu))
    
    # Adicionar handlers de mensagem
    application.add_handler(MessageHandler(filters.VOICE, tratar_audio))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, tratar_texto))
    
    # Adicionar handler para callback queries para tradução
    application.add_handler(CallbackQueryHandler(traduzir_handler, pattern="^traducao_|^original_"))
    
    # Adicionar handler para callback queries dos temas
    application.add_handler(CallbackQueryHandler(tema_handler, pattern="^tema_"))
    
    # Handler genérico para outros callback queries
    application.add_handler(CallbackQueryHandler(menu_handler))
    
    # Configurar e iniciar o webhook
    if WEBHOOK_URL:
        # Modo webhook para Render
        logging.info(f"Iniciando bot com webhook: {WEBHOOK_URL}")
        
        # Configurar webhook e iniciar o servidor
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path="webhook",
            webhook_url=WEBHOOK_URL
        )
    else:
        # Fallback para polling (para desenvolvimento local)
        logging.info("WEBHOOK_URL não configurada. Usando polling (modo de desenvolvimento)")
        try:
            # Primeiro limpar webhooks de forma síncrona
            import requests
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook?drop_pending_updates=true"
            requests.get(url)
        except:
            logging.warning("Não foi possível limpar webhook via HTTP")
        
        # Iniciar bot com polling
        application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
