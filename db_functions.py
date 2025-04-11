# Funções para gerenciar o banco de dados PostgreSQL para o Lana English Bot

import logging
from datetime import datetime, timedelta
from sqlalchemy import create_engine, and_, or_, func, desc
from sqlalchemy.orm import sessionmaker
from models import (
    Base, Usuario, PerfilUsuario, HistoricoErros,
    PontosUsuario, StreakUsuario, UltimaInteracao,
    CodigosUtilizados, InteracoesUsuario, ConversasUsuario
)

def iniciar_bd(db_url):
    """Inicializa a conexão com o banco de dados."""
    engine = create_engine(db_url)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal

# Funções para gerenciar usuários

def obter_usuario(db, user_id):
    """Obtém um usuário pelo user_id do Telegram."""
    return db.query(Usuario).filter(Usuario.user_id == user_id).first()

def criar_usuario(db, user_id, nome=None, assinaturas_ativas=False, ativacao=None, expiracao=None, codigo=None):
    """Cria um novo usuário no banco de dados."""
    usuario = Usuario(
        user_id=user_id,
        nome=nome,
        assinaturas_ativas=assinaturas_ativas,
        ativacao=ativacao,
        expiracao=expiracao,
        codigo=codigo
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario

def atualizar_usuario(db, user_id, nome=None, assinaturas_ativas=None, ativacao=None, expiracao=None, codigo=None):
    """Atualiza os dados de um usuário existente."""
    usuario = obter_usuario(db, user_id)
    if not usuario:
        return criar_usuario(db, user_id, nome, assinaturas_ativas, ativacao, expiracao, codigo)
    
    if nome is not None:
        usuario.nome = nome
    if assinaturas_ativas is not None:
        usuario.assinaturas_ativas = assinaturas_ativas
    if ativacao is not None:
        usuario.ativacao = ativacao
    if expiracao is not None:
        usuario.expiracao = expiracao
    if codigo is not None:
        usuario.codigo = codigo
    
    db.commit()
    db.refresh(usuario)
    return usuario

# Funções para gerenciar perfis de usuário

def obter_perfil(db, user_id):
    """Obtém o perfil de um usuário."""
    return db.query(PerfilUsuario).filter(PerfilUsuario.user_id == user_id).first()

def criar_perfil(db, user_id, nivel=None, objetivo=None, idioma_base=None):
    """Cria um novo perfil para o usuário."""
    perfil = PerfilUsuario(
        user_id=user_id,
        nivel=nivel,
        objetivo=objetivo,
        idioma_base=idioma_base
    )
    db.add(perfil)
    db.commit()
    db.refresh(perfil)
    return perfil

def atualizar_perfil(db, user_id, nivel=None, objetivo=None, idioma_base=None):
    """Atualiza o perfil de um usuário existente."""
    perfil = obter_perfil(db, user_id)
    if not perfil:
        return criar_perfil(db, user_id, nivel, objetivo, idioma_base)
    
    if nivel is not None:
        perfil.nivel = nivel
    if objetivo is not None:
        perfil.objetivo = objetivo
    if idioma_base is not None:
        perfil.idioma_base = idioma_base
    
    db.commit()
    db.refresh(perfil)
    return perfil

# Funções para gerenciar pontos de usuário

def obter_pontos(db, user_id):
    """Obtém os pontos de um usuário."""
    pontos = db.query(PontosUsuario).filter(PontosUsuario.user_id == user_id).first()
    return pontos.pontos if pontos else 0

def adicionar_pontos_db(db, user_id, pontos_novos):
    """Adiciona pontos ao usuário e retorna o total atualizado."""
    pontos_usuario = db.query(PontosUsuario).filter(PontosUsuario.user_id == user_id).first()
    
    if pontos_usuario:
        pontos_usuario.pontos += pontos_novos
    else:
        pontos_usuario = PontosUsuario(user_id=user_id, pontos=pontos_novos)
        db.add(pontos_usuario)
    
    db.commit()
    atualizar_streak_db(db, user_id)
    return pontos_usuario.pontos

# Funções para gerenciar streak

def obter_streak(db, user_id):
    """Obtém o streak de dias consecutivos de um usuário."""
    streak = db.query(StreakUsuario).filter(StreakUsuario.user_id == user_id).first()
    return streak.dias_consecutivos if streak else 0

def atualizar_streak_db(db, user_id):
    """Atualiza o streak de dias consecutivos do usuário."""
    hoje = datetime.now().date()
    streak = db.query(StreakUsuario).filter(StreakUsuario.user_id == user_id).first()
    ultima = db.query(UltimaInteracao).filter(UltimaInteracao.user_id == user_id).first()
    
    # Registrar a interação atual
    if ultima:
        ultima_data = ultima.data.date() if ultima.data else hoje
        ultima.data = datetime.now()
    else:
        ultima = UltimaInteracao(user_id=user_id, data=datetime.now())
        db.add(ultima)
        ultima_data = hoje
    
    # Atualizar o streak
    if not streak:
        streak = StreakUsuario(user_id=user_id, dias_consecutivos=1, ultima_data=datetime.now())
        db.add(streak)
    else:
        # Se a última interação foi ontem, aumenta o streak
        if (hoje - ultima_data).days == 1:
            streak.dias_consecutivos += 1
            streak.ultima_data = datetime.now()
        # Se a última interação foi hoje, mantém o streak
        elif (hoje - ultima_data).days == 0:
            streak.ultima_data = datetime.now()
        # Se passou mais de um dia, reseta o streak
        else:
            streak.dias_consecutivos = 1
            streak.ultima_data = datetime.now()
    
    db.commit()
    return streak.dias_consecutivos

# Funções para gerenciar histórico de erros

def adicionar_erro(db, user_id, original, correcao, data=None):
    """Adiciona um erro ao histórico do usuário."""
    if data is None:
        data = datetime.now()
    
    erro = HistoricoErros(
        user_id=user_id,
        erro=f"Original: {original} | Correção: {correcao}",
        data=data
    )
    db.add(erro)
    db.commit()

def obter_historico_erros(db, user_id, limite=10):
    """Obtém os últimos erros do usuário."""
    erros = db.query(HistoricoErros).filter(
        HistoricoErros.user_id == user_id
    ).order_by(desc(HistoricoErros.data)).limit(limite).all()
    
    # Formatar os erros para compatibilidade com o formato anterior
    resultado = []
    for erro in erros:
        partes = erro.erro.split(" | Correção: ")
        if len(partes) == 2:
            original = partes[0].replace("Original: ", "")
            correcao = partes[1]
            resultado.append((original, correcao))
    
    return resultado

# Funções para gerenciar interações

def obter_contador_interacoes(db, user_id):
    """Obtém o número de interações do usuário."""
    interacoes = db.query(InteracoesUsuario).filter(
        InteracoesUsuario.user_id == user_id
    ).count()
    return interacoes

def adicionar_interacao(db, user_id, tipo, conteudo=None):
    """Registra uma nova interação do usuário."""
    interacao = InteracoesUsuario(
        user_id=user_id,
        tipo=tipo,
        conteudo=conteudo,
        data=datetime.now()
    )
    db.add(interacao)
    db.commit()

# Funções para gerenciar conversas (perguntas usadas)

def registrar_pergunta(db, user_id, mensagem):
    """Registra uma pergunta usada na conversa."""
    conversa = ConversasUsuario(
        user_id=user_id,
        mensagem=mensagem,
        resposta="",  # Não estamos guardando a resposta do usuário aqui
        data=datetime.now()
    )
    db.add(conversa)
    db.commit()

def obter_perguntas_usadas(db, user_id, tema=None):
    """Obtém as perguntas já usadas por um usuário em um tema."""
    query = db.query(ConversasUsuario.mensagem).filter(
        ConversasUsuario.user_id == user_id
    )
    
    # Se o tema for especificado, filtra por perguntas que contêm palavras-chave do tema
    if tema:
        palavras_chave = {
            "daily_life": ["routine", "morning", "daily", "day", "home", "office", "weekend"],
            "travel": ["travel", "destination", "trip", "vacation", "tourism", "beach", "mountain"],
            "business": ["work", "job", "skill", "meeting", "project", "career", "company"],
            "food": ["food", "cook", "dish", "meal", "recipe", "restaurant", "cuisine"],
            "entertainment": ["movie", "film", "actor", "series", "show", "cinema", "watch"],
            "technology": ["tech", "gadget", "device", "app", "computer", "phone", "digital"],
            "health": ["health", "exercise", "fitness", "workout", "diet", "active", "gym"],
            "education": ["learn", "school", "study", "class", "course", "language", "student"]
        }
        
        if tema in palavras_chave:
            # Construir a condição OR para cada palavra-chave
            filtros = []
            for palavra in palavras_chave[tema]:
                filtros.append(ConversasUsuario.mensagem.ilike(f"%{palavra}%"))
            
            query = query.filter(or_(*filtros))
    
    perguntas = [row[0] for row in query.all()]
    return perguntas

# Funções para gerenciar códigos usados

def verificar_codigo_usado(db, codigo):
    """Verifica se um código já foi usado e por qual usuário."""
    codigo_usado = db.query(CodigosUtilizados).filter(CodigosUtilizados.codigo == codigo).first()
    return codigo_usado.user_id if codigo_usado else None

def registrar_uso_codigo(db, user_id, codigo):
    """Registra o uso de um código de ativação."""
    codigo_usado = CodigosUtilizados(
        user_id=user_id,
        codigo=codigo,
        data_utilizacao=datetime.now()
    )
    db.add(codigo_usado)
    db.commit()

# Funções para verificar assinatura premium

def verificar_assinatura_premium(db, user_id):
    """Verifica se o usuário tem assinatura premium ativa."""
    usuario = obter_usuario(db, user_id)
    if not usuario:
        return False
    
    if usuario.assinaturas_ativas and usuario.expiracao:
        agora = datetime.now()
        if agora <= usuario.expiracao:
            return True
        else:
            # Se expirou, atualiza o status
            usuario.assinaturas_ativas = False
            db.commit()
    
    return False

def ativar_assinatura(db, user_id, codigo, dias=30):
    """Ativa a assinatura premium para um usuário."""
    data_ativacao = datetime.now()
    data_expiracao = data_ativacao + timedelta(days=dias)
    
    # Atualizar o usuário
    usuario = atualizar_usuario(
        db, 
        user_id, 
        assinaturas_ativas=True,
        ativacao=data_ativacao,
        expiracao=data_expiracao,
        codigo=codigo
    )
    
    # Registrar o uso do código
    registrar_uso_codigo(db, user_id, codigo)
    
    return data_expiracao

def listar_assinaturas_expiradas(db, horas=24):
    """Lista usuários cuja assinatura expirou nas últimas X horas."""
    agora = datetime.now()
    inicio_periodo = agora - timedelta(hours=horas)
    
    usuarios_expirados = db.query(Usuario).filter(
        and_(
            Usuario.assinaturas_ativas == True,
            Usuario.expiracao < agora,
            Usuario.expiracao > inicio_periodo
        )
    ).all()
    
    # Marcar como inativos
    for usuario in usuarios_expirados:
        usuario.assinaturas_ativas = False
    
    db.commit()
    return usuarios_expirados

# Função para migrar dados do JSON para o banco de dados (uso único)
def migrar_dados_json_para_db(db, dados_json):
    """Migra os dados do formato JSON para o banco de dados."""
    # Migra perfis de usuário
    for user_id_str, perfil in dados_json.get("perfil_usuario", {}).items():
        user_id = int(user_id_str)
        nome = perfil.get("nome", "")
        nivel = perfil.get("nivel", "intermediate")
        
        # Criar ou atualizar usuário
        atualizar_usuario(db, user_id, nome=nome)
        
        # Criar ou atualizar perfil
        atualizar_perfil(db, user_id, nivel=nivel)
    
    # Migra pontos
    for user_id_str, pontos in dados_json.get("pontos_usuario", {}).items():
        user_id = int(user_id_str)
        pontos_obj = db.query(PontosUsuario).filter(PontosUsuario.user_id == user_id).first()
        
        if pontos_obj:
            pontos_obj.pontos = pontos
        else:
            db.add(PontosUsuario(user_id=user_id, pontos=pontos))
    
    # Migra streak
    for user_id_str, dias in dados_json.get("streak_usuario", {}).items():
        user_id = int(user_id_str)
        streak_obj = db.query(StreakUsuario).filter(StreakUsuario.user_id == user_id).first()
        
        if streak_obj:
            streak_obj.dias_consecutivos = dias
        else:
            db.add(StreakUsuario(user_id=user_id, dias_consecutivos=dias))
    
    # Migra assinaturas ativas
    for user_id_str, assinatura in dados_json.get("assinaturas_ativas", {}).items():
        user_id = int(user_id_str)
        
        try:
            ativacao = datetime.fromisoformat(assinatura["ativacao"]) if isinstance(assinatura["ativacao"], str) else assinatura["ativacao"]
            expiracao = datetime.fromisoformat(assinatura["expiracao"]) if isinstance(assinatura["expiracao"], str) else assinatura["expiracao"]
            codigo = assinatura["codigo"]
            
            # Atualizar usuário com dados da assinatura
            atualizar_usuario(
                db, 
                user_id, 
                assinaturas_ativas=True,
                ativacao=ativacao,
                expiracao=expiracao,
                codigo=codigo
            )
            
            # Registrar código usado
            registrar_uso_codigo(db, user_id, codigo)
        except Exception as e:
            logging.error(f"Erro ao migrar assinatura para {user_id}: {e}")
    
    # Salvar alterações
    db.commit()
    logging.info("Migração de dados JSON para o banco de dados concluída!")
