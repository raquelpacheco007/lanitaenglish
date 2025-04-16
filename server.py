import os
from flask import Flask, redirect
import subprocess
import sys
import socket

# Cria a aplicação Flask
app = Flask(__name__)

# Rota principal - redireciona para o bot
@app.route('/')
def index():
    return "Bot está rodando! Esta é apenas a página de status."

# Verifica se a porta está em uso
def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

# Função para iniciar o bot em uma thread separada
def start_bot():
    # Aqui você pode importar e iniciar o bot diretamente
    # Ou iniciar como um subprocesso
    subprocess.Popen([sys.executable, 'bot.py'])

if __name__ == '__main__':
    # Prioriza a porta definida pelo Render, ou usa uma porta alternativa
    port = int(os.environ.get('PORT', 10000))  # Render usa variável de ambiente PORT
    
    # Verifica se o bot.py já está rodando em alguma porta
    # Se estiver, não tenta iniciar o bot novamente
    if not is_port_in_use(port):
        start_bot()
    
    # Inicia o server Flask em uma porta diferente que não conflite
    app.run(host='0.0.0.0', port=port, debug=False)
