<p align="center">
  <img src="./archon-ui-main/public/archon-main-graphic.png" alt="Archon Main Graphic" width="853" height="422">
</p>

<p align="center">
   <a href="https://trendshift.io/repositories/13964" target="_blank"><img src="https://trendshift.io/api/badge/repositories/13964" alt="coleam00%2FArchon | Trendshift" style="width: 250px; height: 55px;" width="250" height="55"/></a>
</p>

<p align="center">
  <em>Power up your AI coding assistants with your own custom knowledge base, task management, and AI chat assistant as an MCP server</em>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> •
  <a href="#upgrading">Upgrading</a> •
  <a href="#whats-included">What's Included</a> •
  <a href="#-coding-agent-integration">Agent Integration</a> •
  <a href="#architecture">Architecture</a> •
  <a href="#troubleshooting">Troubleshooting</a>
</p>

---

## 🎯 What is Archon?

> Archon is currently in beta! Expect things to not work 100%, and please feel free to share any feedback and contribute with fixes/new features! Thank you to everyone for all the excitement we have for Archon already, as well as the bug reports, PRs, and discussions. It's a lot for our small team to get through but we're committed to addressing everything and making Archon into the best tool it possibly can be!

Archon is the **command center** for AI coding assistants. For you, it's a sleek interface to manage knowledge, context, and tasks for your projects. For the AI coding assistant(s), it's a **Model Context Protocol (MCP) server** to collaborate on and leverage the same knowledge, context, and tasks. Connect Claude Code, Kiro, Cursor, Windsurf, etc. to give your AI agents access to:

- **Your documentation** (crawled websites, uploaded PDFs/docs, or ingested directly from your codebase)
- **Smart search capabilities** with advanced RAG strategies and project-scoped filtering
- **Programmatic ingestion** — coding agents can ingest local project docs into the knowledge base via MCP tools
- **Task management** integrated with your knowledge base
- **AI Chat Assistant** — a built-in chat interface that understands your projects, priorities, and goals to help you brainstorm, prioritize, and manage work
- **Real-time updates** as you add new content and collaborate with your coding assistant on tasks

This new vision for Archon replaces the old one (the agenteer). Archon used to be the AI agent that builds other agents, and now you can use Archon to do that and more.

> It doesn't matter what you're building or if it's a new/existing codebase - Archon's knowledge and task management capabilities will improve the output of **any** AI driven coding.

## 🔗 Important Links

