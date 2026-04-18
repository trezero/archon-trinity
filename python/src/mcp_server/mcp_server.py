"""
MCP Server for Archon (Microservices Version)

This is the MCP server that uses HTTP calls to other services
instead of importing heavy dependencies directly. This significantly reduces
the container size from 1.66GB to ~150MB.

Modules:
- RAG Module: RAG queries, search, and source management via HTTP
- Project Module: Task and project management via HTTP
- Health & Session: Local operations

Note: Crawling and document upload operations are handled directly by the
API service and frontend, not through MCP tools.
"""

import json
import logging
import os
import sys
import threading
import time
import traceback
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from mcp.server.fastmcp import Context, FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse

# Add the project root to Python path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Load environment variables from the project root .env file
project_root = Path(__file__).resolve().parent.parent
dotenv_path = project_root / ".env"
load_dotenv(dotenv_path, override=True)

# Configure logging FIRST before any imports that might use it
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("/tmp/mcp_server.log", mode="a")
        if os.path.exists("/tmp")
        else logging.NullHandler(),
    ],
)
logger = logging.getLogger(__name__)

# Import Logfire configuration
from src.server.config.logfire_config import mcp_logger, setup_logfire

# Import service client for HTTP calls
from src.server.services.mcp_service_client import get_mcp_service_client

# Import session management
from src.server.services.mcp_session_manager import get_session_manager

# Global initialization lock and flag
_initialization_lock = threading.Lock()
_initialization_complete = False
_shared_context = None

server_host = "0.0.0.0"  # Listen on all interfaces

# Require ARCHON_MCP_PORT to be set
mcp_port = os.getenv("ARCHON_MCP_PORT")
if not mcp_port:
    raise ValueError(
        "ARCHON_MCP_PORT environment variable is required. "
        "Please set it in your .env file or environment. "
        "Default value: 8051"
    )
server_port = int(mcp_port)


@dataclass
class ArchonContext:
    """
    Context for MCP server.
    No heavy dependencies - just service client for HTTP calls.
    """

    service_client: Any
    health_status: dict = None
    startup_time: float = None

    def __post_init__(self):
        if self.health_status is None:
            self.health_status = {
                "status": "healthy",
                "api_service": False,
                "agents_service": False,
                "last_health_check": None,
            }
        if self.startup_time is None:
            self.startup_time = time.time()


async def perform_health_checks(context: ArchonContext):
    """Perform health checks on dependent services via HTTP."""
    try:
        # Check dependent services
        service_health = await context.service_client.health_check()

        context.health_status["api_service"] = service_health.get("api_service", False)
        context.health_status["agents_service"] = service_health.get("agents_service", False)

        # Overall status
        all_critical_ready = context.health_status["api_service"]

        context.health_status["status"] = "healthy" if all_critical_ready else "degraded"
        context.health_status["last_health_check"] = datetime.now().isoformat()

        if not all_critical_ready:
            logger.warning(f"Health check failed: {context.health_status}")
        else:
            logger.info("Health check passed - dependent services healthy")

    except Exception as e:
        logger.error(f"Health check error: {e}")
        context.health_status["status"] = "unhealthy"
        context.health_status["last_health_check"] = datetime.now().isoformat()


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[ArchonContext]:
    """
    Lifecycle manager - no heavy dependencies.
    """
    global _initialization_complete, _shared_context

    # Quick check without lock
    if _initialization_complete and _shared_context:
        logger.info("♻️ Reusing existing context for new SSE connection")
        yield _shared_context
        return

    # Acquire lock for initialization
    with _initialization_lock:
        # Double-check pattern
        if _initialization_complete and _shared_context:
            logger.info("♻️ Reusing existing context for new SSE connection")
            yield _shared_context
            return

        logger.info("🚀 Starting MCP server...")

        try:
            # Initialize session manager
            logger.info("🔐 Initializing session manager...")
            session_manager = get_session_manager()
            logger.info("✓ Session manager initialized")

            # Initialize service client for HTTP calls
            logger.info("🌐 Initializing service client...")
            service_client = get_mcp_service_client()
            logger.info("✓ Service client initialized")

            # Create context
            context = ArchonContext(service_client=service_client)

            # Perform initial health check
            await perform_health_checks(context)

            logger.info("✓ MCP server ready")

            # Store context globally
            _shared_context = context
            _initialization_complete = True

            yield context

        except Exception as e:
            logger.error(f"💥 Critical error in lifespan setup: {e}")
            logger.error(traceback.format_exc())
            raise
        finally:
            # Clean up resources
            logger.info("🧹 Cleaning up MCP server...")
            logger.info("✅ MCP server shutdown complete")


