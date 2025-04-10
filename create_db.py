
import sqlite3

def criar_banco():
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()

    # Tabela de usuários
    c.execute('''
    CREATE TABLE IF NOT EXISTS usuarios (
        user_id INTEGER PRIMARY KEY,
        nome TEXT,
        nivel TEXT,
        pontos INTEGER DEFAULT 0,
        streak INTEGER DEFAULT 0,
        ultima_interacao TEXT
    )
    ''')

    # Tabela de assinaturas
    c.execute('''
    CREATE TABLE IF NOT EXISTS assinaturas (
        user_id INTEGER PRIMARY KEY,
        ativo BOOLEAN,
        data_ativacao TEXT,
        origem_codigo TEXT,
        FOREIGN KEY (user_id) REFERENCES usuarios(user_id)
    )
    ''')

    # Tabela de códigos utilizados
    c.execute('''
    CREATE TABLE IF NOT EXISTS codigos_utilizados (
        codigo TEXT,
        user_id INTEGER,
        data_uso TEXT,
        FOREIGN KEY (user_id) REFERENCES usuarios(user_id)
    )
    ''')

    # Tabela de interações
    c.execute('''
    CREATE TABLE IF NOT EXISTS interacoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        transcricao TEXT,
        correcao TEXT,
        dica_pronuncia TEXT,
        data TEXT,
        FOREIGN KEY (user_id) REFERENCES usuarios(user_id)
    )
    ''')

    # Tabela de erros
    c.execute('''
    CREATE TABLE IF NOT EXISTS erros (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        erro TEXT,
        data TEXT,
        FOREIGN KEY (user_id) REFERENCES usuarios(user_id)
    )
    ''')

    # Tabela de conversas
    c.execute('''
    CREATE TABLE IF NOT EXISTS conversas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        pergunta TEXT,
        resposta TEXT,
        data TEXT,
        FOREIGN KEY (user_id) REFERENCES usuarios(user_id)
    )
    ''')

    conn.commit()
    conn.close()

if __name__ == '__main__':
    criar_banco()
