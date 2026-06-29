# Agentic RAG for Serum-Free Cell Culture Research

An AI agent system that combines semantic search with knowledge graph capabilities to analyse scientific literature on serum-free and xeno-free cell culture. Ask plain-English questions about media formulations, cell viability, doubling times, and supplier comparisons and receive answers backed by citations from your own PDF library.

The system retrieves relevant passages from your PDFs first, then asks the AI to write an answer using only those passages, which is why it can cite specific papers and DOIs instead of guessing.

Built with:

- Pydantic AI for the AI Agent Framework
- Graphiti for the Knowledge Graph
- Postgres with PGVector for the Vector Database
- Neo4j for the Knowledge Graph Engine (Graphiti connects to this)
- FastAPI for the Agent API

## Overview

This system includes three main components:

1. **Document Ingestion Pipeline**: Reads scientific PDF files, detects paper sections (Abstract, Introduction, Methods, Results, Discussion, References), chunks the text intelligently, extracts biomedical entities (cell types, suppliers, culture conditions, assay methods), and builds both vector embeddings and knowledge graph relationships
2. **AI Agent Interface**: A conversational agent powered by Pydantic AI that searches across the vector database using semantic similarity, keyword matching, and entity-targeted lookup, then writes cited answers
3. **Streaming API**: FastAPI backend with real-time streaming responses and direct search endpoints

## Prerequisites

- Python 3.11 or higher
- PostgreSQL database (such as Neon)
- Neo4j database (for knowledge graph)
- LLM Provider API key (OpenAI, Ollama, Gemini, etc.)

## Installation

### Option A: Automated setup (Linux only)

On Linux, `setup.sh` handles all installation steps in one command:

```bash
chmod +x setup.sh
./setup.sh
```

This script will:
1. Create a Python virtual environment and install all dependencies
2. Run `setup_db.py` to create the PostgreSQL schema on Neon
3. Install Docker (if not present) and start a Neo4j container
4. Install Ollama and pull the `nomic-embed-text` and `qwen3:32b` models

