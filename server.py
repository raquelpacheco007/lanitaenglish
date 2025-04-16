from flask import Flask, request
import logging
import os

# Configuração de logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.route('/')
def index():
    return 'Lanita English Bot - Servidor Ativo'

@app.route('/webhook', methods=['POST'])
def webhook():
    logger.info("Webhook recebido!")
    try:
        # Apenas registra que recebeu o webhook
        telegram_data = request.get_json(force=True)
        logger.info(f"Dados do Telegram: {telegram_data}")
        return 'OK', 200
    except Exception as e:
        logger.error(f"Erro ao processar webhook: {e}")
        return 'Erro', 500

if __name__ == '__main__':
    # Obtém a porta do ambiente do Render
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"Iniciando servidor Flask na porta {port}")
    app.run(host='0.0.0.0', port=port)
