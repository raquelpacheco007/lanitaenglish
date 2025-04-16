from flask import Flask, request
import logging
import os

app = Flask(__name__)

# Ative logs para debug (opcional)
logging.basicConfig(level=logging.INFO)

@app.route('/webhook', methods=['POST'])
def webhook():
    # Aqui você vai processar os dados recebidos do Telegram
    logging.info("Webhook chamado!")
    return 'Webhook recebido com sucesso', 200

@app.route('/')
def index():
    return 'Lanita English está rodando! 🚀'

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))  # Usa a porta definida pelo ambiente ou 5000 por padrão
    app.run(host='0.0.0.0', port=port)
