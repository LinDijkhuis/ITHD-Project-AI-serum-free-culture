 # Agentic RAG for Serum-Free Cell Culture Research


## Project goal
This project aims to support researchers in finding evidence for serum-free and xeno-free cell culture media using artificial intelligence. Rather than manually reading hundreds of scientific papers, the system automatically processes publications, extracts and organises their contents, and retrieves the most relevant evidence to answer research questions. The long-term objective is to assist researchers in identifying suitable serum-free media formulations based on scientific literature.

The current implementation provides a complete retrieval-augmented generation (RAG) pipeline for scientific literature analysis. It is intended as a foundation for future development toward automated comparison and recommendation of serum-free media formulations.


## Overview
An AI agent system that combines semantic search with knowledge graph capabilities to analyse scientific literature on serum-free and xeno-free cell culture. Users can ask questions in their own words about media formulations, cell viability, doubling times, supplier comparisons, and related topics. The system returns answers supported by citations from the indexed PDF library.

The system first retrieves relevant passages from your PDFs, then instructs the language model to generate an answer based only on those retrieved passages.
This allows the system to cite specific papers and DOIs rather than relying on unsupported information.

The system is built using:

- Pydantic AI for the AI Agent Framework
- Graphiti for the Knowledge Graph
- PostgreSQLs with pgvector for the Vector Database
- Neo4j for the Knowledge Graph Engine (Graphiti connects to this)
- FastAPI for the Agent API


### Main components
This system includes three main components:

| Component | Main function |
|---|---|
| **Document Ingestion Pipeline** | Processes scientific PDF files by detecting paper sections, splitting text into searchable chunks, extracting biomedical entities, and creating vector embeddings and knowledge graph relationships. |
| **AI Agent Interface** | Searches the processed literature using semantic search, keyword matching, and entity-based lookup, then generates answers with citations. |
| **Streaming API** | Provides access to the AI agent and search functionality through a FastAPI backend, with real-time response streaming and direct search endpoints. |

## Current capabilities

The system can currently:

| Capability | What it does |
|---|---|
| **Process scientific PDFs** | Converts scientific publications into searchable data. |
| **Detect document structure** | Identifies sections such as **Abstract, Methods, and Results**. |
| **Perform semantic search** | Finds relevant passages based on meaning rather than exact keyword matches. |
| **Store scientific relationships** | Builds a knowledge graph linking biomedical concepts and their relationships. |
| **Generate evidence-based answers** | Produces responses based on information retrieved from the indexed literature. |
| **Cite source publications** | References the original scientific papers used to generate an answer. |

## Current limitations

The current implementation successfully retrieves and summarises evidence from scientific literature. However, several capabilities required to generate evidence-based serum-free media recommendations have not yet been implemented.

| Limitation | What is currently missing |
|---|---|
| **Formulation comparison** | Cannot automatically compare media formulations between studies. |
| **Table extraction** | Cannot reliably extract media compositions from tables. |
| **Evidence quality assessment** | Cannot automatically rank or assess the quality of evidence. |
| **Formulation recommendation** | Cannot recommend an optimal serum-free formulation based on the retrieved evidence. |
| **Statistical analysis** | Cannot yet perform reliable statistical analyses or draw statistically sound conclusions. |

## System architecture

```text
                   Scientific PDFs
                          │
                          ▼
                Document Ingestion
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
   PostgreSQL + pgvector          Neo4j
   (Semantic Search)       (Knowledge Graph)
              │                       
              ▼
    PydanticAI Agent
              │
              ▼
  Evidence-Based Answer
```

**Note:** The Neo4j knowledge graph is currently populated during ingestion but is not yet used by the AI agent during question answering. The current retrieval system uses PostgreSQL for vector, hybrid, and entity-based search.

## Rationale for Technology choices

### Why a vector database?
Scientific articles often describe the same concept using different terminology. A vector database enables semantic searching, allowing the system to retrieve relevant information even when exact keywords are not present.

### Why a knowledge graph?
Relationships between biological entities, such as cell lines, assays and media components, are stored in a knowledge graph. This preserves scientific context that would otherwise be lost when relying only on semantic search.

### Why combine these components?
Vector search is currently used to retrieve relevant passages from the literature, while the knowledge graph stores relationships between scientific entities for future graph-based retrieval. Combining these approaches is intended to allow the system to use both relevant passages and relationships between entities when the graph is integrated into the agent.

## Technology Overview
- FastAPI: Provides the API used by the application
- PostgreSQL: Stores processed literature
- pgvector: Enables semantic searching
- Neo4j: Stores relationships between scientific concepts
- PydanticAI: Controls the AI agent


## Prerequisites

- Python 3.10 or higher
- LLM provider API key (OpenAI, Ollama, Gemini, etc.)
- PostgreSQL database (for example, a Neon-hosted PostgreSQL database)
- Neo4j database (for knowledge graph)


## Installation

### Option A: Automated setup (Linux only)