# Define MCP instructions for Claude Code and other clients
MCP_INSTRUCTIONS = """
# Archon MCP Server Instructions

## 🚨 CRITICAL RULES (ALWAYS FOLLOW)
1. **Task Management**: ALWAYS use Archon MCP tools for task management.
   - Combine with your local TODO tools for granular tracking

2. **Research First**: Before implementing, use rag_search_knowledge_base and rag_search_code_examples
3. **Task-Driven Development**: Never code without checking current tasks first

## 🎯 Targeted Documentation Search

When searching specific documentation (very common!):
1. **Get available sources**: `rag_get_available_sources()` - Returns list with id, title, url
2. **Find source ID**: Match user's request to source title (e.g., "PydanticAI docs" -> find ID)
3. **Filter search**: `rag_search_knowledge_base(query="...", source_id="src_xxx", match_count=5)`

Examples:
- User: "Search the Supabase docs for vector functions"
  1. Call `rag_get_available_sources()`
  2. Find Supabase source ID from results (e.g., "src_abc123")
  3. Call `rag_search_knowledge_base(query="vector functions", source_id="src_abc123")`

- User: "Find authentication examples in the MCP documentation"
  1. Call `rag_get_available_sources()`
  2. Find MCP docs source ID
  3. Call `rag_search_code_examples(query="authentication", source_id="src_def456")`

IMPORTANT: Always use source_id (not URLs or domain names) for filtering!

## 📋 Core Workflow

### Task Management Cycle
1. **Get current task**: `list_tasks(task_id="...")` 
2. **Search/List tasks**: `list_tasks(query="auth", filter_by="status", filter_value="todo")`
3. **Mark as doing**: `manage_task("update", task_id="...", status="doing")`
4. **Research phase**:
   - `rag_search_knowledge_base(query="...", match_count=5)`
   - `rag_search_code_examples(query="...", match_count=3)`
5. **Implementation**: Code based on research findings
6. **Mark for review**: `manage_task("update", task_id="...", status="review")`
7. **Get next task**: `list_tasks(filter_by="status", filter_value="todo")`

### Consolidated Task Tools (Optimized ~2 tools from 5)
- `list_tasks(query=None, task_id=None, filter_by=None, filter_value=None, per_page=10)`
  - list + search + get in one tool
  - Search with keyword query parameter (optional)
  - task_id parameter for getting single task (full details)
  - Filter by status, project, or assignee
  - **Optimized**: Returns truncated descriptions and array counts (lists only)
  - **Default**: 10 items per page (was 50)
- `manage_task(action, task_id=None, project_id=None, ...)`
  - **Consolidated**: create + update + delete in one tool
  - action: "create" | "update" | "delete"
  - Examples:
    - `manage_task("create", project_id="p-1", title="Fix auth")`
    - `manage_task("update", task_id="t-1", status="doing")`
    - `manage_task("delete", task_id="t-1")`

## 🏗️ Project Management

### Project Tools
- `list_projects(project_id=None, query=None, page=1, per_page=10)`
  - List all projects, search by query, or get specific project by ID
- `manage_project(action, project_id=None, title=None, description=None, github_repo=None)`
  - Actions: "create", "update", "delete"

### Document Tools
- `list_documents(project_id, document_id=None, query=None, document_type=None, page=1, per_page=10)`
  - List project documents, search, filter by type, or get specific document
- `manage_document(action, project_id, document_id=None, title=None, document_type=None, content=None, ...)`
  - Actions: "create", "update", "delete"

## 🔍 Research Patterns

### CRITICAL: Keep Queries Short and Focused!
Vector search works best with 2-5 keywords, NOT long sentences or keyword dumps.

✅ GOOD Queries (concise, focused):
- `rag_search_knowledge_base(query="vector search pgvector")`
- `rag_search_code_examples(query="React useState")`
- `rag_search_knowledge_base(query="authentication JWT")`
- `rag_search_code_examples(query="FastAPI middleware")`

❌ BAD Queries (too long, unfocused):
- `rag_search_knowledge_base(query="how to implement vector search with pgvector in PostgreSQL for semantic similarity matching with OpenAI embeddings")`
- `rag_search_code_examples(query="React hooks useState useEffect useContext useReducer useMemo useCallback")`

### Query Construction Tips:
- Extract 2-5 most important keywords from the user's request
- Focus on technical terms and specific technologies
- Omit filler words like "how to", "implement", "create", "example"
- For multi-concept searches, do multiple focused queries instead of one broad query

## 📊 Task Status Flow
`todo` → `doing` → `review` → `done`
- Only ONE task in 'doing' status at a time
- Use 'review' for completed work awaiting validation
- Mark tasks 'done' only after verification

## 📝 Task Granularity Guidelines

### Project Scope Determines Task Granularity

**For Feature-Specific Projects** (project = single feature):
Create granular implementation tasks:
- "Set up development environment"
- "Install required dependencies"
- "Create database schema"
- "Implement API endpoints"
- "Add frontend components"
- "Write unit tests"
- "Add integration tests"
- "Update documentation"

**For Codebase-Wide Projects** (project = entire application):
Create feature-level tasks:
- "Implement user authentication feature"
- "Add payment processing system"
- "Create admin dashboard"

## 📦 Source Management

### manage_rag_source — Add, Sync, and Delete Knowledge Sources
- `manage_rag_source(action="add", source_type="url", title="Example Docs", url="https://docs.example.com")`
  - Crawls a website and ingests its pages into the knowledge base
  - Returns a `progress_id` and `source_id` for tracking the async operation
- `manage_rag_source(action="add", source_type="inline", title="Design Notes", documents='[{"title": "notes.md", "content": "# Notes..."}]')`
  - Ingests inline documents directly (no crawling)
  - Returns a `progress_id` for tracking
- `manage_rag_source(action="sync", source_id="src_xxx")`
  - Re-ingests an existing source to pick up changes (re-crawls URLs, re-processes inline content)
  - Returns a `progress_id` for tracking
- `manage_rag_source(action="delete", source_id="src_xxx")`
  - Removes source and all its documents from the knowledge base

**IMPORTANT**: Use "add" once per source, then "sync" for updates. Do NOT add the same URL twice — it creates duplicates.

## ⏳ Progress Tracking

### rag_check_progress — Poll Async Operations
- `rag_check_progress(progress_id="prog_xxx")`
  - Returns status (`pending`, `processing`, `completed`, `failed`), progress percentage, and details
  - Poll every few seconds until status is `completed` or `failed`

## 🔄 Ingestion Workflow

Recommended flow for adding knowledge:
1. **Add source**: `manage_rag_source(action="add", source_type="url", url="...")` → get `progress_id`
2. **Poll progress**: `rag_check_progress(progress_id="...")` until completed
3. **Search**: `rag_search_knowledge_base(query="...")` to verify content
4. **Update later**: `manage_rag_source(action="sync", source_id="...")` → poll again

## 🎯 Project-Scoped Search

Use `project_id` to restrict searches to sources linked to a specific project:
- `rag_search_knowledge_base(query="auth flow", project_id="proj_xxx")`
- `rag_search_code_examples(query="middleware", project_id="proj_xxx")`

Omit `project_id` to search across all sources.
"""

