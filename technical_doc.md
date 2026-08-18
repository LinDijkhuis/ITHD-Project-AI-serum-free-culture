# Technical Documentation

**Author:** Lin Dijkhuis

**Date:** 09-07-2026

**Version:** 3.0

---

## Before You Start: What Is This Project?

**Why this exists:** Researchers working on serum-free and xeno-free cell culture have to manually dig through dozens of papers to answer basic questions: what medium was used, what viability was reported, which supplier. This project was built to remove that manual search step: ask a question in your own words, get an answer backed by direct citations to the original papers, not the AI's general knowledge.

**Status:** The core retrieval system works and has been verified on a small collection of papers. It reads PDFs, searches them by meaning, and keywords, and generates answers with citations. Two things are still in progress: the knowledge graph is built but is not yet used during question answering, and the system has not been evaluated for performance at large scale.

**How it works, in one paragraph:** 
PDFs are ingested and split into searchable sections. When you ask a question, the system searches those sections for relevant passages first, then asks the AI to answer using only those passages. Which is why it can cite specific papers and DOIs instead of guessing. 

**Example:**

> **Question:** *Has the cell viability decreased without the use of FCS or FBS?*
>
> **Answer:**
>
> Based on **"PBMC Cultures in Serum-Free Media" (Cochrane et al., 2024)**:
>
> - **Cell type:** Human peripheral blood mononuclear cells (PBMCs).
> - **Media compared:** AIM-V, CTS OpTmizer T Cell Expansion SFM, and X-VIVO 15 were compared with RPMI supplemented with human serum.
> - **Cell viability:** Serum-free media supported good levels of viable and proliferating T cells and B cells over a 6-day culture period.
> - **Comparison with serum-containing media:** Under unstimulated conditions, there were minimal differences in cell viability between serum-free media and human serum-containing controls.
> - **Stimulated conditions:** No direct decrease in viability was reported. Some variability in responses to different stimuli (e.g., CpG-ODN and PWM) was observed across media.
>
> **Conclusion:** The study found that serum-free media provided cell viability comparable to human serum-containing controls. It did not report that removing FCS or FBS decreased cell viability, although specific serum components may still influence cellular responses.

If the answer isn't in the ingested papers, the system says so. It does not guess or make things up.

**Quick glossary** (for readers without an AI/ML background):

| Term | Meaning |
|------|---------|
| RAG (Retrieval-Augmented Generation) | Is an AI framework that retrieves information using search algorithms to query external data, searching within indexed vector databases to feed generative Large Language Models (LLMs). Instead of asking an AI to answer from memory, the system first searches your documents for relevant chunks, then asks the AI to answer using only those chunks, which is what makes the citations reliable.  This architecture connects retrieval to generation by converting queries into mathematical vectors to execute high-dimensional similarity searches, appending the most relevant context directly into the prompt. Combining this evidence with its own language abilities, the LLM acts like a researcher with an open reference book. Generating highly accurate, domain-specific reponses. |
| Embedding | A numerical representation of a piece of text that lets the computer measure how similar two pieces of text are in meaning, not just in wording. |
| Vector search | Searching by meaning (using embeddings) rather than by exact keyword match. |
| Knowledge graph | A network of extracted facts (e.g. "Paper X uses Medium Y") stored so relationships between entities can, in future, be queried directly. |
| Chunk | A paper is too long to hand to the AI all at once, so it's split into smaller sections ("chunks") that can be searched individually. |

**Who this is for:** 
- Researchers in serum-free/xeno-free cell culture who want query a growing library of papers and reviewing them instead of manually searching them.


## Contents