Open a terminal and navigate to the directory containing the file:
```bash
cd <path_to_file_location>
```

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

> **Note:** `setup.sh` uses `sudo apt` and Docker, so it is intended for Linux (Ubuntu/Debian). On Windows or macOS, follow Option B below.

---

### Option B: Manual setup

#### 1. Set up a virtual environment

```bash
python -m venv venv

# On Linux/macOS
source venv/bin/activate  

# On Windows (Command prompt)
venv\Scripts\activate     # On Windows (Command prompt)

# Windows (PowerShell)
venv\Scripts\Activate.ps1
```

#### 2. Install dependencies

```bash
pip install -r requirements.txt
```

#### 3. Set up required tables in Postgres

Run the following command to execute sql/schema.sql and create all necessary tables, indexes, and functions:

```bash
python apply_schema.py
```

Be sure to change the embedding dimensions on lines 31, 67, and 100 based on your embedding model. OpenAI's text-embedding-3-small uses 1536 dimensions, while nomic-embed-text from Ollama uses 768 dimensions.

**Warning:** This script drops all existing tables before recreating them.

#### 4. Set up Neo4j

#### Option A: Using Local-AI-Packaged (Simplified setup - Recommended)
1. Clone the Local AI Packaged repository using the stable branch:
 ```bash
git clone https://github.com/coleam00/local-ai-packaged.git
cd local-ai-packaged
 ```
2. Follow the installation instructions in the repository to start Neo4j using Docker Compose.
3. Note the Neo4j username and password configured in the example.env file. The default URI used by this project is: bolt://localhost:7687

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
LLM_CHOICE=qwen3:32b

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

Add your scientific PDF papers to the `source_papers/` folder. The folder already contains scientific papers on serum-free and xeno-free cell culture media. You can add more PDFs at any time and re-run ingestion — you do not need to convert PDFs to any other format first.

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

Before running the API server, you can customise when the agent uses different tools by modifying the system prompt in `agent/prompts.py`. The system prompt controls which metrics the agent extracts, how it compares FBS and FBS-free conditions, and when each retrieval tool is used.

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

| Feature | Description |
|---|---|
| **Real-time streaming responses** | Displays the agent's answer as it is generated. |
| **Tool usage visibility** | Shows which search tools the agent used. |
| **Session management** | Maintains conversation context across questions. |
| **Colour-coded output** | Makes responses and tool information easier to read. |

**Available search tools:**

| Tool | Description |
|---|---|
| `vector_search` | Semantic similarity search across paper chunks. |
| `hybrid_search` | Combines vector and keyword search. |
| `search_by_entity` | Targeted search by cell type, supplier, culture condition, assay method, or institution. |
| `get_document` | Retrieves the full content of a specific paper. |
| `list_documents` | Lists all indexed papers. |


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

| Command | Description |
|---|---|
| `help` | Shows available commands. |
| `health` | Checks the API connection status. |
| `clear` | Clears the current session. |
| `exit` / `quit` | Exits the CLI. |

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

### The Retrieval System

This system combines two complementary approaches:

**Vector Database (PostgreSQL + pgvector)**:
- **Semantic similarity search across paper chunks:** Finds relevant passages even when the wording differs from your question.
- **Hybrid search:** Combines semantic similarity with keyword matching for broader coverage.
- **Entity search:** Filters results by specific biomedical entities, such as all chunks mentioning "Lonza" as a supplier.

**Knowledge Graph (Neo4j + Graphiti)**:
-  **Relationship tracking:** Extracts and stores relationships between entities across papers, such as cell types, culture conditions, media formulations and suppliers and outcomes.
- **Current status:** The knowledge graph is populated during ingestion but is not yet used by the AI agent during question answering.
- **Future use:** Graph-based retrieval could be added to support relationship-based questions and comparisons across papers.

**Intelligent Agent**:
- **Search strategy selection:** Automatically chooses the most appropriate search strategy for each question.
- **Multi-tool retrieval:** Combines results from multiple searches when needed.
- **Source citation:** Cites the paper title, authors, DOI, or PMID and does not fabricate values.
- **Missing information handling:** Explicitly states when a metric is not reported in a paper.

### Example Queries

- **Metric lookup**: "What viability percentages were reported for HEK293 cells in chemically defined media?"
  — the agent primarily uses vector search to find passages reporting that specific measurement

- **Entity-targeted**: "Which suppliers were used in xeno-free protocols for neural stem cells?"
  — uses entity search filtered by cell type and supplier category

- **Cross-paper comparison**: "Compare doubling times across CHO studies that used FBS-free conditions"
  — uses hybrid search to gather results from multiple papers for side-by-side comparison

- **FBS control comparison**: "Find papers that report both FBS and FBS-free viability data for direct comparison"
  — uses hybrid search to locate studies with matched control data

### Why This Architecture Works Well