# Initialize the main FastMCP server with fixed configuration
try:
    logger.info("🏗️ MCP SERVER INITIALIZATION:")
    logger.info("   Server Name: archon-mcp-server")
    logger.info("   Description: MCP server using HTTP calls")

    mcp = FastMCP(
        "archon-mcp-server",
        description="MCP server for Archon - uses HTTP calls to other services",
        instructions=MCP_INSTRUCTIONS,
        lifespan=lifespan,
        host=server_host,
        port=server_port,
    )
    logger.info("✓ FastMCP server instance created successfully")

except Exception as e:
    logger.error(f"✗ Failed to create FastMCP server: {e}")
    logger.error(traceback.format_exc())
    raise


# Health check endpoint
@mcp.tool()
async def health_check(ctx: Context) -> str:
    """
    Check health status of MCP server and dependencies.

    Returns:
        JSON with health status, uptime, and service availability
    """
    try:
        # Try to get the lifespan context
        context = getattr(ctx.request_context, "lifespan_context", None)

        if context is None:
            # Server starting up
            return json.dumps({
                "success": True,
                "status": "starting",
                "message": "MCP server is initializing...",
                "timestamp": datetime.now().isoformat(),
            })

        # Server is ready - perform health checks
        if hasattr(context, "health_status") and context.health_status:
            await perform_health_checks(context)

            return json.dumps({
                "success": True,
                "health": context.health_status,
                "uptime_seconds": time.time() - context.startup_time,
                "timestamp": datetime.now().isoformat(),
            })
        else:
            return json.dumps({
                "success": True,
                "status": "ready",
                "message": "MCP server is running",
                "timestamp": datetime.now().isoformat(),
            })

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return json.dumps({
            "success": False,
            "error": f"Health check failed: {str(e)}",
            "timestamp": datetime.now().isoformat(),
        })


