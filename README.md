# Agentic AI Contributor for Open-Source Go Projects

This is an **agentic AI platform** that solves issues in open-source Go projects. It takes a GitHub issue URL, understands the codebase via AST parsing and semantic search, plans a fix, applies the code changes using search/replace patches, validates the changes by compiling and running tests, and finally generates a PR-ready diff with a title and description.

Built with **LangGraph** for multi-agent orchestration. The default LLM is **Google Gemini**, but it seamlessly supports **OpenAI** and **Anthropic**.

---

## 🏗️ Architecture: The 7-Node Agent Pipeline

This system is not a single prompt or thin wrapper. It uses a **directed graph with a conditional validation loop** (via LangGraph) to mimic how a human engineer works.

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
└────────┬─────────┘     Indexes signatures (functions, structs) into Pinecone.
         │               *Caches by commit-hash to avoid re-parsing.*
         ▼
┌──────────────────┐
│ 3. Context        │  ← Performs hybrid search: Semantic (Pinecone) + Lexical (grep).
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
│ 5. Patch Gen      │  ← Emits SEARCH/REPLACE blocks. Does NOT hallucinate full files.
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

### Key Engineering Decisions

1. **Search/Replace Patches vs Full-File Rewrites**: Asking an LLM to rewrite a 2000-line Go file usually results in deleted functions or hallucinated imports. This system uses `SEARCH/REPLACE` blocks with fuzzy whitespace matching to ensure safe, localized edits.
2. **Validation Repair Loop**: Real coding agents fail and retry. The conditional edge from `Validator` back to `Patch Generator` injects `go test` compiler/test errors directly into the LLM context so it can fix its own mistakes.
3. **AST-Based Code Mapping**: Uses `tree-sitter-go` to build a precise map of functions, methods, and structs with line numbers. This is vastly superior to regex-based codebase scanning.
4. **Hybrid Retrieval**: Combines semantic embeddings (Pinecone) for conceptual matches with keyword grep for exact token matches.

---

## 🚀 Setup Instructions for Evaluators

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
# On Windows: venv\Scripts\activate
# On macOS/Linux: source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. API Keys Configuration

Copy the example environment file:
```bash
cp .env.example .env
```

To run this, you will need **two things**: an LLM provider key, and a Pinecone vector DB key (free tier is fine).
Edit `.env`:

```env
# By default, the system uses Gemini for both LLM and Embeddings
GOOGLE_API_KEY=your_gemini_api_key

# Pinecone is required for the AST code map
PINECONE_API_KEY=your_pinecone_api_key
```

*Note: The Pinecone index (`go-contributor` by default) will be created automatically if it doesn't exist.*

---

## 🧠 Changing LLM Providers (OpenAI / Anthropic)

The system is provider-agnostic. You can easily test it using OpenAI instead of Gemini.

**1. Install the provider package:**
```bash
pip install langchain-openai
```

**2. Add your key to `.env`:**
```env
OPENAI_API_KEY=sk-proj-...
```

**3. Run the CLI with flags:**
```bash
python main.py --repo spf13/cobra --issue 1860 --provider openai --model gpt-4o
```

*(Alternatively, you can change the default `LLM_PROVIDER` and `MODEL_NAME` directly in `config.py`)*.

---

## 💻 Usage

Run the agent via the CLI. You can provide the repository name and issue number:

```bash
python main.py --repo spf13/cobra --issue 1860
```

Or you can pass the full URL:

```bash
python main.py --repo spf13/cobra --issue https://github.com/spf13/cobra/issues/1860
```

### Testing on your own repository
You can test the agent on any public repository without modifying the code.
1. Create a dummy issue on your repository (e.g., "Fix spelling mistake in README").
2. Run the agent against it:
```bash
python main.py --repo your_github_username/your_repo_name --issue 1
```

---

## 📁 Output Artifacts

The agent does **not** push directly to GitHub (to avoid polluting open-source repositories during evaluation). Instead, all outputs are saved locally in the `output/issue-<NUMBER>/` directory.

Example output from a successful run:

```text
output/issue-1860/
├── changes.diff      # The unified git diff containing all code changes
├── pr_title.txt      # The generated pull request title
├── pr_body.md        # The generated PR description (Problem, Solution, Testing)
├── plan.md           # The step-by-step execution plan the LLM followed
└── agent_log.json    # Detailed execution trace, timings, and validation pass/fail status
```

You can take the `changes.diff` file and apply it directly via `git apply changes.diff` to test the code manually.

---

## 🛠️ Project Structure

```text
PRAgent/
├── main.py                    # CLI entry point. Initializes LangGraph.
├── config.py                  # Central configuration (Model definitions, limits).
├── agents/                    # The LangGraph Node Implementations
│   ├── issue_analyzer.py      
│   ├── repo_mapper.py         
│   ├── context_retriever.py   
│   ├── planner.py             
│   ├── patch_generator.py     
│   ├── validator.py           
│   └── pr_generator.py        
├── tools/                     # Core utilities used by the agents
│   ├── code_search.py         # Grep & AST context reader
│   ├── git_tool.py            # Cloning and diff generation
│   ├── go_parser.py           # Tree-sitter Go integration
│   └── test_runner.py         # Subprocess wrappers for `go build / vet / test`
├── vectorstore/
│   └── pinecone_store.py      # Pinecone hybrid search & caching logic
├── workflow/
│   ├── graph.py               # The LangGraph StateGraph topology
│   └── state.py               # The typed dictionary defining AgentState
└── README.md
```

---

## 🎯 Target Repositories

This agent is designed to work with any Go repository, but has been specifically built with the following open-source projects in mind:
- `spf13/cobra`
- `go-playground/validator`
- `gin-gonic/gin`
- `golangci/golangci-lint`
