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
import hashlib
import time
import boto3
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

# Função para corrigir texto com base no nível
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
Nunca inclua frases genéricas ou exemplos externos como “Student sentence: ...” ou “Your response: ...”.
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


# Configurar diretório de cache
CACHE_DIR = os.path.join(tempfile.gettempdir(), "audio_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

def gerar_audio_fala(texto, slow=True):
    try:
        # Verificar se temos as credenciais AWS
        aws_key = os.getenv("AWS_ACCESS_KEY_ID")
        aws_secret = os.getenv("AWS_SECRET_ACCESS_KEY")
        
        if aws_key and aws_secret:
            # Usar Amazon Polly
            polly_client = boto3.client(
                'polly',
                aws_access_key_id=aws_key,
                aws_secret_access_key=aws_secret,
                region_name='us-east-1'
            )
            
            ssml_texto = f"<speak><prosody rate='slow' pitch='-2%' volume='medium'>{texto}</prosody></speak>"

            response = polly_client.synthesize_speech(
                Text=ssml_texto,
                TextType='ssml',
                OutputFormat='mp3',
                VoiceId='Salli',
                Engine='standard'
            )

            caminho = tempfile.mktemp(suffix=".mp3")
            
            with open(caminho, 'wb') as file:
                file.write(response['AudioStream'].read())
            
            return caminho
        else:
            # Fallback para gTTS se não tiver credenciais AWS
            return gerar_audio_com_gtts(texto, slow)
    except Exception as e:
        logging.error(f"Erro ao gerar áudio com Polly: {e}")
        # Fallback para gTTS como backup
        return gerar_audio_com_gtts(texto, slow)

# Mantenha a função original como fallback
def gerar_audio_com_gtts(texto, slow=False):
    # Implementar retry com backoff
    max_tentativas = 3
    for tentativa in range(1, max_tentativas + 1):
        try:
            tts = gTTS(text=texto, lang="en", slow=slow)
            caminho = tempfile.mktemp(suffix=".mp3")
            tts.save(caminho)
            return caminho
        except Exception as e:
            logging.warning(f"Erro ao gerar áudio (tentativa {tentativa}/{max_tentativas}): {e}")
            if tentativa < max_tentativas:
                tempo_espera = tentativa * 2  # backoff exponencial
                logging.info(f"Aguardando {tempo_espera}s antes da próxima tentativa...")
                time.sleep(tempo_espera)
            else:
                logging.error(f"Falha ao gerar áudio após {max_tentativas} tentativas: {e}")
                raise

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
        
        return MENU
    finally:
        db.close()

async def comando_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Criar sessão do banco de dados
    db = SessionLocal()
    
    try:
        # Obter informações do usuário
        usuario = obter_usuario(db, user_id)
        perfil = obter_perfil(db, user_id)
        
        # Verificar se o usuário está cadastrado
        if not usuario:
            await update.message.reply_text(
                "Parece que você ainda não se cadastrou. Vamos começar?\n\n"
                "Por favor, use o comando /start para iniciar o cadastro."
            )
            return ConversationHandler.END
        
        nome = usuario.nome if usuario else "there"
        nivel = perfil.nivel if perfil and perfil.nivel else "intermediate"
        
        # Mostrar o menu principal
        keyboard = [
            [InlineKeyboardButton("🎯 Start Practice", callback_data="practice")],
            [InlineKeyboardButton("📊 My Progress", callback_data="progress")],
            [InlineKeyboardButton("📚 Study Tips", callback_data="tips")],
            [InlineKeyboardButton("🔄 Change Settings", callback_data="settings")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"Olá, {nome}! O que você gostaria de fazer?\n\n"
            f"Seu nível atual: {nivel}",
            reply_markup=reply_markup
        )
        
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
        "• /menu - Acessa o menu principal\n"
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
    try:
        await query.answer()  # Garantir que respondemos ao callback
    except Exception as e:
        logging.error(f"Erro ao responder callback query: {e}")
        
    user_id = query.from_user.id
    nivel = query.data.split("_")[1]
    
    logging.info(f"Alterando nível para usuário {user_id}: {nivel}")  # Log adicional
    
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
    
    try:
        await query.edit_message_text(
            f"Great, {nome}! I'll adjust my feedback for {nivel} level speakers.{texto_premium}\n\n"
            "What would you like to do?",
            reply_markup=reply_markup
        )
    except Exception as e:
        logging.error(f"Erro ao editar mensagem: {e}")
        # Tentar enviar uma nova mensagem como fallback
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=f"Great, {nome}! I'll adjust my feedback for {nivel} level speakers.{texto_premium}\n\n"
                 "What would you like to do?",
            reply_markup=reply_markup
        )
    
    return MENU

# Função para ativar premium com código
async def comando_ativar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not context.args:
        await update.message.reply_text("Por favor, envie o comando no formato:\n/ativar seu_codigo")
        return

    codigo = context.args[0]
    sucesso = False  # Flag de controle

    try:
        # Criar uma sessão do banco de dados
        db = SessionLocal()
        try:
            # Verificar se o código já foi usado por outra pessoa
            codigo_usado_por = verificar_codigo_usado(db, codigo)
            if codigo_usado_por and codigo_usado_por != user_id:
                await update.message.reply_text("⚠️ Este código já está sendo usado por outro usuário.")
                return

            # Ler os dados da planilha
            resposta = requests.get(URL_PLANILHA)
            resposta.raise_for_status()
            dados_csv = resposta.content.decode('utf-8')
            leitor_csv = csv.reader(StringIO(dados_csv))
            lista_linhas = list(leitor_csv)

            # Extrair os códigos válidos (coluna F = índice 5)
            codigos_validos = [linha[5] for linha in lista_linhas[1:] if len(linha) >= 6]

            if codigo in codigos_validos:
                # Ativar assinatura no banco de dados
                data_expiracao = ativar_assinatura(db, user_id, codigo, dias=30)
                
                # Enviar mensagem de boas-vindas premium
                data_expiracao_formatada = data_expiracao.strftime("%d/%m/%Y")
                await update.message.reply_text(
                    "✨ *Acesso Premium Ativado!* ✨\n\n"
                    "Uhuuul! Agora você faz parte do *clube dos fluentes* 🧸💬\n"
                    "Pode treinar seu inglês comigo sem limites: *correções*, *conversas* e *muito aprendizado* te esperando! 🚀\n\n"
                    f"Sua assinatura é válida até: *{data_expiracao_formatada}*\n\n"
                    "Tô MUITO feliz de ter você aqui. *Bora evoluir juntos?* 💛\n\n"
                    "📌 *Comandos úteis:*\n"
                    "`/ativar [código]` – Ativa a assinatura com o código recebido\n"
                    "`/status` – Mostra o status atual da sua assinatura\n"
                    "`/premium` – Exibe informações sobre os benefícios premium",
                    parse_mode='Markdown'
                )

                sucesso = True  # tudo certo, não mostra mensagem de erro depois

            else:
                await update.message.reply_text("⚠️ Código inválido. Verifique se digitou corretamente.")

        finally:
            db.close()
    except Exception as e:
        print("Erro ao acessar a planilha:", e)
        if not sucesso:
            await update.message.reply_text("❌ Ocorreu um erro ao verificar o código. Tente novamente mais tarde.")


# Comando secreto para resetar a assinatura da Raquel (dev)
async def resetarquel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Substitua pelo seu ID real se quiser travar só pra você
    if user_id != 7577122726:  # << substitua esse número pelo seu ID do Telegram
        await update.message.reply_text("❌ Você não tem permissão para usar esse comando.")
        return
    
    # Criar uma sessão do banco de dados
    db = SessionLocal()
    try:
        # Obter usuário
        usuario = obter_usuario(db, user_id)
        if usuario:
            # Desativar assinatura
            usuario.assinaturas_ativas = False
            usuario.expiracao = None
            db.commit()
            
            # Remover códigos utilizados
            codigos = db.query(CodigosUtilizados).filter(CodigosUtilizados.user_id == user_id).all()
            for codigo in codigos:
                db.delete(codigo)
            db.commit()
            
            await update.message.reply_text("🔄 Assinatura resetada com sucesso, Raquel! Pode testar tudo de novo 💛")
        else:
            await update.message.reply_text("⚠️ Usuário não encontrado no banco de dados.")
    finally:
        db.close()

async def comando_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    db = SessionLocal()
    try:
        usuario = obter_usuario(db, user_id)
        
        if usuario and usuario.assinaturas_ativas and usuario.expiracao:
            data_expiracao = usuario.expiracao
            agora = datetime.now()
            
            if data_expiracao > agora:
                dias_restantes = (data_expiracao - agora).days
                data_formatada = data_expiracao.strftime("%d/%m/%Y")
                
                await update.message.reply_text(
                    f"🌟 **Status da sua assinatura premium** 🌟\n\n"
                    f"• Status: ATIVO ✅\n"
                    f"• Validade: até {data_formatada}\n"
                    f"• Dias restantes: {dias_restantes} dias\n\n"
                    f"Aproveite todas as funcionalidades premium! 🧸💕",
                    parse_mode='Markdown'
                )
            else:
                # Assinatura expirada (isso não deveria acontecer pois verificamos na função verificar_acesso)
                # Atualizar o status no banco
                usuario.assinaturas_ativas = False
                db.commit()
                
                await update.message.reply_text(
                    "⚠️ Sua assinatura premium expirou.\n\n"
                    "Para continuar aproveitando todas as funcionalidades premium, renove sua assinatura:\n\n"
                    f'<a href="{LINK_PAGAMENTO}">👉 CLIQUE AQUI E ASSINE</a>\n\n'
                    "Depois de renovar, use o comando <b>/ativar</b> com o novo código recebido.",
                    parse_mode='HTML'
                )
        else:
            # Usuário não tem assinatura
            await update.message.reply_text(
                "🔒 Você ainda não tem uma assinatura premium ativa.\n\n"
                "Adquira acesso ilimitado e desbloqueie todas as funcionalidades:\n\n"
                f'<a href="{LINK_PAGAMENTO}">👉 CLIQUE AQUI E ASSINE</a>\n\n'
                "Após a compra, use o comando <b>/ativar [código]</b> com o código recebido.",
                parse_mode='HTML'
            )
    finally:
        db.close()


async def comando_liberar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Verificar se é o administrador (substitua pelo seu user_id)
    if user_id != 123456789:  # Substitua pelo seu user_id do Telegram
        await update.message.reply_text("Você não tem permissão para usar este comando.")
        return
    
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Uso: /liberar [user_id] [dias]")
        return
    
    try:
        target_id = int(context.args[0])
        dias = int(context.args[1])
        
        db = SessionLocal()
        try:
            # Configurar uma assinatura manual
            data_expiracao = ativar_assinatura(db, target_id, "ADMIN_MANUAL", dias)
            
            data_formatada = data_expiracao.strftime("%d/%m/%Y")
            await update.message.reply_text(f"Usuário {target_id} liberado com sucesso até {data_formatada}!")
        finally:
            db.close()
    except ValueError:
        await update.message.reply_text("ID de usuário ou número de dias inválido.")

# Função geradora de gráficos
async def gerar_grafico_progresso(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    db = SessionLocal()
    try:
        # Verificar se há registros suficientes
        erros_count = db.query(HistoricoErros).filter(HistoricoErros.user_id == user_id).count()
        if erros_count < 5:
            await update.message.reply_text("You need at least 5 conversation records to generate a progress graph.")
            return
        
        # Dados para o gráfico
        interacoes = obter_contador_interacoes(db, user_id)
        precisao = (1 - (erros_count / interacoes)) * 100 if interacoes > 0 else 0
        
        # Criar o gráfico
        plt.figure(figsize=(10, 6))
        plt.bar(['Interactions', 'Corrections', 'Accuracy (%)'], [interacoes, erros_count, precisao])
        plt.title('Your English Learning Progress')
        plt.ylabel('Value')
        plt.grid(axis='y', linestyle='--', alpha=0.7)
        
        # Salvar o gráfico temporariamente
        graph_path = tempfile.mktemp(suffix='.png')
        plt.savefig(graph_path)
        plt.close()
        
        # Enviar o gráfico
        with open(graph_path, 'rb') as f:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=f,
                caption="📊 Your English progress graph. Keep practicing to improve!"
            )
        
        # Limpar arquivo temporário
        try:
            os.remove(graph_path)
        except:
            pass
    finally:
        db.close()

# Comando para gerar gráfico
async def comando_grafico(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await gerar_grafico_progresso(update, context)

async def meuid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text(f"Seu ID de usuário é: {user_id}")

async def comando_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Verificar se o usuário já tem premium ativo
    db = SessionLocal()
    try:
        tem_premium = verificar_assinatura_premium(db, user_id)
        if tem_premium:
            usuario = obter_usuario(db, user_id)
            data_expiracao = usuario.expiracao.strftime("%d/%m/%Y")
            await update.message.reply_text(
                f"🌟Você já tem acesso premium ativo!🌟\n\n"
                f"Sua assinatura é válida até: *{data_expiracao}*\n\n"
                f"Aproveite todos os recursos exclusivos da Lana English! 🧸💕",
                parse_mode='Markdown'
            )
            return
    finally:
        db.close()
    
    # Se não tem premium, mostrar informações sobre a assinatura
    premium_text = (
        "🧸 Ei! Acabou as interações grátis com a Lana English.\n"
        "Tô amando ver sua evolução no inglês! 💬✨\n"
        "Que tal desbloquear o acesso completo e continuar treinando comigo sem limites?\n\n"
        "Com o plano completo, você ganha:\n"
        "✅ Respostas ilimitadas\n"
        "✅ Correções personalizadas\n"
        "✅ Dicas exclusivas a cada áudio\n"
        "✅ Treinos de conversação sem parar!\n\n"
        '<a href="https://pay.hotmart.com/C99134085F">👉 CLIQUE AQUI E ASSINE</a>\n\n'
        "Depois de assinar, envie aqui na conversa /ativar e o código gerado após o pagamento.\n\n"
        "📌 Ex: /ativar HP18060709281022, o seu acesso Premium será liberado!\n\n"
        "Te espero do outro lado com muito vocabulário, fluência e aquele abraço de ursa! 🐻💖.\n\n"
    )

    await update.message.reply_text(premium_text, parse_mode='HTML')

async def comando_tema(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
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
    
    await update.message.reply_text(
        "Choose a conversation theme you'd like to practice:",
        reply_markup=reply_markup
    )
    
    return TEMA

async def tema_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    tema = query.data.split("_")[1]
    
    # Guardar o tema escolhido no banco de dados
    db = SessionLocal()
    try:
        # Atualizar/criar perfil com o tema atual
        perfil = obter_perfil(db, user_id)
        if perfil:
            perfil.objetivo = tema  # Usando o campo objetivo para armazenar o tema atual
            db.commit()
        else:
            criar_perfil(db, user_id, objetivo=tema)
        
        # Obter nível do usuário
        nivel = perfil.nivel if perfil else "intermediate"
        
        # Registrar a pergunta no banco de dados
        pergunta = escolher_proxima_pergunta(user_id, tema)
        registrar_pergunta(db, user_id, pergunta)
    finally:
        db.close()
    
    # Iniciar a prática
    tema_nome = TEMAS.get(tema, "Conversation")
    
    # Gerar áudio da pergunta
    caminho_audio = gerar_audio_fala(pergunta, slow=(nivel == "beginner"))
    
    with open(caminho_audio, "rb") as audio_file:
        mensagem = await context.bot.send_voice(chat_id=query.message.chat_id, voice=audio_file)
    
    # Salvar a mensagem para posterior tradução
    if user_id not in ultimas_mensagens:
        ultimas_mensagens[user_id] = {}
    ultimas_mensagens[user_id][str(mensagem.message_id)] = pergunta
    
    # Adicionar botão de tradução
    keyboard = [
        [InlineKeyboardButton("🇧🇷 Traduzir para Português", callback_data=f"traducao_{mensagem.message_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await context.bot.edit_message_reply_markup(
        chat_id=query.message.chat_id,
        message_id=mensagem.message_id,
        reply_markup=reply_markup
    )
    
    await query.edit_message_text(
        f"🎙️ Vamos praticar {tema_nome}!\n\n"
        f"Vou fazer perguntas sobre este tópico. Responda com uma mensagem de voz para praticar a fala.\n\n"
        f"Tente responder por áudio, se não conseguir você também pode enviar em texto. Não se preocupe se errar, estou aqui para ajudar você a evoluir!🧸❤️\n\n"
        f"💬 {pergunta}"
    )
    
    return ConversationHandler.END

async def comando_pergunta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not verificar_acesso(user_id):
        # Verificar se o usuário tinha uma assinatura que expirou
        db = SessionLocal()
        try:
            codigos = db.query(CodigosUtilizados).filter(CodigosUtilizados.user_id == user_id).first()
            if codigos:
                await update.message.reply_text(
                    "Ei! Percebi que sua assinatura premium expirou. 🧸\n\n"
                    "Para continuar aproveitando todas as funcionalidades ilimitadas, renove sua assinatura:\n\n"
                    f"{LINK_PAGAMENTO}\n\n"
                    "Depois de renovar, use o comando /ativar com o novo código recebido.\n\n"
                    "Estou ansiosa para continuar nosso aprendizado juntos! 💛"
                )
            else:
                await update.message.reply_text(
                    "⏰ Você atingiu seu limite diário de prática gratuita.\n\n"
                    "Para acesso ilimitado, atualize para nosso plano premium!\n\n"
                    f"[Fazer Upgrade Agora]({LINK_PAGAMENTO})",
                    parse_mode='Markdown'
                )
        finally:
            db.close()
        return
    
    # Obter tema atual
    db = SessionLocal()
    try:
        perfil = obter_perfil(db, user_id)
        tema_atual = perfil.objetivo if perfil and perfil.objetivo else "daily_life"
        nivel = perfil.nivel if perfil and perfil.nivel else "intermediate"
    finally:
        db.close()
    
    # Escolher próxima pergunta
    pergunta = escolher_proxima_pergunta(user_id, tema_atual)
    
    # Gerar áudio da pergunta
    caminho_audio = gerar_audio_fala(pergunta, slow=(nivel == "beginner"))
    
    with open(caminho_audio, "rb") as audio_file:
        mensagem = await context.bot.send_voice(chat_id=update.effective_chat.id, voice=audio_file)
    
    # Salvar a mensagem para posterior tradução
    if user_id not in ultimas_mensagens:
        ultimas_mensagens[user_id] = {}
    ultimas_mensagens[user_id][str(mensagem.message_id)] = pergunta
    
    # Adicionar botão de tradução
    keyboard = [
        [InlineKeyboardButton("🇧🇷 Traduzir para Português", callback_data=f"traducao_{mensagem.message_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await context.bot.edit_message_reply_markup(
        chat_id=update.effective_chat.id,
        message_id=mensagem.message_id,
        reply_markup=reply_markup
    )
    
    await update.message.reply_text(f"💬 {pergunta}")
    
    # Limpar arquivo temporário
    try:
        os.remove(caminho_audio)
    except:
        pass

async def comando_ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🌟 **Lana English Practice Bot Help** 🌟\n\n"
        "Aqui são alguns Comandos pra você interagir:\n\n"
        "🧸 Comandos Básicos:\n"
        "• /start - Inicia ou reinicia o bot\n"
        "• /menu - Acessa o menu principal\n"
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
        
        "**How to Practice:**\n"
        "1. Send me voice messages to practice speaking\n"
        "2. Or send text messages for writing practice\n"
        "3. I'll correct your English and provide helpful tips\n"
        "4. Respond to keep the conversation going\n\n"
        
        "Remember, consistent practice is key to improving your English! 🌱"
    )
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

# Handler para mensagens de texto
async def tratar_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    texto = update.message.text
    
    # Verificar se tem um fluxo ativo de cadastro
    if user_id in estagio_usuario:
        # Se o usuário estiver no estágio de nome, processar o nome
        if estagio_usuario[user_id] == NOME:
            await nome_handler(update, context)
            return
    
    # Verificar se o usuário já foi cadastrado
    db = SessionLocal()
    try:
        usuario = obter_usuario(db, user_id)
        if not usuario:
            await update.message.reply_text(
                "Parece que você ainda não se cadastrou. Vamos começar?\n\n"
                "Por favor, me diga seu nome:"
            )
            estagio_usuario[user_id] = NOME
            return
        
        # Verificar se o usuário tem acesso premium ou está dentro da cota gratuita
        if not verificar_acesso(user_id):
            # Verificar se o usuário tinha uma assinatura que expirou
            codigos = db.query(CodigosUtilizados).filter(CodigosUtilizados.user_id == user_id).first()
            if codigos:
                await update.message.reply_text(
                    "Ei! Percebi que sua assinatura premium expirou. 🧸\n\n"
                    "Para continuar aproveitando todas as funcionalidades ilimitadas, renove sua assinatura:\n\n"
                    f"{LINK_PAGAMENTO}\n\n"
                    "Depois de renovar, use o comando /ativar com o novo código recebido.\n\n"
                    "Estou ansiosa para continuar nosso aprendizado juntos! 💛"
                )
            else:
                premium_text = (
                    "🧸 Ei! Acabou as interações grátis com a Lana English.\n"
                    "Tô amando ver sua evolução no inglês! 💬✨\n"
                    "Que tal desbloquear o acesso completo e continuar treinando comigo sem limites?\n\n"
                    "Com o plano completo, você ganha:\n"
                    "✅ Respostas ilimitadas\n"
                    "✅ Correções personalizadas\n"
                    "✅ Dicas exclusivas a cada áudio\n"
                    "✅ Treinos de conversação sem parar!\n\n"
                    '<a href="https://pay.hotmart.com/C99134085F">👉 CLIQUE AQUI E ASSINE</a>\n\n'
                    "Depois de assinar, envie aqui na conversa /ativar e o código gerado após o pagamento.\n\n"
                    "📌 Ex: /ativar HP14506899281022, o seu acesso Premium será liberado!\n\n"
                    "Te espero do outro lado com muito vocabulário, fluência e aquele abraço de ursa! 🐻💖.\n\n"
                )

                await update.message.reply_text(premium_text, parse_mode='HTML')
            return

        # Incrementar contadores - registrar interação
        adicionar_interacao(db, user_id, "texto", texto)
        
        # Obter dados do usuário
        perfil = obter_perfil(db, user_id)
        nivel = perfil.nivel if perfil and perfil.nivel else "intermediate"
        tema_atual = perfil.objetivo if perfil and perfil.objetivo else "daily_life"
    finally:
        db.close()
    
    # Informar que está processando
    processando_msg = await update.message.reply_text("🔄 Analisando seu texto...")
    
    try:
        # Corrigir o texto
        correcoes, frases_originais, explicacoes = await corrigir_texto_por_partes(texto, nivel)
    
        # Verificação adicional para garantir que temos uma resposta válida
        if correcoes is None:
            correcoes = "Não foi possível realizar a correção."
            frases_originais = []
            explicacoes = []
    
        # Adicionar pontos
        pontos = 3  # Pontos base por interação de texto (menor que áudio)
        if correcoes == "Perfect ✨":
            pontos += 2  # Bônus para resposta perfeita
    
        pontos_totais = adicionar_pontos(user_id, pontos)
    
        # Salvar erros no histórico se houver
        if correcoes != "Perfect ✨" and frases_originais and explicacoes:
            db = SessionLocal()
            try:
                # Adicionar cada erro ao banco de dados
                for i, frase in enumerate(frases_originais):
                    if i < len(explicacoes):
                        adicionar_erro(db, user_id, frase, explicacoes[i])
            finally:
                db.close()
    
        # Preparar resposta
        if correcoes == "Perfect ✨":
            resposta = "✅ Great job! Sua mensagem está perfeita!🧸🎉\n"
        else:
            resposta = "📝 Aqui estão algumas correções:\n" + correcoes 
            if explicacoes:
                resposta += "\n".join(explicacoes[:2]) + "\n\n"
        
        # Fazer uma pergunta para continuar a conversa
        resposta_conversa = await conversar_sobre_tema(texto, tema_atual, nivel)
        
        # Deletar mensagem de processamento
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=processando_msg.message_id)
        
        # Enviar feedback
        await update.message.reply_text(resposta)
        
        # Enviar resposta de conversa em áudio com botão de tradução
        caminho_resposta = gerar_audio_fala(resposta_conversa, slow=(nivel == "beginner"))
        with open(caminho_resposta, "rb") as audio_file:
            mensagem = await context.bot.send_voice(chat_id=update.effective_chat.id, voice=audio_file)
        
        # Salvar a mensagem para posterior tradução
        if user_id not in ultimas_mensagens:
            ultimas_mensagens[user_id] = {}
        ultimas_mensagens[user_id][str(mensagem.message_id)] = resposta_conversa
        
        # Adicionar botão de tradução
        keyboard = [
            [InlineKeyboardButton("🇧🇷 Traduzir para Português", callback_data=f"traducao_{mensagem.message_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.edit_message_reply_markup(
            chat_id=update.effective_chat.id,
            message_id=mensagem.message_id,
            reply_markup=reply_markup
        )
        
        # Obter dados atualizados do streak
        db = SessionLocal()
        try:
            streak_atual = obter_streak(db, user_id)
        finally:
            db.close()
        
        # Enviar texto da resposta
        await update.message.reply_text(
            f"🏆 +{pontos} points! (Total: {pontos_totais})\n"
            f"🔥 Day streak: {streak_atual}"
        )
        
        # Limpar arquivos temporários
        try:
            os.remove(caminho_resposta)
        except:
            pass
        
    except Exception as e:
        logging.error(f"Erro no processamento de texto: {e}")
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=processando_msg.message_id)
        await update.message.reply_text(
            "😔 Desculpe, tive problemas ao processar sua mensagem. Por favor, tente novamente."
        )

async def tratar_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Verificar se tem um fluxo ativo de cadastro
    if user_id in estagio_usuario:
        # Se o usuário estiver no estágio de nome, processar o nome
        if estagio_usuario[user_id] == NOME:
            await update.message.reply_text(
                "Por favor, digite seu nome em texto, não em áudio."
            )
            return
    
    # Verificar se o usuário já foi cadastrado
    db = SessionLocal()
    try:
        usuario = obter_usuario(db, user_id)
        if not usuario:
            await update.message.reply_text(
                "Parece que você ainda não se cadastrou. Vamos começar?\n\n"
                "Por favor, me diga seu nome:"
            )
            estagio_usuario[user_id] = NOME
            return
        
        # Verificar se o usuário tem acesso premium ou está dentro da cota gratuita
        if not verificar_acesso(user_id):
            # Verificar se o usuário tinha uma assinatura que expirou
            codigos = db.query(CodigosUtilizados).filter(CodigosUtilizados.user_id == user_id).first()
            if codigos:
                await update.message.reply_text(
                    "Ei! Percebi que sua assinatura premium expirou. 🧸\n\n"
                    "Para continuar aproveitando todas as funcionalidades ilimitadas, renove sua assinatura:\n\n"
                    f"{LINK_PAGAMENTO}\n\n"
                    "Depois de renovar, use o comando /ativar com o novo código recebido.\n\n"
                    "Estou ansiosa para continuar nosso aprendizado juntos! 💛"
                )
            else:
                premium_text = (
                    "🧸 Ei! Acabou as interações grátis com a Lana English.\n"
                    "Tô amando ver sua evolução no inglês! 💬✨\n"
                    "Que tal desbloquear o acesso completo e continuar treinando comigo sem limites?\n\n"
                    "Com o plano completo, você ganha:\n"
                    "✅ Respostas ilimitadas\n"
                    "✅ Correções personalizadas\n"
                    "✅ Dicas exclusivas a cada áudio\n"
                    "✅ Treinos de conversação sem parar!\n\n"
                    '<a href="https://pay.hotmart.com/C99134085F">👉 CLIQUE AQUI E ASSINE</a>\n\n'
                    "Depois de assinar, envie aqui na conversa /ativar e o código gerado após o pagamento.\n\n"
                    "📌 Ex: /ativar HP16060606081022, o seu acesso Premium será liberado!\n\n"
                    "Te espero do outro lado com muito vocabulário, fluência e aquele abraço de ursa! 🐻💖.\n\n"
                )

                await update.message.reply_text(premium_text, parse_mode='HTML')
            return

        # Incrementar contadores - registrar interação
        adicionar_interacao(db, user_id, "audio")
        
        # Obter dados do usuário
        perfil = obter_perfil(db, user_id)
        nivel = perfil.nivel if perfil and perfil.nivel else "intermediate"
        tema_atual = perfil.objetivo if perfil and perfil.objetivo else "daily_life"
    finally:
        db.close()

    # Baixar áudio
    file = await context.bot.get_file(update.message.voice.file_id)
    ogg_path = tempfile.mktemp(suffix=".ogg")
    await file.download_to_drive(ogg_path)
    
    # Converter para MP3
    mp3_path = ogg_para_mp3(ogg_path)
    
    # Informar que está processando
    processando_msg = await update.message.reply_text("🎧 Processando seu áudio...")
    
    try:
        # Transcrever áudio
        transcricao = await transcrever_audio(mp3_path)
        
        # Corrigir o texto transcrito
        correcoes, frases_originais, explicacoes = await corrigir_texto_por_partes(transcricao, nivel)
        
        # Analisar pronúncia
        analise_pronuncia = await analisar_pronuncia(transcricao, mp3_path, nivel)
        
        # Adicionar pontos
        pontos = 5  # Pontos base por interação
        if correcoes == "Perfect ✨":
            pontos += 3  # Bônus para resposta perfeita
        
        pontos_totais = adicionar_pontos(user_id, pontos)
        
        # Salvar erros no histórico se houver
        if correcoes != "Perfect ✨" and frases_originais:
            db = SessionLocal()
            try:
                # Adicionar cada erro ao banco de dados
                for i, frase in enumerate(frases_originais):
                    if i < len(explicacoes):
                        adicionar_erro(db, user_id, frase, explicacoes[i])
            finally:
                db.close()
        
        # Preparar resposta
        resposta = f"🗣️ Você disse:\n{transcricao}\n"
        
        if correcoes == "Perfect ✨":
            resposta += "✅ Perfeito! Muito bem!🧸🎉\n"
        else:
            resposta += "📝 Aqui estão algumas correções:\n" + correcoes 
            if explicacoes:
                resposta += "\n".join(explicacoes[:2]) + "\n"
        
        # Adicionar feedback de pronúncia se não for perfeito
        if correcoes != "Perfect ✨":
            resposta += f"🗣️ Dicas de pronúncia:\n{analise_pronuncia}\n\n"
        
        # Fazer uma pergunta para continuar a conversa
        resposta_conversa = await conversar_sobre_tema(transcricao, tema_atual, nivel)
        
        # Editar mensagem de processamento
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=processando_msg.message_id)
        
        # Enviar feedback
        await update.message.reply_text(resposta)
        
        # Enviar resposta de conversa com botão de tradução
        caminho_resposta = gerar_audio_fala(resposta_conversa, slow=(nivel == "beginner"))
        
        with open(caminho_resposta, "rb") as audio_file:
            mensagem = await context.bot.send_voice(chat_id=update.effective_chat.id, voice=audio_file)
        
        # Salvar a mensagem para posterior tradução
        if user_id not in ultimas_mensagens:
            ultimas_mensagens[user_id] = {}
        ultimas_mensagens[user_id][str(mensagem.message_id)] = resposta_conversa
        
        # Adicionar botão de tradução
        keyboard = [
            [InlineKeyboardButton("🇧🇷 Traduzir para Português", callback_data=f"traducao_{mensagem.message_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.edit_message_reply_markup(
            chat_id=update.effective_chat.id,
            message_id=mensagem.message_id,
            reply_markup=reply_markup
        )
        
        # Obter dados atualizados do streak
        db = SessionLocal()
        try:
            streak_atual = obter_streak(db, user_id)
        finally:
            db.close()
        
        await update.message.reply_text(
            f"🏆 +{pontos} points! (Total: {pontos_totais})\n"
            f"🔥 Day streak: {streak_atual}"
        )
        
        # Limpar arquivos temporários
        try:
            os.remove(ogg_path)
            os.remove(mp3_path)
            os.remove(caminho_resposta)
        except:
            pass
        
    except Exception as e:
        logging.error(f"Erro no processamento de áudio: {e}")
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=processando_msg.message_id)
        await update.message.reply_text(
            "😔 Desculpe, tive dificuldades para processar seu áudio. Por favor, tente novamente."
        )

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
    application.add_handler(CommandHandler("menu", comando_menu))
    application.add_handler(CommandHandler("ativar", comando_ativar))
    application.add_handler(CommandHandler("status", comando_status))
    application.add_handler(CommandHandler("resetarquel", resetarquel))
    application.add_handler(CommandHandler("meuid", meuid))
    
    # Adicionar handlers de mensagem
    application.add_handler(MessageHandler(filters.VOICE, tratar_audio))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, tratar_texto))
    
    # Adicionar handler para callback queries para tradução
    application.add_handler(CallbackQueryHandler(traduzir_handler, pattern="^traducao_|^original_"))
    
    # Adicionar handler para callback queries dos temas
    application.add_handler(CallbackQueryHandler(tema_handler, pattern="^tema_"))
    
    # Handler genérico para outros callback queries
    application.add_handler(CallbackQueryHandler(menu_handler))

    # Adicione este padrão específico ao seu CallbackQueryHandler
    application.add_handler(CallbackQueryHandler(nivel_handler, pattern="^nivel_"))
    
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