# Session management endpoint
@mcp.tool()
async def session_info(ctx: Context) -> str:
    """
    Get current and active session information.

    Returns:
        JSON with active sessions count and server uptime
    """
    try:
        session_manager = get_session_manager()

        # Build session info
        session_info_data = {
            "active_sessions": session_manager.get_active_session_count(),
            "session_timeout": session_manager.timeout,
        }

        # Add server uptime
        context = getattr(ctx.request_context, "lifespan_context", None)
        if context and hasattr(context, "startup_time"):
            session_info_data["server_uptime_seconds"] = time.time() - context.startup_time

        return json.dumps({
            "success": True,
            "session_management": session_info_data,
            "timestamp": datetime.now().isoformat(),
        })

    except Exception as e:
        logger.error(f"Session info failed: {e}")
        return json.dumps({
            "success": False,
            "error": f"Failed to get session info: {str(e)}",
            "timestamp": datetime.now().isoformat(),
        })


# Import and register modules
def register_modules():
    """Register all MCP tool modules."""
    logger.info("🔧 Registering MCP tool modules...")

    modules_registered = 0

    # Import and register RAG module (HTTP-based version)
    try:
        from src.mcp_server.features.rag import register_rag_tools

        register_rag_tools(mcp)
        modules_registered += 1
        logger.info("✓ RAG module registered (HTTP-based)")
    except ImportError as e:
        logger.warning(f"⚠ RAG module not available: {e}")
    except Exception as e:
        logger.error(f"✗ Error registering RAG module: {e}")
        logger.error(traceback.format_exc())

    # Import and register all feature tools - separated and focused

    # Project Management Tools
    try:
        from src.mcp_server.features.projects import register_project_tools

        register_project_tools(mcp)
        modules_registered += 1
        logger.info("✓ Project tools registered")
    except ImportError as e:
        # Module not found - this is acceptable in modular architecture
        logger.warning(f"⚠ Project tools module not available (optional): {e}")
    except (SyntaxError, NameError, AttributeError) as e:
        # Code errors that should not be ignored
        logger.error(f"✗ Code error in project tools - MUST FIX: {e}")
        logger.error(traceback.format_exc())
        raise  # Re-raise to prevent running with broken code
    except Exception as e:
        # Unexpected errors during registration
        logger.error(f"✗ Failed to register project tools: {e}")
        logger.error(traceback.format_exc())
        # Don't raise - allow other modules to register

    # Task Management Tools
    try:
        from src.mcp_server.features.tasks import register_task_tools

        register_task_tools(mcp)
        modules_registered += 1
        logger.info("✓ Task tools registered")
    except ImportError as e:
        logger.warning(f"⚠ Task tools module not available (optional): {e}")
    except (SyntaxError, NameError, AttributeError) as e:
        logger.error(f"✗ Code error in task tools - MUST FIX: {e}")
        logger.error(traceback.format_exc())
        raise
    except Exception as e:
        logger.error(f"✗ Failed to register task tools: {e}")
        logger.error(traceback.format_exc())

    # Document Management Tools
    try:
        from src.mcp_server.features.documents import register_document_tools

        register_document_tools(mcp)
        modules_registered += 1
        logger.info("✓ Document tools registered")
    except ImportError as e:
        logger.warning(f"⚠ Document tools module not available (optional): {e}")
    except (SyntaxError, NameError, AttributeError) as e:
        logger.error(f"✗ Code error in document tools - MUST FIX: {e}")
        logger.error(traceback.format_exc())
        raise
    except Exception as e:
        logger.error(f"✗ Failed to register document tools: {e}")
        logger.error(traceback.format_exc())

    # Version Management Tools
    try:
        from src.mcp_server.features.documents import register_version_tools

        register_version_tools(mcp)
        modules_registered += 1
        logger.info("✓ Version tools registered")
    except ImportError as e:
        logger.warning(f"⚠ Version tools module not available (optional): {e}")
    except (SyntaxError, NameError, AttributeError) as e:
        logger.error(f"✗ Code error in version tools - MUST FIX: {e}")
        logger.error(traceback.format_exc())
        raise
    except Exception as e:
        logger.error(f"✗ Failed to register version tools: {e}")
        logger.error(traceback.format_exc())

    # Feature Management Tools
    try:
        from src.mcp_server.features.feature_tools import register_feature_tools

        register_feature_tools(mcp)
        modules_registered += 1
        logger.info("✓ Feature tools registered")
    except ImportError as e:
        logger.warning(f"⚠ Feature tools module not available (optional): {e}")
    except (SyntaxError, NameError, AttributeError) as e:
        logger.error(f"✗ Code error in feature tools - MUST FIX: {e}")
        logger.error(traceback.format_exc())
        raise
    except Exception as e:
        logger.error(f"✗ Failed to register feature tools: {e}")
        logger.error(traceback.format_exc())

    # Extension Management Tools
    try:
        from src.mcp_server.features.extensions import register_extension_tools

        register_extension_tools(mcp)
        modules_registered += 1
        logger.info("✓ Extension tools registered")
    except ImportError as e:
        logger.warning(f"⚠ Extension tools module not available (optional): {e}")
    except (SyntaxError, NameError, AttributeError) as e:
        logger.error(f"✗ Code error in extension tools - MUST FIX: {e}")
        logger.error(traceback.format_exc())
        raise
    except Exception as e:
        logger.error(f"✗ Failed to register extension tools: {e}")
        logger.error(traceback.format_exc())

    # Session Memory Tools
    try:
        from src.mcp_server.features.sessions import register_session_tools

        register_session_tools(mcp)
        modules_registered += 1
        logger.info("✓ Session tools registered")
    except ImportError as e:
        logger.warning(f"⚠ Session tools module not available (optional): {e}")
    except (SyntaxError, NameError, AttributeError) as e:
        logger.error(f"✗ Code error in session tools - MUST FIX: {e}")
        logger.error(traceback.format_exc())
        raise
    except Exception as e:
        logger.error(f"✗ Failed to register session tools: {e}")
        logger.error(traceback.format_exc())

    # Materialization Tools
    try:
        from src.mcp_server.features.materialization import register_materialization_tools

        register_materialization_tools(mcp)
        modules_registered += 1
        logger.info("✓ Materialization module registered (HTTP-based)")
    except ImportError as e:
        logger.warning(f"⚠ Materialization module not available (optional): {e}")
    except (SyntaxError, NameError, AttributeError) as e:
        logger.error(f"✗ Code error in materialization tools - MUST FIX: {e}")
        logger.error(traceback.format_exc())
        raise
    except Exception as e:
        logger.error(f"✗ Failed to register materialization tools: {e}")
        logger.error(traceback.format_exc())

    # LeaveOff Point Tools
    try:
        from src.mcp_server.features.leaveoff import register_leaveoff_tools

        register_leaveoff_tools(mcp)
        modules_registered += 1
        logger.info("✓ LeaveOff Point module registered (HTTP-based)")
    except ImportError as e:
        logger.warning(f"⚠ LeaveOff Point module not available (optional): {e}")
    except (SyntaxError, NameError, AttributeError) as e:
        logger.error(f"✗ Code error in leaveoff tools - MUST FIX: {e}")
        logger.error(traceback.format_exc())
        raise
    except Exception as e:
        logger.error(f"✗ Failed to register leaveoff tools: {e}")
        logger.error(traceback.format_exc())

    # Postman Integration Tools
    try:
        from src.mcp_server.features.postman import register_postman_tools

        register_postman_tools(mcp)
        modules_registered += 1
        logger.info("✓ Postman integration module registered (HTTP-based)")
    except ImportError as e:
        logger.warning(f"⚠ Postman integration module not available (optional): {e}")
    except (SyntaxError, NameError, AttributeError) as e:
        logger.error(f"✗ Code error in postman tools - MUST FIX: {e}")
        logger.error(traceback.format_exc())
        raise
    except Exception as e:
        logger.error(f"✗ Failed to register postman tools: {e}")
        logger.error(traceback.format_exc())

    logger.info(f"📦 Total modules registered: {modules_registered}")

    if modules_registered == 0:
        logger.error("💥 No modules were successfully registered!")
        raise RuntimeError("No MCP modules available")


