# Agentic AI Contributor for Open-Source Go Projects

An **agentic AI system** that takes a GitHub issue from an approved Go repository, understands the codebase, plans and implements a fix, validates it with tests, and generates a PR-ready diff with title and body.

Built with **LangGraph** for multi-agent orchestration and **Google Gemini** (free tier) as the default LLM.

---

## Architecture

```
GitHub Issue URL
       │
       ▼
┌──────────────────┐
│  Issue Analyzer   │  ← Fetches issue + comments from GitHub API
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Repo Mapper      │  ← Clones repo, builds AST code map, indexes into Pinecone
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Context Retriever │  ← Pinecone semantic search + grep + test discovery
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│    Planner        │  ← Step-by-step fix plan with exact file paths
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Patch Generator   │  ← Search/replace patches (NOT full-file rewrites)
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│   Validator       │  ← go build + go vet + go test
└────────┬─────────┘
    ┌────┴────┐
    │  Pass?  │──No (retries < 3)──→ back to Patch Generator
    └────┬────┘
         │ Yes (or max retries)
         ▼
┌──────────────────┐
│  PR Generator     │  ← PR title + body + unified diff
└──────────────────┘
```

### Key Design Choices

| Feature | Implementation | Why |
|---|---|---|
| **Orchestration** | LangGraph StateGraph | Demonstrates real multi-agent workflow |
| **Code understanding** | tree-sitter AST parsing | Accurate function/struct/interface extraction |
| **Search** | Pinecone + keyword grep | Semantic + lexical search combined |
| **Code editing** | Search/replace patches | Safer than full-file rewrites |
| **Validation** | go build / vet / test loop | Real coding agents use repair loops |
| **LLM** | Swappable (Gemini/OpenAI/Anthropic) | Change one variable to switch |
| **Caching** | Commit-hash indexed | Avoids re-parsing unchanged repos |

---

## Prerequisites

- **Python 3.11+**
- **Go 1.21+** (for running tests on the target repo)
- **Git** (for cloning repositories)
- A **Google AI Studio API key** (free): https://aistudio.google.com/apikey
- A **Pinecone API key** (free tier): https://www.pinecone.io/

---

## Setup

### 1. Clone this repository

```bash
git clone https://github.com/YOUR_USERNAME/agentic-go-contributor.git
cd agentic-go-contributor
```

### 2. Create a virtual environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and add your API keys:

```env
GOOGLE_API_KEY=your_google_api_key
PINECONE_API_KEY=your_pinecone_api_key
```

---

## Usage

### Basic usage

```bash
python main.py --repo spf13/cobra --issue 123
```

### With a full issue URL

```bash
python main.py --repo spf13/cobra --issue https://github.com/spf13/cobra/issues/123
```

### Override the model (when hitting rate limits)

```bash
python main.py --repo spf13/cobra --issue 123 --model gemini-1.5-pro
```

### Switch LLM provider

```bash
python main.py --repo spf13/cobra --issue 123 --provider openai --model gpt-4o
```

---

## How to Change the Model

The model name is a **single variable** in `config.py`:

```python
MODEL_NAME = "gemini-2.0-flash"   # ← change this
```

Or set it via environment variable:

```bash
export MODEL_NAME=gemini-1.5-pro
```

Or pass it at runtime:

```bash
python main.py --repo spf13/cobra --issue 123 --model gemini-1.5-flash
```

### Supported providers

| Provider | Install | Model examples |
|---|---|---|
| **Gemini** (default) | `pip install langchain-google-genai` | `gemini-2.0-flash`, `gemini-1.5-pro` |
| **OpenAI** | `pip install langchain-openai` | `gpt-4o`, `gpt-4o-mini` |
| **Anthropic** | `pip install langchain-anthropic` | `claude-sonnet-4-20250514`, `claude-3-5-haiku-20241022` |

---

## Output

All outputs are saved to `output/issue-{N}/`:

```
output/issue-123/
├── pr_title.txt      # PR title
├── pr_body.md        # PR body (Problem/Solution/Changes/Tests)
├── changes.diff      # Unified diff of all changes
├── plan.md           # Agent's change plan
└── agent_log.json    # Full execution log with timing
```

---

## Project Structure

```
agentic-go-contributor/
├── config.py                  # Model name variable + all settings
├── main.py                    # CLI entry point
├── requirements.txt           # Python dependencies
├── .env.example               # Environment variable template
│
├── agents/
│   ├── __init__.py            # get_llm() multi-provider factory
│   ├── issue_analyzer.py      # Fetch issue + comments, classify
│   ├── repo_mapper.py         # Clone, parse AST, index Pinecone
│   ├── context_retriever.py   # Semantic + grep search, test discovery
│   ├── planner.py             # Step-by-step change plan
│   ├── patch_generator.py     # Search/replace patch generation
│   ├── validator.py           # go build/vet/test runner
│   └── pr_generator.py        # PR title + body generation
│
├── tools/
│   ├── __init__.py
│   ├── git_tool.py            # Git clone, branch, diff
│   ├── code_search.py         # Directory tree, grep, file reader
│   ├── go_parser.py           # tree-sitter Go parser + regex fallback
│   └── test_runner.py         # go build/vet/test subprocess runner
│
├── vectorstore/
│   ├── __init__.py
│   └── pinecone_store.py      # Pinecone vector store for code map
│
├── workflow/
│   ├── __init__.py
│   ├── state.py               # AgentState TypedDict
│   └── graph.py               # LangGraph StateGraph definition
│
├── repos/                     # Cloned repositories (gitignored)
├── .cache/                    # Index cache (gitignored)
└── output/                    # Generated PR outputs
```

---

## Approved Repositories

| Repository | Difficulty |
|---|---|
| `spf13/cobra` | ⭐ Easiest (recommended) |
| `go-playground/validator` | ⭐⭐ Medium |
| `gin-gonic/gin` | ⭐⭐⭐ Harder |
| `golangci/golangci-lint` | ⭐⭐⭐⭐ Hardest |

---

## License

MIT
