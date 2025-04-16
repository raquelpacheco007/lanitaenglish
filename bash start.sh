#!/bin/bash

# Mata qualquer processo Python que possa estar rodando
pkill -f python || true

# Espera um pouco para garantir que os processos foram encerrados
sleep 2

# Inicia o servidor Flask
python server.py