# Register all modules when this file is imported
try:
    register_modules()
except Exception as e:
    logger.error(f"💥 Critical error during module registration: {e}")
    logger.error(traceback.format_exc())
    raise


# Track server start time at module level for health checks
_server_start_time = time.time()


# Define health endpoint function at module level
async def http_health_endpoint(request: Request):
    """HTTP health check endpoint for monitoring systems."""
    logger.info("Health endpoint called via HTTP")
    try:
        # Try to get the shared context for detailed health info
        if _shared_context and hasattr(_shared_context, "health_status"):
            # Use actual server startup time for consistency with MCP health_check tool
            uptime = time.time() - _shared_context.startup_time
            await perform_health_checks(_shared_context)

            return JSONResponse({
                "success": True,
                "health": _shared_context.health_status,
                "uptime_seconds": uptime,
                "timestamp": datetime.now().isoformat(),
            })
        else:
            # Server starting up or no MCP connections yet - use module load time as fallback
            uptime = time.time() - _server_start_time
            return JSONResponse({
                "success": True,
                "status": "ready",
                "uptime_seconds": uptime,
                "message": "MCP server is running (no active connections yet)",
                "timestamp": datetime.now().isoformat(),
            })
    except Exception as e:
        logger.error(f"HTTP health check failed: {e}", exc_info=True)
        return JSONResponse({
            "success": False,
            "error": f"Health check failed: {str(e)}",
            "uptime_seconds": time.time() - _server_start_time,
            "timestamp": datetime.now().isoformat(),
        }, status_code=500)