1. **Complementary Strengths**: Semantic search finds related content regardless of wording. The knowledge graph reveals connections between entities across papers.
2. **Prevents Numerical Hallucinations**: The agent is instructed never to estimate or infer viability percentages, growth rates, or doubling times. It only reports values stated in the retrieved passages.
3. **Section-Aware Chunking**: The PDF parser preserves the scientific structure of each paper so chunks from the Methods section are not mixed with chunks from the Results section
4. **Flexible LLM Support**: The system can switch between OpenAI, Ollama, OpenRouter, or Gemini based on user requirements and budget

## Project Structure

```
ITHD-Project-AI-serum-free-culture/
├── agent/                   # Contains the conversational AI, API and retrieval logic.
│   ├── agent.py             # Pydantic AI agent with registered tools
│   ├── api.py               # FastAPI application and endpoints
│   ├── db_utils.py          # PostgreSQL connection and query functions
│   ├── graph_utils.py       # Neo4j / Graphiti integration
│   ├── models.py            # Data models (request, response, search results)
│   ├── prompts.py           # System prompt controlling agent behaviour
│   ├── providers.py         # LLM and embedding provider abstraction
│   └── tools.py             # Agent tool implementations
├── ingestion/               # Processes scientific papers into searchable knowledge.
│   ├── ingest.py            # Main ingestion orchestration
│   ├── pdf_parser.py        # PDF reading and IMRaD section detection
│   ├── chunker.py           # Semantic and rule-based chunking
│   ├── embedder.py          # Embedding generation (multi-provider)
│   └── graph_builder.py     # Knowledge graph construction
├── sql/                     # Database schema
├── source_papers/           # Your scientific PDF files (14 papers included)
├── tests/                   # Test suite
└── cli.py                   # Interactive command-line interface
```
## Typical Workflow

1. Add scientific PDF papers to the project.
2. Run the ingestion pipeline.
3. Store the processed information in the vector database and knowledge graph.
4. Ask a research question through the application.
5. Retrieve the most relevant scientific evidence.
6. Generate an evidence-based answer with references.

## How Document Ingestion Works

When a new publication is added, the system automatically:

1. **Extracts the text:** Reads the content of the PDF.
2. **Identifies document sections:** Detects sections such as Abstract, Methods, and Results.
3. **Creates searchable chunks:** Divides the text into smaller sections for retrieval.
4. **Generates embeddings:** Converts the chunks into vector representations for semantic search.
5. **Extracts biomedical entities:** Identifies relevant entities such as cell types, suppliers, and culture conditions.
6. **Stores the processed information:** Saves searchable text and entity relationships in PostgreSQL and Neo4j.

## API Documentation

Visit http://localhost:8058/docs for interactive API documentation once the server is running.

## Key Features

| Key feature | What it does |
|---|---|
| **PDF support** | Processes scientific PDF files directly without requiring a separate conversion step and automatically detects document sections such as **Abstract, Methods, Results, and Discussion**. |
| **Semantic and keyword search** | Finds relevant passages based on meaning, exact terms, or a combination of both. |
| **Entity search** | Allows results to be filtered by biomedical entities such as cell type, supplier, culture condition, assay method, or institution. |
| **Evidence-grounded responses** | Instructs the AI agent to report when information is not found in the available literature rather than estimating or inventing missing values. |
| **Streaming responses** | Provides AI responses in real time using Server-Sent Events (SSE). |
| **Flexible providers** | Supports multiple LLM and embedding providers, including locally hosted models through Ollama. |

## Before modifying the system
- Ensure the ingestion pipeline still completes successfully.
- Verify that embeddings are generated correctly.
- Test retrieval quality using example questions.
- Confirm that citations are still returned.
- Review application logs for unexpected errors.

## Running Tests
Run the tests after modifying the system to verify that ingestion, retrieval, and API functionality continue to operate correctly.

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=agent --cov=ingestion --cov-report=html

# Run specific test categories
pytest tests/agent/
pytest tests/ingestion/
```

## Known challenges
- Scientific terminology varies greatly between publications.
- Tables are difficult to extract reliably.
- Large language models should not be relied upon without retrieved evidence.
- PDF formatting differs considerably between publishers.

## Starting point for further development
Developers continuing this project should first focus on improving structured information extraction, particularly the extraction of media formulations from scientific tables. This functionality forms the foundation for implementing formulation comparison and, ultimately, evidence-based recommendation generation.

## Component dependencies
| Component | Depends on | Why it matters |
|-----------|------------|---------|
| Ingestion | PDF parser | Extracts and processes information from scientific papers. Without this step, no searchable data is created. |
| Embeddings | Chunked text | Converts processed text into vector representations for semantic search. |
| Knowledge Graph | Entity extraction | Stores relationships between scientific concepts to improve context and retrieval. |
| Retrieval | Embeddings + Knowledge Graph | Combines semantic search and graph information to find the most relevant scientific evidence. |
| AI Agent | Retrieval | Generates evidence-based answers using retrieved information instead of relying solely on the language model's internal knowledge. |

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
