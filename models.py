# models.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime, BigInteger, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Usuario(Base):
    __tablename__ = 'usuarios'

    id = Column(Integer, primary_key=True, autoincrement=True)
    nome = Column(String)
    user_id = Column(BigInteger, unique=True)
    assinaturas_ativas = Column(Boolean, default=False)
    ativacao = Column(DateTime)
    expiracao = Column(DateTime)
    codigo = Column(String)

class PerfilUsuario(Base):
    __tablename__ = 'perfil_usuario'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('usuarios.user_id'))
    nivel = Column(String)
    objetivo = Column(String)
    idioma_base = Column(String)

class HistoricoErros(Base):
    __tablename__ = 'historico_erros'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('usuarios.user_id'))
    erro = Column(Text)
    data = Column(DateTime)

class PontosUsuario(Base):
    __tablename__ = 'pontos_usuario'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('usuarios.user_id'))
    pontos = Column(Integer, default=0)

class StreakUsuario(Base):
    __tablename__ = 'streak_usuario'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('usuarios.user_id'))
    dias_consecutivos = Column(Integer, default=0)
    ultima_data = Column(DateTime)

class UltimaInteracao(Base):
    __tablename__ = 'ultima_interacao'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('usuarios.user_id'))
    data = Column(DateTime)

class CodigosUtilizados(Base):
    __tablename__ = 'codigos_utilizados'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('usuarios.user_id'))
    codigo = Column(String)
    data_utilizacao = Column(DateTime)

class InteracoesUsuario(Base):
    __tablename__ = 'interacoes_usuario'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('usuarios.user_id'))
    tipo = Column(String)
    conteudo = Column(Text)
    data = Column(DateTime)

class ConversasUsuario(Base):
    __tablename__ = 'conversas_usuario'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('usuarios.user_id'))
    mensagem = Column(Text)
    resposta = Column(Text)
    data = Column(DateTime)