# Register health endpoint using FastMCP's custom_route decorator
try:
    mcp.custom_route("/health", methods=["GET"])(http_health_endpoint)
    logger.info("✓ HTTP /health endpoint registered successfully")
except Exception as e:
    logger.error(f"✗ Failed to register /health endpoint: {e}")
    logger.error(traceback.format_exc())


# ── Setup file endpoints ────────────────────────────────────────────────────


def _get_setup_urls(request: Request) -> tuple[str, str]:
    """Derive (api_url, mcp_url) for baking into setup scripts.

    When the request comes through the Vite proxy, X-Forwarded-Host
    carries the external hostname (e.g. '192.168.1.10:3737').
    We extract just the hostname and combine with the known service ports
    so users outside Docker get reachable URLs.
    Falls back to ARCHON_HOST env var (the externally-reachable address).
    """
    forwarded_host = request.headers.get("x-forwarded-host", "")
    if forwarded_host:
        hostname = forwarded_host.split(":")[0]
    else:
        hostname = request.url.hostname or os.environ.get("ARCHON_HOST", "localhost")

    mcp_port = os.environ.get("ARCHON_MCP_PORT", "8051")
    api_port = os.environ.get("ARCHON_SERVER_PORT", "8181")
    return f"http://{hostname}:{api_port}", f"http://{hostname}:{mcp_port}"


async def http_archon_setup_sh(request: Request) -> PlainTextResponse:
    """Serve archonSetup.sh with API and MCP URLs baked in."""
    api_url, mcp_url = _get_setup_urls(request)
    script = _render_setup_sh(api_url, mcp_url)
    return PlainTextResponse(
        script,
        headers={"Content-Disposition": 'attachment; filename="archonSetup.sh"'},
    )


async def http_agent_work_orders_setup_sh(request: Request) -> PlainTextResponse:
    """Serve agentWorkOrderSetup.sh with URLs baked in."""
    api_url, mcp_url = _get_setup_urls(request)
    script = _render_agent_work_orders_setup_sh(api_url, mcp_url)
    return PlainTextResponse(
        script,
        headers={"Content-Disposition": 'attachment; filename="agentWorkOrderSetup.sh"'},
    )


async def http_archon_setup_bat(request: Request) -> PlainTextResponse:
    """Serve archonSetup.bat with API and MCP URLs baked in."""
    api_url, mcp_url = _get_setup_urls(request)
    script = _render_setup_bat(api_url, mcp_url)
    return PlainTextResponse(
        script,
        headers={"Content-Disposition": 'attachment; filename="archonSetup.bat"'},
    )


async def http_archon_setup_md(request: Request) -> PlainTextResponse:
    """Serve the /archon-setup Claude Code slash command."""
    content = _render_setup_md()
    return PlainTextResponse(content)


async def http_scan_projects_md(request: Request) -> PlainTextResponse:
    """Serve the /scan-projects Claude Code slash command."""
    content = _render_command_md("scan-projects.md")
    return PlainTextResponse(content)


async def http_claude_md_snippet(request: Request) -> PlainTextResponse:
    """Serve the recommended Archon CLAUDE.md rules snippet."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "integrations" / "claude-code" / "claude-md-snippet.md"
        if candidate.exists():
            return PlainTextResponse(candidate.read_text())
    return PlainTextResponse("", status_code=404)


def _render_setup_sh(api_url: str, mcp_url: str) -> str:
    """Generate archonSetup.sh with API and MCP URLs injected."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "integrations" / "claude-code" / "setup" / "archonSetup.sh"
        if candidate.exists():
            content = candidate.read_text()
            content = content.replace("{{ARCHON_API_URL}}", api_url)
            content = content.replace("{{ARCHON_MCP_URL}}", mcp_url)
            return content
    raise FileNotFoundError("archonSetup.sh template not found")


