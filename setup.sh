#!/bin/bash
set -e

echo "=== ITHD Project: AI Serum-Free Culture - Setup ==="

# --- Python venv ---
echo ""
echo "[1/6] Installing python3-venv..."
sudo apt install python3-venv -y

echo "[2/6] Creating virtual environment..."
python3 -m venv venv

echo "[3/6] Installing dependencies..."
source venv/bin/activate
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet

echo "[4/6] Setting up PostgreSQL schema on Neon..."
python setup_db.py

# --- Docker + Neo4j ---
echo ""
echo "[5/6] Setting up Docker and Neo4j..."

if ! command -v docker &> /dev/null; then
    sudo apt install docker.io -y
    sudo systemctl start docker
    sudo usermod -aG docker $USER
fi

if ! sudo docker ps --filter "name=neo4j" --format "{{.Names}}" | grep -q neo4j; then
    sudo docker run -d \
      --name neo4j \
      --restart unless-stopped \
      -p 7474:7474 -p 7687:7687 \
      -e NEO4J_AUTH=neo4j/SerumFree!8 \
      neo4j:latest
    echo "Neo4j container started."
else
    echo "Neo4j container already running, skipping."
fi

# --- Ollama ---
echo ""
echo "[6/6] Installing Ollama and pulling models..."

if ! command -v ollama &> /dev/null; then
    curl -fsSL https://ollama.com/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
fi

ollama pull nomic-embed-text
ollama pull qwen3:32b

echo ""
echo "=== Setup complete! ==="
echo ""
echo "To activate your environment: source venv/bin/activate"