- **[GitHub Discussions](https://github.com/coleam00/Archon/discussions)** - Join the conversation and share ideas about Archon
- **[Contributing Guide](CONTRIBUTING.md)** - How to get involved and contribute to Archon
- **[Introduction Video](https://youtu.be/8pRc_s2VQIo)** - Getting started guide and vision for Archon
- **[Archon Kanban Board](https://github.com/users/coleam00/projects/1)** - Where maintainers are managing issues/features
- **[Dynamous AI Mastery](https://dynamous.ai)** - The birthplace of Archon - come join a vibrant community of other early AI adopters all helping each other transform their careers and businesses!

## Quick Start

<p align="center">
  <a href="https://youtu.be/DMXyDpnzNpY">
    <img src="https://img.youtube.com/vi/DMXyDpnzNpY/maxresdefault.jpg" alt="Archon Setup Tutorial" width="640" />
  </a>
  <br/>
  <em>📺 Click to watch the setup tutorial on YouTube</em>
  <br/>
  <a href="./archon-example-workflow">-> Example AI coding workflow in the video <-</a>
</p>

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [Node.js 18+](https://nodejs.org/) (for hybrid development mode)
- [Supabase](https://supabase.com/) account (free tier or local Supabase both work)
- [OpenAI API key](https://platform.openai.com/api-keys) (Gemini and Ollama are supported too!)
- (OPTIONAL) [Make](https://www.gnu.org/software/make/) (see [Installing Make](#installing-make) below)

### Setup Instructions

1. **Clone Repository**:
   ```bash
   git clone -b stable https://github.com/coleam00/archon.git
   ```
   ```bash
   cd archon
   ```
   
   **Note:** The `stable` branch is recommended for using Archon. If you want to contribute or try the latest features, use the `main` branch with `git clone https://github.com/coleam00/archon.git`
2. **Environment Configuration**:

   ```bash
   cp .env.example .env
   # Edit .env and add your Supabase credentials:
   # SUPABASE_URL=https://your-project.supabase.co
   # SUPABASE_SERVICE_KEY=your-service-key-here
   ```

   IMPORTANT NOTES:
   - For cloud Supabase: They recently introduced a new type of service role key but use the legacy one (the longer one).
   - For local Supabase: Set `SUPABASE_URL` to http://host.docker.internal:8000 (unless you have an IP address set up). To get `SUPABASE_SERVICE_KEY` run `supabase status -o env`.

3. **Database Setup**: In your [Supabase project](https://supabase.com/dashboard) SQL Editor, copy, paste, and execute the contents of `migration/complete_setup.sql`

4. **Start Services** (choose one):

   **Full Docker Mode (Recommended for Normal Archon Usage)**

   ```bash
   docker compose up --build -d
   ```

   This starts all core microservices in Docker:
   - **Server**: Core API and business logic (Port: 8181)
   - **MCP Server**: Protocol interface for AI clients (Port: 8051)
   - **UI**: Web interface (Port: 3737)

   Ports are configurable in your .env as well!

5. **Configure API Keys**:
   - Open http://localhost:3737
   - You'll automatically be brought through an onboarding flow to set your API key (OpenAI is default)

## ⚡ Quick Test

Once everything is running:

1. **Test Web Crawling**: Go to http://localhost:3737 → Knowledge Base → "Crawl Website" → Enter a doc URL (such as https://ai.pydantic.dev/llms.txt)
2. **Test Document Upload**: Knowledge Base → Upload a PDF
3. **Test Projects**: Projects → Create a new project and add tasks
4. **Test Extensions**: Projects → open a project → Extensions tab → click `+ Extension` to link skills, plugins, or commands to the project; Settings → Default Extensions to configure the template for new connections
5. **Test Chat**: Click the floating Archon button (bottom-right) or navigate to `/chat` — the AI assistant can search your knowledge base, analyze projects, and help prioritize work (requires the agents service: `docker compose --profile agents up -d`)
6. **Integrate with your AI coding assistant**: MCP Dashboard → Copy connection config for your AI coding assistant

## 🤖 Coding Agent Integration

Archon can be used directly by AI coding agents to ingest, search, and manage project documentation. This replaces the pattern of reading dozens of documentation files per session with targeted semantic search.

### Connecting Any MCP Client

Add Archon as an MCP server in your client's configuration:

**Claude Code** (`.mcp.json` or `~/.claude/mcp.json`):
```json
{
  "mcpServers": {
    "archon": {
      "type": "streamable-http",
      "url": "http://localhost:8051/mcp"
    }
  }
}
```

**Cursor / Windsurf / Kiro** (MCP settings):
```json
{
  "archon": {
    "url": "http://localhost:8051/mcp",
    "transport": "streamable-http"
  }
}
```

Replace `localhost` with the Archon server's hostname/IP if running on a different machine.

### MCP Tools for Agents

Once connected, agents have access to these tools:

| Tool | Purpose |
|------|---------|
| `manage_rag_source` | Add, sync, or delete knowledge sources (inline docs or URLs) |
| `rag_check_progress` | Poll async ingestion/sync progress |
| `rag_search_knowledge_base` | Semantic search across documentation (supports `project_id` scoping) |
| `rag_search_code_examples` | Search for code snippets extracted from documentation |
| `rag_get_available_sources` | List all knowledge sources |
| `rag_list_pages_for_source` | Browse pages within a source |
| `rag_read_full_page` | Read complete page content |
| `find_projects` / `manage_project` | Project management |
| `find_tasks` / `manage_task` | Task management |
| `find_extensions` / `manage_extensions` | Query and manage skills, plugins, and commands |

### Typical Agent Workflow

1. **Ingest project docs** — Agent reads local `.md` files and sends them to Archon:
   ```
   manage_rag_source(action="add", source_type="inline", title="My Project Docs",
       documents=[{"title": "auth.md", "content": "...", "path": "docs/auth.md"}, ...],
       project_id="proj-123")
   ```
2. **Poll until complete** — `rag_check_progress(progress_id="...")` until `status="completed"`
3. **Search during development** — `rag_search_knowledge_base(query="auth middleware", project_id="proj-123")`
4. **Update after changes** — Delete and re-add, or use `manage_rag_source(action="sync", source_id="...")`

For a comprehensive integration guide, see [`archonIntegration.md`](archonIntegration.md).

### Claude Code Skill

A pre-built Claude Code skill is available at [`integrations/claude-code/`](integrations/claude-code/) that automates the full workflow:

```bash
# Install the skill
cp -r integrations/claude-code/skills/archon-memory ~/.claude/skills/

# Add ambient behavior to your global instructions
cat integrations/claude-code/claude-md-snippet.md >> ~/.claude/CLAUDE.md
```

Then use `/archon-memory` in any Claude Code session:

| Command | Purpose |
|---------|---------|
| `/archon-memory ingest` | Ingest project docs (first time) |
| `/archon-memory sync` | Re-ingest after doc changes |
| `/archon-memory search <query>` | Search project knowledge |
| `/archon-memory search-all <query>` | Search across all projects |
| `/archon-memory shared add <url>` | Add shared cross-project knowledge |
| `/archon-memory tasks` | View project tasks |

See the [integration README](integrations/claude-code/README.md) for full details.

## Installing Make

<details>
<summary><strong>🛠️ Make installation (OPTIONAL - For Dev Workflows)</strong></summary>

### Windows

```bash
# Option 1: Using Chocolatey
choco install make

# Option 2: Using Scoop
scoop install make

# Option 3: Using WSL2
wsl --install
# Then in WSL: sudo apt-get install make
```

### macOS

```bash
# Make comes pre-installed on macOS
# If needed: brew install make
```

### Linux

```bash
# Debian/Ubuntu
sudo apt-get install make

# RHEL/CentOS/Fedora
sudo yum install make
```

</details>

<details>
<summary><strong>🚀 Quick Command Reference for Make</strong></summary>
<br/>

| Command           | Description                                             |
| ----------------- | ------------------------------------------------------- |
| `make dev`        | Start hybrid dev (backend in Docker, frontend local) ⭐ |
| `make dev-docker` | Everything in Docker                                    |
| `make stop`       | Stop all services                                       |
| `make test`       | Run all tests                                           |
| `make lint`       | Run linters                                             |
| `make install`    | Install dependencies                                    |
| `make check`      | Check environment setup                                 |
| `make clean`      | Remove containers and volumes (with confirmation)       |

</details>

## 🔄 Database Reset (Start Fresh if Needed)

If you need to completely reset your database and start fresh:

<details>
<summary>⚠️ <strong>Reset Database - This will delete ALL data for Archon!</strong></summary>

1. **Run Reset Script**: In your Supabase SQL Editor, run the contents of `migration/RESET_DB.sql`

   ⚠️ WARNING: This will delete all Archon specific tables and data! Nothing else will be touched in your DB though.

2. **Rebuild Database**: After reset, run `migration/complete_setup.sql` to create all the tables again.

3. **Restart Services**:

   ```bash
   docker compose --profile full up -d
   ```

4. **Reconfigure**:
   - Select your LLM/embedding provider and set the API key again
   - Re-upload any documents or re-crawl websites

The reset script safely removes all tables, functions, triggers, and policies with proper dependency handling.

</details>

## 📚 Documentation

### Core Services

| Service                    | Container Name             | Default URL           | Purpose                                    |
| -------------------------- | -------------------------- | --------------------- | ------------------------------------------ |
| **Web Interface**          | archon-ui                  | http://localhost:3737 | Main dashboard and controls                |
| **API Service**            | archon-server              | http://localhost:8181 | Web crawling, document processing          |
| **MCP Server**             | archon-mcp                 | http://localhost:8051 | Model Context Protocol interface           |
| **Agents Service**         | archon-agents              | http://localhost:8052 | AI chat, agents, SSE streaming             |
| **Agent Work Orders** *(optional)* | archon-agent-work-orders | http://localhost:8053 | Workflow execution with Claude Code CLI    |  

## Upgrading

To upgrade Archon to the latest version:

1. **Pull latest changes**:
   ```bash
   git pull
   ```

2. **Rebuild and restart containers**:
   ```bash
   docker compose up -d --build
   ```
   This rebuilds containers with the latest code and restarts all services.

3. **Check for database migrations**:
   - Open the Archon settings in your browser: [http://localhost:3737/settings](http://localhost:3737/settings)
   - Navigate to the **Database Migrations** section
   - If there are pending migrations, the UI will display them with clear instructions
   - Click on each migration to view and copy the SQL
   - Run the SQL scripts in your Supabase SQL editor in the order shown

## What's Included

### 🧠 Knowledge Management

- **Smart Web Crawling**: Automatically detects and crawls entire documentation sites, sitemaps, and individual pages
- **Document Processing**: Upload and process PDFs, Word docs, markdown files, and text documents with intelligent chunking
- **Inline Ingestion**: Coding agents can read local project files and ingest them directly into the knowledge base via MCP tools — no manual upload needed
- **Code Example Extraction**: Automatically identifies and indexes code examples from documentation for enhanced search
- **Vector Search**: Advanced semantic search with contextual embeddings for precise knowledge retrieval
- **Project-Scoped Search**: Filter search results by project so different repos' docs don't pollute each other
- **Source Management**: Organize knowledge by source, type, and tags for easy filtering. Add, sync, and delete sources programmatically

### 🤖 AI Integration

- **Model Context Protocol (MCP)**: Connect any MCP-compatible client (Claude Code, Kiro, Cursor, Windsurf, even non-AI coding assistants like Claude Desktop)
- **MCP Tools**: Comprehensive yet simple set of tools for RAG queries, source management, task management, and project operations
- **Source Management via MCP**: `manage_rag_source` tool lets agents add, sync, and delete knowledge sources; `rag_check_progress` tracks async ingestion
- **Claude Code Skill**: Pre-built `/archon-memory` skill for Claude Code that handles ingestion, sync, search, and cross-project knowledge sharing (see [Coding Agent Integration](#-coding-agent-integration))
- **Multi-LLM Support**: Works with OpenAI, OpenRouter, Ollama, and Google Gemini models
- **RAG Strategies**: Hybrid search, contextual embeddings, and result reranking for optimal AI responses
- **Real-time Streaming**: Live responses from AI agents with progress tracking

### 📋 Project & Task Management

- **Hierarchical Projects**: Organize work with projects, features, and tasks in a structured workflow
- **AI-Assisted Creation**: Generate project requirements and tasks using integrated AI agents
- **Project Enrichment**: Add goals, relevance, and AI-suggested categories to projects for better prioritization
- **Document Management**: Version-controlled documents with collaborative editing capabilities
- **Progress Tracking**: Real-time updates and status management across all project activities
- **Project Extensions**: Link skills, plugins, and commands directly to a project from the Extensions tab — the `+ Extension` dialog lets you search and multi-select from all available extensions

### 🧩 Extensions Management

- **Three Extension Types**: Manage **skills** (reusable Claude Code workflows), **plugins** (MCP servers and integrations), and **commands** (Claude Code slash commands) from a single interface
- **Registry Distribution**: Extensions are served from Archon's built-in registry and distributed to connected AI IDEs automatically
- **Project-Scoped Linking**: Attach specific extensions to individual projects so each project's AI context gets the right tools; use the `+ Extension` dialog to select from all available extensions at once
- **Default Extensions Template**: Configure which extensions are automatically installed on every new application that connects via `/archon-setup` — managed in Settings > Default Extensions
- **Auto-Sync to IDEs**: Run `/archon-extension-sync` inside Claude Code to pull the latest extensions from Archon into your local `~/.claude/` directory; setup scripts do this automatically on first connect
- **MCP Tools for Agents**: `find_extensions` and `manage_extensions` let coding agents query and manage extension state programmatically

### ⚙️ Agent Work Orders *(optional)*

- **Workflow Execution Engine**: Orchestrate multi-step AI coding workflows using Claude Code CLI as the execution backend (requires `--profile work-orders` or `make dev-work-orders`)
- **Repository Management**: Agents can clone, branch, and operate on git repositories as part of automated workflows
- **SSE Progress Updates**: Real-time streaming updates as workflow steps execute
- **Standalone Microservice**: Runs independently on port 8053 so it doesn't add overhead to the core stack

### 💬 AI Chat Assistant

- **Interactive Chat Interface**: Built-in AI assistant accessible via a floating sidebar or a dedicated `/chat` page
- **Project Awareness**: Chat with context about your projects, tasks, knowledge base, and session history
- **Prioritization Engine**: Ask "What should I work on?" and get recommendations based on momentum, strategic alignment, dependencies, and effort matching
- **Cross-Project Synergy**: Discover how your projects could work together or share patterns
- **User Profile & Onboarding**: AI-guided onboarding builds your profile so the assistant understands your role, goals, and priorities
- **Configurable Models**: Choose between Claude, GPT, and other providers per conversation
- **Advisor & Action Mode**: Read-only advisor by default, with an unlockable action mode that can create tasks, update projects, and more (with approval)
- **Tool-Use Visibility**: See what the AI is searching and analyzing in real-time via collapsible tool cards
- **Persistent & Searchable History**: All conversations are saved and full-text searchable
- **SSE Streaming**: Token-by-token streaming with heartbeat keepalive for responsive interactions

### 🔄 Real-time Updates

- **HTTP Polling**: Smart, visibility-aware polling with ETag caching for bandwidth efficiency
- **SSE Streaming**: Server-sent events for chat responses and agent operations
- **Background Processing**: Asynchronous operations that don't block the user interface
- **Health Monitoring**: Built-in service health checks and automatic reconnection

## Architecture

### Microservices Structure

Archon uses true microservices architecture with clear separation of concerns:

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend UI   │    │  Server (API)   │    │   MCP Server    │    │ Agents Service  │
│                 │    │                 │    │                 │    │                 │
│  React + Vite   │◄──►│    FastAPI      │◄──►│    Lightweight  │◄──►│   PydanticAI    │
│  TanStack Query │    │    REST APIs    │    │    HTTP Wrapper │    │   ChatAgent     │
│  Port 3737      │    │    Port 8181    │    │    Port 8051    │    │   Port 8052     │
└─────────────────┘    └─────────────────┘    └─────────────────┘    └─────────────────┘
         │                        │                        │                        │
         │   SSE (chat stream)    │                        │                        │
         └────────────────────────┼────────────────────────┼────────────────────────┘
                                  │                        │
                         ┌─────────────────┐               │
                         │    Database     │               │
                         │                 │               │
                         │    Supabase     │◄──────────────┘
                         │    PostgreSQL   │
                         │    PGVector     │
                         └─────────────────┘
```

### Service Responsibilities

| Service                  | Location                       | Purpose                          | Key Features                                                       |
| ------------------------ | ------------------------------ | -------------------------------- | ------------------------------------------------------------------ |
| **Frontend**             | `archon-ui-main/`              | Web interface and dashboard      | React, TypeScript, TailwindCSS, TanStack Query                     |
| **Server**               | `python/src/server/`           | Core business logic and APIs     | FastAPI, service layer, REST APIs, ML/AI operations                |
| **MCP Server**           | `python/src/mcp_server/`       | MCP protocol interface           | Lightweight HTTP wrapper, MCP tools, session management            |
| **Agents**               | `python/src/agents/`           | PydanticAI agent hosting         | ChatAgent, RAG/Document agents, SSE streaming                      |
| **Agent Work Orders** *(optional)* | `python/src/agent_work_orders/` | Workflow execution engine | Claude Code CLI automation, repository management, SSE updates |

### Communication Patterns

- **HTTP-based**: All inter-service communication uses REST APIs
- **SSE Streaming**: Real-time chat responses from Agent Service to Frontend
- **HTTP Polling**: Smart, visibility-aware polling with ETag caching for data freshness
- **MCP Protocol**: AI clients connect to MCP Server via streamable HTTP
- **No Direct Imports**: Services are truly independent with no shared code dependencies

### Key Architectural Benefits

- **Lightweight Containers**: Each service contains only required dependencies
- **Independent Scaling**: Services can be scaled independently based on load
- **Development Flexibility**: Teams can work on different services without conflicts
- **Technology Diversity**: Each service uses the best tools for its specific purpose

## 🔧 Configuring Custom Ports & Hostname

By default, Archon services run on the following ports:

- **archon-ui**: 3737
- **archon-server**: 8181
- **archon-mcp**: 8051
- **archon-agents**: 8052 (optional)
- **archon-agent-work-orders**: 8053 (optional)

### Changing Ports

To use custom ports, add these variables to your `.env` file:

```bash
# Service Ports Configuration
ARCHON_UI_PORT=3737
ARCHON_SERVER_PORT=8181
ARCHON_MCP_PORT=8051
ARCHON_AGENTS_PORT=8052
AGENT_WORK_ORDERS_PORT=8053
```

Example: Running on different ports:

```bash
ARCHON_SERVER_PORT=8282
ARCHON_MCP_PORT=8151
```

### Configuring Hostname

By default, Archon uses `localhost` as the hostname. You can configure a custom hostname or IP address by setting the `HOST` variable in your `.env` file:

```bash
# Hostname Configuration
HOST=localhost  # Default

# Examples of custom hostnames:
HOST=192.168.1.100     # Use specific IP address
HOST=archon.local      # Use custom domain
HOST=myserver.com      # Use public domain
```

This is useful when:

- Running Archon on a different machine and accessing it remotely
- Using a custom domain name for your installation
- Deploying in a network environment where `localhost` isn't accessible

After changing hostname or ports:

1. Restart Docker containers: `docker compose down && docker compose --profile full up -d`
2. Access the UI at: `http://${HOST}:${ARCHON_UI_PORT}`
3. Update your AI client configuration with the new hostname and MCP port

## 🔧 Development

### Quick Start

```bash
# Install dependencies
make install

# Start development (recommended)
make dev        # Backend in Docker, frontend local with hot reload

# Alternative: Everything in Docker
make dev-docker # All services in Docker

# Stop everything (local FE needs to be stopped manually)
make stop
```

### Development Modes

#### Hybrid Mode (Recommended) - `make dev`

Best for active development with instant frontend updates:

- Backend services run in Docker (isolated, consistent)
- Frontend runs locally with hot module replacement
- Instant UI updates without Docker rebuilds

#### Full Docker Mode - `make dev-docker`

For all services in Docker environment:

- All services run in Docker containers
- Better for integration testing
- Slower frontend updates

### Testing & Code Quality

```bash
# Run tests
make test       # Run all tests
make test-fe    # Run frontend tests
make test-be    # Run backend tests

# Run linters
make lint       # Lint all code
make lint-fe    # Lint frontend code
make lint-be    # Lint backend code

# Check environment
make check      # Verify environment setup

# Clean up
make clean      # Remove containers and volumes (asks for confirmation)
```

### Viewing Logs

```bash
# View logs using Docker Compose directly
docker compose logs -f              # All services
docker compose logs -f archon-server # API server
docker compose logs -f archon-mcp    # MCP server
docker compose logs -f archon-ui     # Frontend
```

**Note**: The backend services are configured with `--reload` flag in their uvicorn commands and have source code mounted as volumes for automatic hot reloading when you make changes.

## Troubleshooting

### Common Issues and Solutions

#### Port Conflicts

If you see "Port already in use" errors:

```bash
# Check what's using a port (e.g., 3737)
lsof -i :3737

# Stop all containers and local services
make stop

# Change the port in .env
```

#### Docker Permission Issues (Linux)

If you encounter permission errors with Docker:

```bash
# Add your user to the docker group
sudo usermod -aG docker $USER

# Log out and back in, or run
newgrp docker
```

#### Windows-Specific Issues

- **Make not found**: Install Make via Chocolatey, Scoop, or WSL2 (see [Installing Make](#installing-make))
- **Line ending issues**: Configure Git to use LF endings:
  ```bash
  git config --global core.autocrlf false
  ```

#### Frontend Can't Connect to Backend

- Check backend is running: `curl http://localhost:8181/health`
- Verify port configuration in `.env`
- For custom ports, ensure both `ARCHON_SERVER_PORT` and `VITE_ARCHON_SERVER_PORT` are set

#### Docker Compose Hangs

If `docker compose` commands hang:

```bash
# Reset Docker Compose
docker compose down --remove-orphans
docker system prune -f

# Restart Docker Desktop (if applicable)
```

#### Hot Reload Not Working

- **Frontend**: Ensure you're running in hybrid mode (`make dev`) for best HMR experience
- **Backend**: Check that volumes are mounted correctly in `docker-compose.yml`
- **File permissions**: On some systems, mounted volumes may have permission issues

## 📈 Progress

<p align="center">
  <a href="https://star-history.com/#coleam00/Archon&Date">
    <img src="https://api.star-history.com/svg?repos=coleam00/Archon&type=Date" width="500" alt="Star History Chart">
  </a>
</p>

## 📄 License

Archon Community License (ACL) v1.2 - see [LICENSE](LICENSE) file for details.

**TL;DR**: Archon is free, open, and hackable. Run it, fork it, share it - just don't sell it as-a-service without permission.