def _render_agent_work_orders_setup_sh(api_url: str, mcp_url: str) -> str:
    """Read agentWorkOrderSetup.sh template, substitute placeholders, return."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "integrations" / "claude-code" / "setup" / "agentWorkOrderSetup.sh"
        if candidate.exists():
            content = candidate.read_text()
            content = content.replace("{{ARCHON_API_URL}}", api_url)
            content = content.replace("{{ARCHON_MCP_URL}}", mcp_url)
            return content
    raise FileNotFoundError("agentWorkOrderSetup.sh template not found")


def _render_setup_bat(api_url: str, mcp_url: str) -> str:
    """Generate archonSetup.bat with API and MCP URLs injected."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "integrations" / "claude-code" / "setup" / "archonSetup.bat"
        if candidate.exists():
            content = candidate.read_text()
            content = content.replace("{{ARCHON_API_URL}}", api_url)
            content = content.replace("{{ARCHON_MCP_URL}}", mcp_url)
            # Ensure Windows CRLF line endings — cmd.exe fails with Unix LF
            content = content.replace("\r\n", "\n").replace("\n", "\r\n")
            return content
    raise FileNotFoundError("archonSetup.bat template not found")


def _render_setup_md() -> str:
    """Return the /archon-setup Claude Code slash command content."""
    return _render_command_md("archon-setup.md")


def _render_command_md(filename: str) -> str:
    """Return a Claude Code slash command file from integrations/claude-code/commands/."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "integrations" / "claude-code" / "commands" / filename
        if candidate.exists():
            return candidate.read_text()
    raise FileNotFoundError(f"{filename} not found")


async def http_plugin_manifest(request: Request) -> JSONResponse:
    """Return the archon-memory plugin manifest."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "integrations" / "claude-code" / "plugins" / "archon-memory" / ".claude-plugin" / "plugin.json"
        if candidate.exists():
            import json
            data = json.loads(candidate.read_text())
            return JSONResponse(data)
    return JSONResponse({"error": "plugin manifest not found"}, status_code=404)


async def http_download_plugin(request: Request):
    """Return the archon-memory plugin as a compressed tar archive.

    Excludes development artifacts (.venv, .pytest_cache, __pycache__, .git)
    so the tarball is small and won't overwrite the client's virtual environment.
    """
    import io
    import tarfile
    from starlette.responses import Response

    _EXCLUDE_DIRS = {".venv", ".pytest_cache", "__pycache__", ".git"}

    def _tar_filter(tarinfo: tarfile.TarInfo) -> tarfile.TarInfo | None:
        parts = Path(tarinfo.name).parts
        if any(part in _EXCLUDE_DIRS for part in parts):
            return None
        return tarinfo

    for parent in Path(__file__).resolve().parents:
        plugin_dir = parent / "integrations" / "claude-code" / "plugins" / "archon-memory"
        if plugin_dir.is_dir():
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w:gz") as tar:
                tar.add(plugin_dir, arcname="archon-memory", filter=_tar_filter)
            buf.seek(0)
            return Response(
                content=buf.read(),
                media_type="application/gzip",
                headers={"Content-Disposition": 'attachment; filename="archon-memory.tar.gz"'},
            )
    return JSONResponse({"error": "plugin not found"}, status_code=404)


async def http_download_extensions(request: Request):
    """Return default extensions as a compressed tar archive (skills/{name}/SKILL.md).

    Only extensions with is_default=True are included so that new project setups
    receive only the curated default set configured in Archon Settings.
    """
    import io
    import tarfile

    import httpx
    from starlette.responses import Response

    from src.server.config.service_discovery import get_api_url

    try:
        api_url = get_api_url()
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{api_url}/api/extensions",
                params={"include_content": True, "is_default": True},
            )
            if response.status_code != 200:
                return JSONResponse({"error": "failed to fetch extensions from API"}, status_code=502)
            extensions = response.json().get("extensions", [])
    except httpx.RequestError as e:
        logger.error(f"Failed to fetch extensions for tarball: {e}")
        return JSONResponse({"error": "API server unreachable"}, status_code=502)

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for ext in extensions:
            name = ext.get("name", "")
            content = ext.get("content", "")
            if not name or not content:
                continue
            data = content.encode("utf-8")
            info = tarfile.TarInfo(name=f"{name}/SKILL.md")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    buf.seek(0)
    return Response(
        content=buf.read(),
        media_type="application/gzip",
        headers={"Content-Disposition": 'attachment; filename="extensions.tar.gz"'},
    )