- [1. Project Overview](#1-project-overview)
  - [1.1 Why AI and RAG](#11-why-ai-and-rag)
  - [1.2 Current Project Status](#12-current-project-status)
  - [1.3 Problem Statement](#13-problem-statement)
- [2. Getting Started](#2-getting-started)
  - [2.1 System Requirements](#21-system-requirements)
  - [2.2 First-Time Setup](#22-first-time-setup)
  - [2.3 Packages](#23-packages)
- [3. Instruction Guide](#3-instruction-guide)
- [4. Architecture](#4-architecture)
  - [4.1 How the System Works](#41-how-the-system-works)
  - [4.2 System Architecture Diagram](#42-system-architecture-diagram)
- [5. Configuration Reference](#5-configuration-reference)
- [6. Current system status](#6-current-system-status)
- [7. Known Limitations](#7-known-limitations)
- [8. Troubleshooting](#8-troubleshooting)
- [Support & Contact](#support--contact)

---

## 1. Project Overview

This system is an Agentic Retrieval-Augmented Generation (RAG) application built specifically for analysing serum-free and xeno-free cell culture research papers. It allows a researcher to ask natural-language questions about cell culture protocols, media formulations, viability outcomes, and supplier information, and receive answers backed by evidence extracted from scientific PDFs. It cites specific papers and DOIs rather than generating answers from general knowledge.

The system retrieves relevant snippets from your PDFs first, then asks the AI to write an answer using only those snippets, which is why it can cite specific papers and DOIs instead of guessing.

## 1.1. Why AI and RAG

A plain AI chatbot (e.g. asking ChatGPT directly) can answer questions about cell culture from its general training knowledge, but it cannot guarantee the answer reflects what a *specific* paper actually says. It may blend, misremember, or hallucinate details, and it cannot give a verifiable source. 

This project uses Retrieval-Augmented Generation (RAG) instead: the system only answers using text it has actually retrieved from the uploaded papers, and every answer is traceable back to a specific paper and DOI. This trades some flexibility (it can only answer about papers that have been ingested) for reliability and verifiability, which matters in a scientific context where an unverifiable or fabricated answer is worse than no answer.

### 1.2 Current Project Status

The project currently provides a complete Retrieval-Augmented Generation (RAG) pipeline for scientific literature. Researchers can upload scientific papers, process them into a searchable knowledge base, and ask natural-language questions through an AI assistant. The assistant retrieves relevant evidence from the uploaded papers and generates answers that cite the original sources.

At the current stage the system can successfully:

- Extract the text and logical sections (e.g., Introduction, Methods, Results, and Discussion) from scientific PDF documents.
- Convert papers into searchable text passages.
- Create semantic representations that enable meaning-based rather than keyword-based searching.
- Store the processed information in a searchable database.
- Build a knowledge graph representing relationships between entities such as cell types, suppliers, and culture conditions.
- Retrieve relevant evidence using semantic and keyword-based search techniques.
- Generate evidence-based answers with citations to the original research papers.

The current implementation **does not yet** generate scientific recommendations automatically. Instead, it retrieves the most relevant evidence from the literature. Producing structured recommendations requires additional work on table extraction, domain-specific entity extraction, and comparison logic, which are described later in this document.

The main limitations of the current implementations:

- **The knowledge graph is generated but is not yet used during question answering.** Although the system successfully builds a network of relationships between entities (such as cell types, suppliers, and culture conditions), the AI assistant currently answers questions using the citation-based retrieval system only. Integrating the knowledge graph into the retrieval process is planned future work rather than a missing or faulty feature.

- **The system has only been evaluated on a relatively small collection of papers.** 
The current evaluation focuses on verifying that the pipeline functions correctly rather than measuring performance at scale. Before the system is deployed with a much larger literature collection, further optimisation will be required. During testing, one minor issue affecting internal record-keeping was identified; this does not affect the evidence retrieved or the answers presented to the user. Further technical details are provided in later sections.

### 1.3 Problem Statement

Serum-free cell culture research is scattered across many papers with inconsistent reporting formats. Manually comparing viability percentages, doubling times, or media brands across a literature corpus is time-consuming. This system indexes the PDFs into two complementary databases and lets an LLM-powered agent retrieve and synthesise the relevant information on demand.

---

## 2. Getting Started

### 2.1 System Requirements

**Operating System**

- Linux (Ubuntu 22.04+ recommended) for the VM
- Windows/macOS with WSL2 or Remote-SSH also supported

**Hardware**

- RAM: minimum 8 GB (16 GB recommended for qwen3:32b)
- Storage: minimum 10 GB free (models + Docker images)
- CPU: 4+ cores recommended

**Software**

- Python 3.10+
- Docker 20.10+
- Git
- Ollama (installed automatically via `setup.sh`)

**Network**

- Internet access required for Neon PostgreSQL (cloud)
- Ports 7474 and 7687 accessible for Neo4j (local)
- Port 11434 accessible for Ollama (local)

---

### 2.2 First-Time Setup

**Prerequisites**

- Python 3.10+
- Docker
- Git
- A Neon PostgreSQL account (cloud)
- An API key for your chosen LLM provider (unless using Ollama locally)

### Installation

**Step 1 — Clone the repository**

Open a terminal and navigate to the directory where you want to store the project:

```bash
cd <path_to_project_location>
```
Clone the repository and enter the project directory:
```bash
git clone <repo-url>
cd ITHD-Project-AI-serum-free-culture
```

**Step 2 — Choose a setup method**

There are two ways to set up the project:
- Option A: Automated setup (Linux only). The `setup.sh` script automates most of the installation.
- Option B: Manual setup. Recommended for Windows and macOS, or when you want to configure each component yourself.

### Option A: Automated setup (Linux only)

From the project directory, run:
```bash
chmod +x setup.sh
./setup.sh
```

The script:
1. Creates a Python virtual environment and installs the required Python packages.
2. Sets up the PostgreSQL database schema on Neon.
3. Sets up Neo4j using Docker.
4. Installs Ollama and pulls the required models:
    - `nomic-embed-text`
    - `qwen3:32b` 


After the script finishes, activate the virtual environment:
```bash
source venv/bin/activate
```
Then continue to Step 3 — Configure environment variables below. 

> **Note:** `setup.sh` uses Linux-specific commands such as `sudo apt` and is intended for Ubuntu/Debian-based systems. For Windows or macOS, use the manual setup below.

---

### Option B: Manual setup

#### 1. Set up a Python virtual environment

From the project directory:
```bash
python -m venv venv
```
Activate the environment:
```bash
# On Linux/macOS
source venv/bin/activate  

# On Windows (Command prompt)
venv\Scripts\activate     # On Windows (Command prompt)

# Windows (PowerShell)
venv\Scripts\Activate.ps1
```

#### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

#### 3. Set up PostgresSQL

The project uses **Neon PostgreSQL** for the application database.
First, make sure the Neon PostgreSQL database is created and the connection string is available.

Then configure `DATABASE_URL` in your `.env` file as described in Step 5 — Configure environment variables.

After configuring the database connection, run:

```bash
python apply_schema.py
```
This executes `sql/schema.sql` and creates the required tables, indexes, and database functions.


**Warning:** `apply_schema.py` drops the existing tables before recreating them. Do not run this command on a database containing data you want to keep.

The vector dimensions in `sql/schema.sql` must match the embedding model that is being used. `text-embedding-3-small`uses 1536 dimensions,  while `nomic-embed-text` uses 768 dimensions. Check the schema on lines 31, 67, and 100 before running `apply_schema.py`.

#### 4. Set up Neo4j

Neo4j is used to store the project's knowledge graph.

#### Option A: Local-AI-Packaged 
Clone the Local AI Packaged repository:
 ```bash
git clone https://github.com/coleam00/local-ai-packaged.git
cd local-ai-packaged
 ```

Follow the installation instructions in the repository to start Neo4j using Docker Compose.
After Neo4j has started, the default connection used by this project is:
```bash
 bolt://localhost:7687
```
Record the Neo4j username and password so that they can be added to the project's `.env` file.

> **Note:** This is an external repository and its setup instructions may change. If this method causes problems, Neo4j can also be installed directly using the alternative method below. 

#### Option B: Neo4j Desktop
1. Download and install [Neo4j Desktop](https://neo4j.com/download/)
2. Create a new project
3. Create a local DBMS
4. Set a password and start the DBMS.
5. Record the connection details (URI, username, password).

**Step 5 — Configure environment variables**

From the project directory, copy `example.env` to `.env` and fill in your values:

Copy `example.env` to `.env` and fill in your values:

- `DATABASE_URL` — Neon PostgreSQL connection string
- `NEO4J_PASSWORD` — password for Neo4j
- `LLM_CHOICE` — the large language model you want to use
- `LLM_API_KEY` — your API key

A typical OpenAI configuration is:

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
> **Note:** The LLM provider and embedding provider are configured separately. You can use one provider for the LLM and another for embeddings.

**Step 6 — Verify the installation**


After completing the setup, make sure the following services are available:
- The Python virtual environment is activated.
- The Neon PostgreSQL database is accessible.
- Neo4j is running and accessible at the configured URI.
- The selected LLM provider is configured correctly.
- The selected embedding model is available.


### 2.3 Packages

**AI Agent**

| Package | Purpose |
|---------|---------|
| `pydantic-ai` | Agent framework used to build and orchestrate the research assistant |
| `openai` | OpenAI-compatible client, used here to connect to Ollama locally |
| `anthropic` | Anthropic SDK for Claude API access |
| `mcp` | Model Context Protocol, enables tool use between the agent and external services |

**Knowledge Graph**

| Package | Purpose |
|---------|---------|
| `graphiti-core` | Builds and queries the temporal knowledge graph on top of Neo4j |
| `neo4j` | Driver for connecting to the Neo4j graph database |

**Database**

| Package | Purpose |
|---------|---------|
| `asyncpg` | Async PostgreSQL driver for connecting to Neon |

**Document Processing**

| Package | Purpose |
|---------|---------|
| `pymupdf` | PDF parsing for ingesting research papers |

**API & Server**

| Package | Purpose |
|---------|---------|
| `fastapi` + `uvicorn` | REST API layer for the application |

**Data Validation**

| Package | Purpose |
|---------|---------|
| `pydantic` | Data models and validation throughout the codebase |

**Testing**

| Package | Purpose |
|---------|---------|
| `pytest` + `pytest-asyncio` | Test suite for async code |

---

## 3. Instruction Guide

### Running the Application

**Step 1 — Activate the environment**

```bash
source venv/bin/activate
```

**Step 2 — Start required services**

```bash
# Check if Docker is running
docker ps

# Start Neo4j if it is not already running
docker start neo4j

# Verify Ollama is running and models are available
ollama list
```

**Step 3 — Ingest documents**

Place your PDF (or markdown) research papers in the `source_papers/` folder, then run the ingestion pipeline:

```bash
# Basic ingestion
python -m ingestion.ingest
```
This automatically:

- Detects the paper structure (IMRaD sections)
- Extracts metadata (title, DOI, publication year)
- Creates chunks
- Generates embeddings
- Stores the chunks inside PostgreSQL
- Extracts entities into Neo4j

![alt text](image-1.png)
In the image above you can see in the terminal the environment was activated and the ingestion pipeline was started (called upon).

#### Optional flags:

```bash
# With verbose logging
python -m ingestion.ingest --verbose

# Skip knowledge graph (if Neo4j is not needed)
python -m ingestion.ingest --no-graph

# Clean existing data before ingesting
python -m ingestion.ingest --clean

# Use a different folder
python -m ingestion.ingest --documents /path/to/your/papers
```

#### Verify the paper was added:
```bash
curl http://localhost:8058/documents
```

> **Tip — Running ingestion in the background on the VM**
>
> Ingestion can take a long time. Use `screen` to keep it running even if your SSH session drops:
>
> ```bash
> # Start a named screen session
> screen -S <name_screen>
>
> # Run ingestion inside the session
> python -m ingestion.ingest --verbose
>
> # Detach from the session (keeps it running): press Ctrl + A, then D
>
> # List active sessions
> screen -ls
>
> # Reattach to a session
> screen -r ingest
>
> # Close a session completely (from inside it)
> exit
> ```

![alt text](image-3.png)
In the image above you see the terminal while the files are being ingested, chunked and embedded (mostly with graphiti).

![alt text](image.png)
A screenshot of after the ingestion is done. 14 files were ingested (as in the screenshots). 

![alt text](image-2.png)
In the image above you see the ingestion summary that appears in the terminal after the ingestion of the files is done. The names of the files are shown with the amount of chunks and graph episodes created.

**Step 4 — Start the API server (Terminal 1)**

The API server runs in the foreground and must stay running to handle requests. Leave this terminal open.

```bash
python -m agent.api
```
![alt text](image-6.png)
In the image above you see that agent.api is called using the command in the terminal. It shows that the application start-up is complete and ready.

**Step 5 — Verify the server is running**

```bash
curl http://localhost:8058/health
```

**Step 6 — Start the CLI chat (Terminal 2)**

Open a new terminal window, activate the environment, then start the CLI. The API server from Step 4 must already be running in the other terminal.

```bash
source venv/bin/activate
python cli.py
```

![alt text](image-7.png)
In the image above you see a new terminal window is opened and the CLI.py is called upon or the command is typed in the terminal. The CLI is opened and tells it is healthy and ready to be asked a question. 

---

### Available API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Check if the API and database are running |
| POST | `/chat` | Send a question to the agent |
| POST | `/chat/stream` | Streaming response via Server-Sent Events |
| POST | `/search/vector` | Direct vector similarity search |
| POST | `/search/hybrid` | Hybrid search (vector + keyword) |
| GET | `/documents` | List all ingested documents |

### Example Chat Request

```bash
curl -X POST http://localhost:8058/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the cell viability for the serum-free medium?"}'
```

---

## 4. Architecture

### 4.1 How the System Works

The diagram below shows the complete workflow of the application.

1. Research papers are placed in the `source_papers` folder.
2. The ingestion pipeline reads every PDF.
3. Each paper is split into logical scientific sections (IMRaD).
4. The sections are divided into smaller chunks.
5. Every chunk is converted into an embedding and stored inside PostgreSQL.
6. Graphiti extracts entities and relationships and stores them in Neo4j.
7. When a researcher asks a question, the AI agent searches the stored information.
8. The retrieved evidence is sent to the language model, which generates an answer containing references to the original papers.



## Ingestion Pipeline

```mermaid
flowchart TD
    A[PDF] --> B[Section Detection - IMRaD]
    B --> C[Section-aware Chunking]
    C --> D[Embeddings]
    C --> E[Entity Extraction - Graphiti]
    D --> F[(PostgreSQL + pgvector)]
    E --> G[(Neo4j Knowledge Graph)]
```


## Query Pipeline

```mermaid
flowchart TD
    A[Researcher Question] --> B[Pydantic AI Agent]
    B --> C[Determine Retrieval Strategy]
    C --> D[Vector Search]
    C --> E[Hybrid Search]
    C --> F[Entity Search]
    D --> G[Retrieve Relevant Evidence]
    E --> G
    F --> G
    G --> H[LLM Generation]
    H --> I[Evidence-backed Response]
```

**Note:** The Neo4j knowledge graph is currently populated during ingestion but is not yet connected to the agent's question-answering process. Graph-based retrieval is planned future work.


### 4.2 System Architecture Diagram

```mermaid
flowchart TD
    A["source_papers/*.pdf"]
    A --> B

    B["**Ingestion Pipeline**\ningest.py"]
    B --> C
    B --> D

    C["**PostgreSQL** + pgvector\n─────────────────\ndocuments\nchunks\nsessions\nmessages"]

    D["**Neo4j** via Graphiti\n─────────────────\nEntity nodes\nRelationship edges\nEpisodic nodes"]

    C --> E
  

    E["**Pydantic AI Agent**\n─────────────────\nvector_search\nhybrid_search\nsearch_by_entity\nget_document\nlist_documents"]

    E --> F

    F["**FastAPI** — api.py\n─────────────────\nPOST /chat\nPOST /chat/stream\nPOST /search/vector\nPOST /search/hybrid\nGET  /documents\nGET  /health"]
```

**Note:** The Neo4j knowledge graph is currently populated during document ingestion but is not yet connected to the AI agent for question answering. Graph-based retrieval is planned as future work.

> **Note:** To render the diagram above, open this file in VS Code and press `Ctrl + Shift + V` to open Markdown Preview. Install the **Markdown Preview Mermaid Support** extension if the diagram does not appear.

---

## 5. Configuration Reference

All configuration is done through the `.env` file. Copy `example.env` to `.env` and fill in your values. The table below lists every variable, whether it is required, its default, and what it does.

### Database

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | — | Full Neon PostgreSQL connection string |

### LLM Provider

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LLM_PROVIDER` | Yes | — | Provider name: `openai`, `ollama`, `gemini`, or `openrouter` |
| `LLM_BASE_URL` | Yes | — | API endpoint. See examples below |
| `LLM_API_KEY` | Yes | — | API key. Use `ollama` as the value for local Ollama |
| `LLM_CHOICE` | Yes | — | Model name, e.g. `qwen2.5:7b`, `qwen3:32b`, `gpt-4.1-mini`, `gemini-2.5-flash` |
| `INGESTION_LLM_CHOICE` | No | same as `LLM_CHOICE` | A separate (usually faster or cheaper) model used only during document ingestion |

**Provider base URL examples:**

| Provider | `LLM_BASE_URL` |
|----------|----------------|
| Ollama (local) | `http://localhost:11434/v1` |
| OpenAI | `https://api.openai.com/v1` |
| OpenRouter | `https://openrouter.ai/api/v1` |
| Gemini | `https://generativelanguage.googleapis.com/v1beta` |

### Embedding Model

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `EMBEDDING_PROVIDER` | Yes | — | Provider name: `openai`, `ollama`, or `gemini` |
| `EMBEDDING_BASE_URL` | Yes | — | API endpoint for the embedding model (same format as LLM) |
| `EMBEDDING_API_KEY` | Yes | — | API key for embeddings (can be the same as `LLM_API_KEY`) |
| `EMBEDDING_MODEL` | Yes | — | Model name, e.g. `nomic-embed-text`, `text-embedding-3-small` |
| `VECTOR_DIMENSION` | Yes | `768` | Must match the dimension of your embedding model. `768` for `nomic-embed-text`, `1536` for `text-embedding-3-small` |

### Neo4j Knowledge Graph

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `NEO4J_URI` | No | `bolt://localhost:7687` | Neo4j connection URI |
| `NEO4J_USER` | No | `neo4j` | Neo4j username |
| `NEO4J_PASSWORD` | No | — | Neo4j password (set during Neo4j setup). Required if Neo4j is used |

> If Neo4j is not configured, run ingestion with `--no-graph` to skip knowledge graph building.

### Application

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `APP_ENV` | No | `development` | Set to `production` to disable debug logging |
| `LOG_LEVEL` | No | `INFO` | Log verbosity: `DEBUG`, `INFO`, `WARNING`, or `ERROR` |
| `APP_PORT` | No | `8058` | Port on which the FastAPI server listens |

---

## 6. Current system status

The core retrieval pipeline is functional end to end: PDFs are parsed, 
chunked, embedded, and made searchable through vector and hybrid search, 
with the agent citing paper and DOI for every claim. This part of the 
system has been tested and works.

Two things sit outside that functional core:

- **The knowledge graph is built but disconnected from question-answering.** 
  Ingestion populates Neo4j via Graphiti, and a working graph search 
  method already exists (`GraphitiClient.search()`), but no agent tool 
  calls it yet — see Known Limitations.
- **The pipeline has not been performance-tested or optimized at scale.** 
  It was built and verified for correctness on a small number of papers. 
  Several parts of the pipeline (documented below) will not scale well 
  as the paper count grows, and one part has a data-accuracy bug that 
  should be fixed before the system is relied on for chunk-position data.

## 7. Known Limitations

The following limitations are known and may be addressed in future versions.

**Medium composition from tables.**
Many papers list exact medium ingredients and concentrations in a table within the Methods section. The PDF reader extracts table content as a flat stream of text, which often results in garbled or missing data. When this happens, the agent will explicitly state: *"Medium composition was not fully captured from this paper. It may be in a table that could not be extracted."* It will not guess or fill in values from general 
knowledge.

**Knowledge graph is built but not wired to the agent.**
The knowledge graph (Neo4j, via Graphiti) is populated during ingestion, building a network of relationships between cell types, media suppliers, culture conditions, and outcomes. A working search method for the graph already exists (`GraphitiClient.search()` in `agent/graph_utils.py`), but the agent has no tool to call it, so no questions are currently 
answered using the graph. All agent answers come from vector and hybrid search over PostgreSQL. Connecting the two requires: (1) a wrapper function in `tools.py` (following the pattern of `entity_search_tool`), and (2) a registered `@rag_agent.tool` in `agent.py` with a docstring telling the LLM when to prefer it — relationship-style questions ("which suppliers are used across all MSC papers?") rather than passage-lookup questions, which vector/hybrid search already handle.

**Scanned-image PDFs.**
PDFs that consist of scanned images without a text layer (i.e. no embedded text, only a photo of the page) produce no output. The system requires PDFs with a proper text layer. If a paper produces no chunks after ingestion, this is the most likely cause.

**Author and journal name extraction.**
The PDF parser extracts the title, DOI, and publication year from paper headers. Author names and journal names are not reliably extracted because their position and format vary too much between publishers. These fields may be absent from chunk metadata.

**Chunk position tracking can be incorrect for repeated text.**
When locating a chunk in the original document, the system searches for the chunk's text from the beginning of the document each time. If the same text appears multiple times, it may find an earlier occurrence rather than the occurrence that belongs to the chunk. This does not affect the content of the chunk or the information available to the agent. It only affects the recorded start and end character offsets in the chunk metadata, which are used to track the chunk's position within the original document.

**Not yet tested at scale, performance has not been optimized.**
The pipeline was built and verified for correctness, not throughput. Several stages will slow down or become bottlenecks as the number of ingested papers grows:
- Documents are ingested one at a time rather than concurrently, so ingestion time scales linearly with paper count even though most of the work (LLM calls, embedding calls, database writes) could overlap.
- Oversized document sections are sent to the LLM one piece at a time rather than batched, adding fixed network overhead per call.
- Chunks are inserted into the database one row at a time rather than in batches.
- Knowledge graph extraction is slow when run against a local model on the order of minutes per chunk, but drops to seconds per chunk if pointed at a cloud LLM API instead.
- Ingestion and knowledge-graph building currently run as a single pass, so fast vector data isn't usable until the slow graph step finishes too (the ingestion script already supports `--no-graph` and a graph-only pass to split these, but this isn't the default behaviour yet).
- Hybrid search combines vector and keyword results with a full outer join, which gets slower as the paper library grows; this affects every query, not just ingestion.

**Follow-up questions inconsistently resolve context.**
During testing, follow-up questions sometimes remained correctly scoped to the paper(s) discussed in the previous response (e.g. "give me more details about the medium composition" correctly returned detail from the paper just discussed). However, when a follow-up question asked about information that was not present in the previously discussed paper, the system occasionally retrieved information from a different paper, instead of indicating that the paper did not contain the requested information. This should be investigated further before the system is relied on for multi-turn conversations.

These issues do not all affect the current retrieval pipeline in the same way. Some are primarily performance and scalability limitations, while the follow-up-context issue can affect answer correctness in specific multi-turn conversations.
The follow-up context issue should therefore be investigated separately before the system is relied upon for complex multi-turn conversations.

---

## Evaluation

The current implementation successfully demonstrates the technical feasibility of the retrieval pipeline.

Successfully implemented:

- PDF ingestion
- Automatic chunking
- Embedding generation
- Vector search
- Hybrid retrieval
- Citation-based answers

Current limitations:

- Tables cannot yet be extracted correctly
- Figures cannot be analysed
- Morphology images are ignored
- No structured comparison between papers
- Recommendations cannot yet be generated
- Inconsistency with follow-up questions

The system therefore functions as an evidence retrieval assistant rather than a scientific recommendation system.

#### Examples 

![alt text](image-9.png)
![alt text](image-8.png)

In the image above the agent was asked "what medium does not contain animal derived components and is completely animal free?". The agent gives the key findings of the paper and the outcomes of the medium on the cells. The sources of which paper the this information comes from was also given by the agent. 

![alt text](image-10.png)
![alt text](image-11.png)
In the image above, the agent was asked "what is in the defined medium?". The agent uses one explicit paper to answer this question. The title and DOI of the paper is given.

![alt text](image-12.png)
![alt text](image-13.png)
In the image above, the agent was asked "What is the transfection efficiency of the HEK cell?". The agent answers "Specific details about transfection protocols, reagent compatibility, or efficiency percentages (e.g., % GFP-positive cells) are absent in the analyzed passages.". The agent gives answer: "- **Transfection Efficiency Not Assessed**: None of the listed studies or sections (methods, results, discussion) evaluate transfection performance in HEK or similar cell lines."

![alt text](image-14.png)
![alt text](image-15.png)
In the image above, the agent was asked "Is the cell differentiation speed increased or decreased without FCS-containing medium". The agent gives the key points of three papers that could answer the question asked. The sources of which paper the this information comes from was also given by the agent. 

![alt text](image-16.png)
In the image above the agent is being asked what "In what papers are the doubling time measured and mentioned?". The agent shows two articles: Mi Jang et al., "Serum-free cultures of C2C12 cells" (2022) Scientific Reports 12:827 (DOI: 10.1038/s41598-022-04804-z) and Cochrane et al., "Serum-free media for peripheral blood" (2024) Frontiers in Toxicology (DOI: 10.3389/ftox.2024.1462688). The tool used with the search is shown.

![alt text](image-17.png)
In the image above the agent is being asked "Which papers mention Lonza as a supplier?". The agent gives as answer the five document names where it was mentioned. It does not give the actual source with the author and DOI.

![alt text](image-22.png)
![alt text](image-20.png)
In the image above the agent is being asked "What's the average reported viability across all serum-free protocols?". The agent gives some key findings: in mean viability, median viability, highest viability and lowest viability. It also notes there are some gaps in the data. This shows that the numbers are not entirely accurate as not all the papers have any of this data or have the data in a graphical format and thus is not being read by the agent. Also is shown only 2 papers are being used for this.

### Questions the agent should handle well

- Fact lookup from narrative text: "What doubling time did this paper report for its PBMCs serum-free protocol?" or "What growth factors were included in this serum-free medium?" Anything stated in Methods or Results.
- Single-paper, single-claim questions: e.g. "Does this paper use xeno-free conditions?" One fact, traceable to one passage.
- Entity-tagged lookups: e.g. "Which papers mention Lonza as a supplier?" Works via entity search, as long as the term is on the entity list (see below).
- A question where the answer isn't in any of the papers: when a fact isn't in the retrieved evidence, the agent says so directly instead of guessing. This is an intended behaviour, not a bug.

### Questions the agent would not handle well

- Anything requiring a table: e.g. exact medium recipes and concentrations (see Section 7, table extraction).
- Anything requiring a figure or image: morphology photos, graphs, charts. Not processed by the system at all.
- Cross-paper comparison or synthesis: e.g. "Which of these three media formulations gave the best viability?" The agent retrieves passages per paper but doesn't synthesize a comparison.
- Recommendations or judgment calls: e.g. "What medium should I use for my MSC culture?" Out of scope by design, this is a retrieval assistant, not an advisory one.
- Aggregate or statistical questions across the library: e.g. "What's the average reported viability across all serum-free protocols?" No computation mechanism exists.
- Relationship questions needing the knowledge graph: e.g. "Which suppliers are most commonly paired with MSC culture across the corpus?" This is exactly what the graph was built for, but it isn't wired to the agent yet (see Section 7), so these questions fall back to plain search and usually return an incomplete or "not found" answer.
- Author or journal-based questions: not reliably extracted from PDFs (see Section 7).
- Entity terms not on the hardcoded list: if a paper uses a supplier or cell type not in the entity list, entity search misses it silently, with no warning.

## 8. Troubleshooting

### The API does not start

Check that the database connection is working:

```bash
psql "$DATABASE_URL" -c "SELECT 1;"
```

Check that the `.env` file exists and contains `DATABASE_URL`. If the file is missing or the variable is empty, the server will fail at startup.

### No results returned for a question

The most common cause is that ingestion has not been run yet. Run:

```bash
python -m ingestion.ingest --verbose
```

Confirm that documents are listed in the database:

```bash
curl http://localhost:8058/documents
```

### Neo4j connection errors at startup

If you are not using the knowledge graph, re-run ingestion with `--no-graph` and make sure `NEO4J_PASSWORD` is either removed from `.env` or left blank. Neo4j errors are non-fatal. Ingestion will continue without the graph if the connection fails.

### Ollama model not found

Make sure the model was pulled before running:

```bash
ollama pull nomic-embed-text
ollama pull qwen3:32b
```

List installed models to confirm:

```bash
ollama list
```

### Embedding dimension mismatch

If you see a database error mentioning vector dimensions, the `VECTOR_DIMENSION` in your `.env` does not match the model you selected. Check the table in [Section 5](#embedding-model) for the correct dimension, update `.env`, and re-run the database schema setup in `sql/schema.sql`.

### PDF produces no chunks after ingestion

The PDF likely has no text layer (scanned image). Open the PDF and try to select text. If you cannot, the file needs OCR processing before it can be ingested. This is not supported automatically.

---

## Support & Contact

For any questions about the domain-specific RAG (Retrieval-Augmented Generation) system, please contact:

| Name | Email |
|------|-------|
| Marc Teunis | marc.teunis@hu.nl |
| Bas van Gestel | bas.vangestel@hu.nl |
| Ronald Vlasblom | ronald.vlasblom@hu.nl |