After it finishes, activate the environment with `source venv/bin/activate` and skip to [step 5 (Configure environment variables)](#5-configure-environment-variables).

> **Note:** `setup.sh` uses `sudo apt` and Docker, so it is intended for Linux (Ubuntu/Debian). On Windows or macOS follow Option B below.

---

### Option B: Manual setup

#### 1. Set up a virtual environment

```bash
python -m venv venv
source venv/bin/activate  # On Linux/macOS
# or
venv\Scripts\activate     # On Windows
```

#### 2. Install dependencies

```bash
pip install -r requirements.txt
```

#### 3. Set up required tables in Postgres

Execute the SQL in `sql/schema.sql` to create all necessary tables, indexes, and functions.

Be sure to change the embedding dimensions on lines 31, 67, and 100 based on your embedding model. OpenAI's text-embedding-3-small is 1536 and nomic-embed-text from Ollama is 768 dimensions, for reference.

Note that this script will drop all tables before creating/recreating them.

#### 4. Set up Neo4j

#### Option A: Using Local-AI-Packaged (Simplified setup - Recommended)
1. Clone the repository: `git clone https://github.com/coleam00/local-ai-packaged`
2. Follow the installation instructions to set up Neo4j through the package
3. Note the username and password you set in .env and the URI will be bolt://localhost:7687

#### Option B: Using Neo4j Desktop
1. Download and install [Neo4j Desktop](https://neo4j.com/download/)
2. Create a new project and add a local DBMS
3. Start the DBMS and set a password
4. Note the connection details (URI, username, password)

#### 5. Configure environment variables

Copy `example.env` to `.env` and fill in your values:

```bash
# Database Configuration
DATABASE_URL=postgresql://username:password@ep-example-12345.us-east-2.aws.neon.tech/neondb

# Neo4j Configuration
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password

# LLM Provider Configuration (choose one)
LLM_PROVIDER=openai
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-your-api-key
LLM_CHOICE=gpt-4.1-mini

# Embedding Configuration
EMBEDDING_PROVIDER=openai
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_API_KEY=sk-your-api-key
EMBEDDING_MODEL=text-embedding-3-small

# Ingestion Configuration
INGESTION_LLM_CHOICE=gpt-4.1-nano  # Faster model for processing

# Application Configuration
APP_ENV=development
LOG_LEVEL=INFO
APP_PORT=8058
```

For other LLM providers:
```bash
# Ollama (Local — no API key needed)
LLM_PROVIDER=ollama
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama
LLM_CHOICE=qwen3:32b-instruct

# OpenRouter
LLM_PROVIDER=openrouter
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_API_KEY=your-openrouter-key
LLM_CHOICE=anthropic/claude-3-5-sonnet

# Gemini
LLM_PROVIDER=gemini
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta
LLM_API_KEY=your-gemini-key
LLM_CHOICE=gemini-2.5-flash
```

## Quick Start

### 1. Prepare Your Documents

Add your PDF research papers to the `source_papers/` folder. The folder already contains 15 papers on serum-free and xeno-free cell culture media. You can add more PDFs at any time and re-run ingestion — you do not need to convert PDFs to any other format first.

### 2. Run Document Ingestion

**Important**: You must run ingestion first to populate the databases before the agent can provide meaningful responses.

```bash
# Basic ingestion
python -m ingestion.ingest

# Clean existing data and re-ingest everything
python -m ingestion.ingest --clean

# Faster processing without knowledge graph
python -m ingestion.ingest --no-graph --verbose
```

The ingestion process will:
- Parse each PDF and detect scientific sections (Abstract, Introduction, Methods, Results, Discussion, References)
- Extract DOIs and publication years from paper headers
- Extract biomedical entities: cell types, media suppliers, culture conditions, assay methods, institutions
- Generate embeddings for vector search
- Store everything in PostgreSQL and Neo4j

Note that ingestion can take a while, especially if semantic chunking or knowledge graph building is enabled, because both require LLM calls per chunk.

### 3. Configure Agent Behaviour (Optional)

Before running the API server, you can customise when the agent uses different tools by modifying the system prompt in `agent/prompts.py`. The system prompt controls which metrics the agent extracts, how it compares FBS vs. FBS-free conditions, and when to use each search tool.

### 4. Start the API Server (Terminal 1)

```bash
python -m agent.api

# Server will be available at http://localhost:8058
```

### 5. Use the Command Line Interface (Terminal 2)

```bash
# Start the CLI (connects to http://localhost:8058 by default)
python cli.py

# Connect to a different port
python cli.py --port 8080
```

#### CLI Features

- **Real-time streaming responses** — see the agent's answer as it is generated
- **Tool usage visibility** — understand which tools the agent used:
  - `vector_search` — semantic similarity search across paper chunks
  - `hybrid_search` — combined vector + keyword search
  - `search_by_entity` — targeted lookup by cell type, supplier, culture condition, assay method, or institution
  - `get_document` — retrieve the full content of a specific paper
  - `list_documents` — browse all indexed papers
- **Session management** — maintains conversation context across questions
- **Color-coded output** — easy to read responses and tool information

#### Example CLI Session

```
🤖 Agentic RAG — Serum-Free Cell Culture CLI
============================================================
Connected to: http://localhost:8058

You: What viability outcomes were reported for CHO cells in serum-free media?

🤖 Assistant:
Three studies reported viability above 90% for CHO cells in serum-free conditions...

🛠 Tools Used:
  1. vector_search (query='CHO cell viability serum-free', limit=10)
  2. search_by_entity (entity_category='cell_types', entity_value='CHO')

────────────────────────────────────────────────────────────

You: Which suppliers appeared most often in xeno-free protocols?

🤖 Assistant:
Lonza and CellGenix were cited in multiple xeno-free protocols across the indexed papers...

🛠 Tools Used:
  1. hybrid_search (query='xeno-free supplier', limit=10)
```

#### CLI Commands

- `help` — show available commands
- `health` — check API connection status
- `clear` — clear current session
- `exit` or `quit` — exit the CLI

### 6. Test the System

#### Health Check
```bash
curl http://localhost:8058/health
```

#### Chat with the Agent (Non-streaming)
```bash
curl -X POST "http://localhost:8058/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Which papers report doubling times for HEK293 cells in chemically defined media?"
  }'
```

#### Streaming Chat
```bash
curl -X POST "http://localhost:8058/chat/stream" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Compare viability outcomes for CHO and HEK293 cells in FBS-free conditions"
  }'
```

## How It Works

### The Power of Hybrid RAG + Knowledge Graph

This system combines two complementary approaches:

**Vector Database (PostgreSQL + pgvector)**:
- Semantic similarity search across paper chunks — finds relevant passages even when the wording differs from your question
- Hybrid search combines semantic similarity with keyword matching for broader coverage
- Entity search filters results by specific biomedical entities (e.g. all chunks mentioning "Lonza" as a supplier)

**Knowledge Graph (Neo4j + Graphiti)**:
- Tracks relationships between entities across papers — useful for understanding which media formulations and suppliers appear alongside particular cell types or outcomes
- Graph traversal for discovering connections between studies

**Intelligent Agent**:
- Automatically chooses the best search strategy for each question
- Combines results from multiple searches when needed
- Always cites paper title, authors, DOI or PMID — never fabricates values
- If a metric is not reported in a paper, it says so explicitly

### Example Queries

- **Metric lookup**: "What viability percentages were reported for HEK293 cells in chemically defined media?"
  — uses vector search to find passages reporting that specific measurement

- **Entity-targeted**: "Which suppliers were used in xeno-free protocols for neural stem cells?"
  — uses entity search filtered by cell type and supplier category

- **Cross-paper comparison**: "Compare doubling times across CHO studies that used FBS-free conditions"
  — uses hybrid search to gather results from multiple papers for side-by-side comparison

- **FBS control comparison**: "Find papers that report both FBS and FBS-free viability data for direct comparison"
  — uses hybrid search to locate studies with matched control data

### Why This Architecture Works Well

1. **Complementary Strengths**: Semantic search finds related content regardless of wording; the knowledge graph reveals connections between entities across papers
2. **No Hallucination on Numbers**: The agent is instructed never to estimate or infer viability percentages, growth rates, or doubling times — only to report what is written in the retrieved passages
3. **Section-Aware Chunking**: The PDF parser preserves the scientific structure of each paper so chunks from the Methods section are not mixed with chunks from the Results section
4. **Flexible LLM Support**: Switch between OpenAI, Ollama, OpenRouter, or Gemini based on your needs and budget

## API Documentation

Visit http://localhost:8058/docs for interactive API documentation once the server is running.

## Key Features

- **PDF Support**: Reads scientific PDFs directly — no conversion step needed; detects IMRaD sections automatically
- **Semantic + Keyword Search**: Finds relevant passages by meaning, by exact terms, or by both combined
- **Entity Search**: Filter results by cell type, supplier, culture condition, assay method, or institution
- **No Fabrication**: Agent is instructed to report "not found in this study" rather than estimating missing values
- **Streaming Responses**: Real-time AI responses with Server-Sent Events
- **Flexible Providers**: Support for multiple LLM and embedding providers including local (Ollama)
- **Session Memory**: Conversation history is stored so follow-up questions work naturally

## Project Structure

```
ITHD-Project-AI-serum-free-culture/
├── agent/                    # AI agent and API
│   ├── agent.py             # Pydantic AI agent with registered tools
│   ├── api.py               # FastAPI application and endpoints
│   ├── db_utils.py          # PostgreSQL connection and query functions
│   ├── graph_utils.py       # Neo4j / Graphiti integration
│   ├── models.py            # Data models (request, response, search results)
│   ├── prompts.py           # System prompt controlling agent behaviour
│   ├── providers.py         # LLM and embedding provider abstraction
│   └── tools.py             # Agent tool implementations
├── ingestion/               # Document processing pipeline
│   ├── ingest.py            # Main ingestion orchestration
│   ├── pdf_parser.py        # PDF reading and IMRaD section detection
│   ├── chunker.py           # Semantic and rule-based chunking
│   ├── embedder.py          # Embedding generation (multi-provider)
│   └── graph_builder.py     # Knowledge graph construction
├── sql/                     # Database schema
├── source_papers/           # Your scientific PDF files (15 papers included)
├── tests/                   # Test suite
└── cli.py                   # Interactive command-line interface
```

## Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=agent --cov=ingestion --cov-report=html

# Run specific test categories
pytest tests/agent/
pytest tests/ingestion/
```

## Troubleshooting

### Common Issues

**Database Connection**: Ensure your `DATABASE_URL` is correct and the database is accessible
```bash
psql -d "$DATABASE_URL" -c "SELECT 1;"
```

**Neo4j Connection**: Verify your Neo4j instance is running and credentials are correct
```bash
curl -u neo4j:password http://localhost:7474/db/data/
```

**No Results from Agent**: Make sure you have run the ingestion pipeline first
```bash
python -m ingestion.ingest --verbose
```

**LLM API Issues**: Check your API key and provider configuration in `.env`

**PDFs not being read**: Ensure your files are in `source_papers/` and have a `.pdf` extension. The parser supports standard text-layer PDFs; scanned-image-only PDFs without OCR will produce little or no text.

---

Built with Pydantic AI, FastAPI, PostgreSQL, and Neo4j.
