# Agentic AI Contributor for Open-Source Go Projects

An autonomous, agentic AI platform designed to resolve issues in open-source Go projects. 

This system takes a GitHub issue URL, understands the target codebase through AST parsing and semantic search, formulates a step-by-step implementation plan, modifies the code safely using search/replace patches, validates the changes through the Go compiler and test suite, and generates a pull request ready for review.

Built with **LangGraph** for multi-agent orchestration, supporting **Google Gemini** (default), **OpenAI**, and **Anthropic** models.

---

## 🚀 Key Features & Engineering Decisions

1. **Multi-Agent Orchestration**: Utilizes a directed StateGraph (LangGraph) to orchestrate issue analysis, code retrieval, planning, patching, and validation.
2. **AST-Based Code Mapping**: Employs `tree-sitter-go` to parse Go syntax and extract precise function/struct/interface signatures, avoiding the brittleness of regex-based scanning.
3. **Hybrid Context Retrieval**: Combines Pinecone semantic embeddings (for conceptual matching) with lexical grep search (for exact token matching) to accurately locate relevant files and tests.
4. **Safe Code Modification**: Avoids hallucination-prone full-file rewrites. Uses a strict `SEARCH/REPLACE` patching mechanism with fuzzy whitespace matching to ensure localized, safe code edits.
5. **Self-Healing Validation Loop**: Automatically runs `go build`, `go vet`, and `go test`, feeding compiler errors back into the LLM context so the agent can autonomously fix its own mistakes.
6. **Provider Agnostic**: Easily switchable LLM backends via environment variables or CLI flags.

---

## 🏗️ Architecture Pipeline

```text
GitHub Issue URL
       │
       ▼
┌──────────────────┐
│ 1. Issue Analyzer │  ← Fetches issue + comments. Classifies intent & extracts keywords.
└────────┬─────────┘     (Comments often hold more context than the issue body)
         │
         ▼
┌──────────────────┐
│ 2. Repo Mapper    │  ← Clones repo. Parses all .go files via tree-sitter AST.
└────────┬─────────┘     Indexes signatures into Pinecone. Caches by commit-hash.
         │
         ▼
┌──────────────────┐
│ 3. Context        │  ← Performs hybrid search (Semantic + Grep).
│    Retriever      │    Automatically discovers adjacent `*_test.go` files.
└────────┬─────────┘     LLM ranks and selects the top 10 most relevant files.
         │
         ▼
┌──────────────────┐
│ 4. Planner        │  ← Generates a step-by-step fix plan specifying exact file paths.
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ 5. Patch Gen      │  ← Emits exact SEARCH/REPLACE blocks.
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ 6. Validator      │  ← Runs: go build → go vet → go test.
└────────┬─────────┘
    ┌────┴────┐
    │  Pass?  │──No (retries < 3)──→ back to Patch Generator (with error logs)
    └────┬────┘
         │ Yes (or max retries)
         ▼
┌──────────────────┐
│ 7. PR Generator   │  ← Reads unified diff. Writes PR Title and PR Body (Markdown).
└──────────────────┘
```

---

## 🛠️ Setup Instructions

### 1. Prerequisites

- **Python 3.11+**
- **Go 1.21+** (installed on the host machine to run validation tests)
- **Git**

### 2. Installation

```bash
git clone https://github.com/jigs1188/PRAgent.git
cd PRAgent

# Create and activate a virtual environment
python -m venv venv
# Windows: venv\Scripts\activate
# macOS/Linux: source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. API Keys Configuration

Copy the example environment file:
```bash
cp .env.example .env
```

Edit `.env` to include your LLM provider key and a Pinecone vector DB key (the free tier is sufficient).

```env
# ── LLM Configuration ──
# Change these two variables to switch LLMs (e.g., LLM_PROVIDER=openai, MODEL_NAME=gpt-4o)
LLM_PROVIDER=gemini
MODEL_NAME=gemini-2.5-flash

# ── API Keys ──
GOOGLE_API_KEY=your_gemini_api_key
OPENAI_API_KEY=your_openai_api_key_if_using_openai
PINECONE_API_KEY=your_pinecone_api_key
```

*Note: The Pinecone index (`go-contributor` by default) will be created automatically upon first run.*

---

## 💻 Usage & Testing

Run the agent via the CLI. Provide the repository name and issue number (or full URL):

```bash
python main.py --repo spf13/cobra --issue 1860
```

### Supported Repositories
The agent is designed to work with any Go repository but has been validated against:
- `spf13/cobra` (Recommended for testing)
- `go-playground/validator`
- `gin-gonic/gin`
- `golangci/golangci-lint`

### Switching Models (OpenAI, Anthropic, or other Gemini models)
The system is entirely provider-agnostic. You can switch to OpenAI (e.g. `gpt-4o`) or Anthropic (e.g. `claude-3-5-sonnet-20241022`) easily.

**Method 1: Using CLI Flags (Easiest)**
1. Make sure you have the provider package installed:
   ```bash
   pip install langchain-openai langchain-anthropic
   ```
2. Add the corresponding API key to your `.env` file:
   ```env
   OPENAI_API_KEY=sk-proj-...
   ANTHROPIC_API_KEY=sk-ant-...
   ```
3. Run the CLI with the `--provider` and `--model` flags:
   ```bash
   python main.py --repo spf13/cobra --issue 1860 --provider openai --model gpt-4o
   ```
   Or for Anthropic:
   ```bash
   python main.py --repo spf13/cobra --issue 1860 --provider anthropic --model claude-3-5-sonnet-20241022
   ```

**Method 2: Changing the .env File (Recommended for Permanent Switching)**
Because `config.py` uses `load_dotenv(override=True)`, you can permanently change the default model by updating your `.env` file directly:
```env
LLM_PROVIDER=openai
MODEL_NAME=gpt-4o
```

---

## 📁 Output Artifacts

The agent does **not** push directly to GitHub to avoid polluting open-source repositories during evaluation. Instead, all outputs are saved locally in the `output/issue-<NUMBER>/` directory.

Example output from a successful run:

```text
output/issue-1860/
├── changes.diff      # The unified git diff containing all code changes
├── pr_title.txt      # The generated pull request title
├── pr_body.md        # The generated PR description (Problem, Solution, Testing)
├── plan.md           # The step-by-step execution plan the LLM followed
└── agent_log.json    # Detailed execution trace, timings, and validation pass/fail status
```

### How to Verify the Output

Once the CLI finishes, you can review the agent's work directly. On Linux/macOS or Git Bash, you can run:

```bash
# View the generated plan the LLM followed
cat output/issue-1860/plan.md

# View the actual code changes
cat output/issue-1860/changes.diff

# View the ready-to-merge Pull Request description
cat output/issue-1860/pr_body.md
```

**Verifying the code:**
You can verify the agent actually wrote valid code by applying the diff directly to the cloned repository and running the tests manually:
```bash
cd repos/cobra
git apply ../../output/issue-1860/changes.diff
go test ./...
```