async def http_download_commands(request: Request):
    """Return all registered commands as a compressed tar archive.

    Fetches type='command' extensions from the registry and packages them
    using the command_group/filename structure from plugin_manifest metadata.
    Falls back to the static integrations/claude-code/commands/ directory
    if the registry query fails.
    """
    import io
    import tarfile

    import httpx
    from starlette.responses import Response

    from src.server.config.service_discovery import get_api_url

    try:
        api_url = get_api_url()
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{api_url}/api/extensions",
                params={"include_content": "true", "type": "command", "skill_group": "template"},
            )
            if response.status_code == 200:
                extensions = response.json().get("extensions", [])
                if extensions:
                    buf = io.BytesIO()
                    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
                        for ext in extensions:
                            content = ext.get("content", "")
                            manifest = ext.get("plugin_manifest") or {}
                            group = manifest.get("command_group")
                            filename = manifest.get("filename") or f"{ext.get('name', 'unknown')}.md"

                            if group:
                                arcname = f"{group}/{filename}"
                            else:
                                arcname = filename

                            data = content.encode("utf-8")
                            info = tarfile.TarInfo(name=arcname)
                            info.size = len(data)
                            tar.addfile(info, io.BytesIO(data))
                    buf.seek(0)
                    return Response(
                        content=buf.read(),
                        media_type="application/gzip",
                        headers={"Content-Disposition": 'attachment; filename="commands.tar.gz"'},
                    )
    except (httpx.RequestError, Exception) as e:
        logger.warning(f"Registry-backed commands tarball failed, falling back to static: {e}")

    # Fallback: serve static files from integrations/claude-code/commands/
    for parent in Path(__file__).resolve().parents:
        commands_dir = parent / "integrations" / "claude-code" / "commands"
        if commands_dir.is_dir():
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w:gz") as tar:
                for md_file in sorted(commands_dir.rglob("*.md")):
                    rel_path = md_file.relative_to(commands_dir)
                    tar.add(md_file, arcname=str(rel_path))
            buf.seek(0)
            return Response(
                content=buf.read(),
                media_type="application/gzip",
                headers={"Content-Disposition": 'attachment; filename="commands.tar.gz"'},
            )
    return JSONResponse({"error": "commands directory not found"}, status_code=404)


# Register setup endpoints
try:
    mcp.custom_route("/archon-setup.sh", methods=["GET"])(http_archon_setup_sh)
    mcp.custom_route("/archon-setup.bat", methods=["GET"])(http_archon_setup_bat)
    mcp.custom_route("/archon-setup.md", methods=["GET"])(http_archon_setup_md)
    mcp.custom_route("/scan-projects.md", methods=["GET"])(http_scan_projects_md)
    mcp.custom_route("/archon-setup/agent-work-orders-setup.sh", methods=["GET"])(http_agent_work_orders_setup_sh)
    logger.info("✓ Setup file endpoints registered")
    mcp.custom_route("/archon-setup/plugin-manifest", methods=["GET"])(http_plugin_manifest)
    mcp.custom_route("/archon-setup/plugin/archon-memory.tar.gz", methods=["GET"])(http_download_plugin)
    mcp.custom_route("/archon-setup/extensions.tar.gz", methods=["GET"])(http_download_extensions)
    mcp.custom_route("/archon-setup/commands.tar.gz", methods=["GET"])(http_download_commands)
    mcp.custom_route("/archon-setup/claude-md-snippet.md", methods=["GET"])(http_claude_md_snippet)
    logger.info("✓ Plugin and extension distribution endpoints registered")
except Exception as e:
    logger.error(f"✗ Failed to register setup endpoints: {e}")


def main():
    """Main entry point for the MCP server."""
    try:
        # Initialize Logfire first
        setup_logfire(service_name="archon-mcp-server")

        logger.info("🚀 Starting Archon MCP Server")
        logger.info("   Mode: Streamable HTTP")
        logger.info(f"   URL: http://{server_host}:{server_port}/mcp")

        mcp_logger.info("🔥 Logfire initialized for MCP server")
        mcp_logger.info(f"🌟 Starting MCP server - host={server_host}, port={server_port}")

        mcp.run(transport="streamable-http")

    except Exception as e:
        mcp_logger.error(f"💥 Fatal error in main - error={str(e)}, error_type={type(e).__name__}")
        logger.error(f"💥 Fatal error in main: {e}")
        logger.error(traceback.format_exc())
        raise


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("👋 MCP server stopped by user")
    except Exception as e:
        logger.error(f"💥 Unhandled exception: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)
