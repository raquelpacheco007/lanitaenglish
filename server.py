from flask import Flask, request
import logging

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
    app.run(host='0.0.0.0', port=10000)
