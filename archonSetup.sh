#!/usr/bin/env bash
# Archon Setup Script — Connect this machine to Archon
# Server URL is baked in at download time.

set -e

ARCHON_API_URL="http://172.16.1.230:8181"
ARCHON_MCP_URL="http://172.16.1.230:8051"

# Fall back to defaults if placeholders were not substituted (script run directly from repo)
[ "$ARCHON_API_URL" = "http://172.16.1.230:8181" ] && ARCHON_API_URL="http://172.16.1.230:8181"
[ "$ARCHON_MCP_URL" = "http://172.16.1.230:8051" ] && ARCHON_MCP_URL="http://172.16.1.230:8051"

API_BASE="$ARCHON_API_URL"

# ── UI helpers ────────────────────────────────────────────────────────────────

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ] && [ "${TERM:-}" != "dumb" ]; then
  C_RESET=$'\033[0m'
  C_BOLD=$'\033[1m'
  C_DIM=$'\033[2m'
  C_BLUE=$'\033[34m'
  C_CYAN=$'\033[36m'
  C_GREEN=$'\033[32m'
  C_YELLOW=$'\033[33m'
  C_RED=$'\033[31m'
  C_MAGENTA=$'\033[35m'
else
  C_RESET=""
  C_BOLD=""
  C_DIM=""
  C_BLUE=""
  C_CYAN=""
  C_GREEN=""
  C_YELLOW=""
  C_RED=""
  C_MAGENTA=""
fi

print_header() {
  echo
  printf "%s%sArchon Setup%s\n" "$C_BOLD" "$C_CYAN" "$C_RESET"
  printf "  %sServer:%s %s\n" "$C_DIM" "$C_RESET" "$ARCHON_MCP_URL"
  printf "  %sAPI:%s    %s\n" "$C_DIM" "$C_RESET" "$ARCHON_API_URL"
  printf "  %s%s%s\n\n" "$C_DIM" "--------------------------------------------------" "$C_RESET"
}

ui_step() {
  printf "%s%s[%s/4] %s%s\n" "$C_BOLD" "$C_BLUE" "$1" "$2" "$C_RESET"
}

ui_info() {
  printf "  %s%s%s\n" "$C_DIM" "$1" "$C_RESET"
}

ui_success() {
  printf "  %s✓%s %s\n" "$C_GREEN" "$C_RESET" "$1"
}

ui_warn() {
  printf "  %s!%s %s\n" "$C_YELLOW" "$C_RESET" "$1"
}

ui_error() {
  printf "  %sx%s %s\n" "$C_RED" "$C_RESET" "$1" >&2
}

ask() {
  local prompt="$1"
  local default="$2"
  local answer

  if [ -n "$default" ]; then
    printf "  %s%s%s [%s]: " "$C_MAGENTA" "$prompt" "$C_RESET" "$default" >&2
  else
    printf "  %s%s%s: " "$C_MAGENTA" "$prompt" "$C_RESET" >&2
  fi

  read -r answer < /dev/tty || true
  printf "%s\n" "${answer:-$default}"
}

check_dependency() {
  if ! command -v "$1" &>/dev/null; then
    ui_error "'$1' is required but not installed."
    exit 1
  fi
}

url_encode() {
  "$PYTHON" -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$1"
}

# ── Dependency checks ────────────────────────────────────────────────────────

check_dependency curl
check_dependency claude

# ── Detect best Python ──────────────────────────────────────────────────────
# Priority: user's default `python` first (matches `which python`), then python3,
# then versioned candidates. We prefer 3.10+ but fall back to any Python 3.

PYTHON=""
PYTHON_FALLBACK=""
for candidate in python python3 python3.13 python3.12 python3.11 python3.10; do
  if command -v "$candidate" &>/dev/null; then
    PY_IS_3=$("$candidate" -c "import sys; print(sys.version_info[0] == 3)" 2>/dev/null || echo "False")
    if [ "$PY_IS_3" = "True" ]; then
      PY_GE_310=$("$candidate" -c "import sys; print(sys.version_info >= (3,10))" 2>/dev/null || echo "False")
      if [ "$PY_GE_310" = "True" ]; then
        PYTHON="$candidate"
        break
      elif [ -z "$PYTHON_FALLBACK" ]; then
        PYTHON_FALLBACK="$candidate"
      fi
    fi
  fi
done

# Fall back to any Python 3 if no 3.10+ found
if [ -z "$PYTHON" ]; then
  PYTHON="$PYTHON_FALLBACK"
fi

if [ -z "$PYTHON" ]; then
  ui_error "Python 3 is required but not installed."
  ui_info "Install Python 3.10 from: https://www.python.org/downloads/release/python-31011/"
  exit 1
fi

# ── Python version check (3.10+ recommended) ───────────────────────────────

PY_VERSION=$("$PYTHON" -c "import sys; v=sys.version_info; print(f'{v.major}.{v.minor}')" 2>/dev/null || echo "unknown")
PY_OK=$("$PYTHON" -c "import sys; print(sys.version_info >= (3,10))" 2>/dev/null || echo "False")

if [ "$PY_OK" != "True" ]; then
  echo
  ui_warn "Python $PY_VERSION detected ($(command -v "$PYTHON")) — Python 3.10+ is required."
  ui_info "The scanner and plugin system need Python 3.10+."
  echo
  if [ "$(uname)" = "Darwin" ]; then
    if command -v brew &>/dev/null; then
      ui_info "Install with Homebrew:  brew install python@3.10"
    else
      ui_info "Install from: https://www.python.org/downloads/release/python-31011/"
    fi
  elif [ -f /etc/debian_version ] || command -v apt &>/dev/null; then
    ui_info "Install with apt:  sudo apt install python3.10"
  elif command -v dnf &>/dev/null; then
    ui_info "Install with dnf:  sudo dnf install python3.10"
  else
    ui_info "Install from: https://www.python.org/downloads/release/python-31011/"
  fi
  echo
  CONTINUE=$(ask "Continue anyway? (y/N)" "N")
  if [ "${CONTINUE,,}" != "y" ]; then
    ui_info "Install Python 3.10+ and re-run this script."
    exit 0
  fi
  echo
fi

# ── Start ────────────────────────────────────────────────────────────────────

print_header

# ── Confirm server URLs ───────────────────────────────────────────────────────

printf "  %sArchon server URLs:%s\n" "$C_BOLD" "$C_RESET"
printf "  API: %s\n" "$ARCHON_API_URL"
printf "  MCP: %s\n" "$ARCHON_MCP_URL"
echo
NEW_API=$(ask "API URL (Enter to accept)" "$ARCHON_API_URL")
if [ "$NEW_API" != "$ARCHON_API_URL" ]; then
  ARCHON_API_URL="$NEW_API"
  # Derive a sensible MCP default by swapping :8181→:8051, then let user confirm
  ARCHON_MCP_URL=$(printf "%s" "$ARCHON_API_URL" | sed 's/:8181/:8051/')
fi
ARCHON_MCP_URL=$(ask "MCP URL (Enter to accept)" "$ARCHON_MCP_URL")
API_BASE="$ARCHON_API_URL"
echo

# ── Step 1/4: System name ────────────────────────────────────────────────────

ui_step 1 "System name"
SYSTEM_NAME=$(ask "System name" "$(hostname)")
echo

# ── Step 2/4: Project ────────────────────────────────────────────────────────

ui_step 2 "Project"

# Verify API is reachable before attempting any project operations
if ! curl -sf "$API_BASE/api/projects?include_content=false&q=" >/dev/null 2>&1; then
  ui_error "Cannot reach Archon API at $API_BASE"
  ui_info "Check that Archon is running and the URL is correct, then re-run this script."
  exit 1
fi

DIR_NAME=$(basename "$(pwd)")
PROJECT_ID=""
PROJECT_TITLE=""

ui_info "Searching for \"$DIR_NAME\"..."
SEARCH_RESULT=$(curl -sf "$API_BASE/api/projects?include_content=false&q=$(url_encode "$DIR_NAME")" 2>/dev/null || echo '{"projects":[]}')
MATCH_COUNT=$("$PYTHON" -c "import json,sys; print(len(json.loads(sys.argv[1]).get('projects',[])))" "$SEARCH_RESULT")

if [ "$MATCH_COUNT" -eq 1 ]; then
  # Exactly one match — use it automatically
  PROJECT_ID=$("$PYTHON" -c "import json,sys; print(json.loads(sys.argv[1])['projects'][0]['id'])" "$SEARCH_RESULT")
  PROJECT_TITLE=$("$PYTHON" -c "import json,sys; print(json.loads(sys.argv[1])['projects'][0]['title'])" "$SEARCH_RESULT")
  ui_success "Matched: $PROJECT_TITLE"

elif [ "$MATCH_COUNT" -eq 0 ]; then
  # No match — create a project automatically using the directory name
  ui_info "No match found. Creating project \"$DIR_NAME\"..."
  CREATE_PAYLOAD=$("$PYTHON" -c "import json,sys; print(json.dumps({'title': sys.argv[1]}))" "$DIR_NAME")
  TMPFILE=$(mktemp)
  HTTP_STATUS=$(curl -s -o "$TMPFILE" -w "%{http_code}" -X POST "$API_BASE/api/projects" \
    -H "Content-Type: application/json" \
    -d "$CREATE_PAYLOAD" 2>/dev/null || echo "000")
  CREATE_RESULT=$(cat "$TMPFILE" 2>/dev/null || echo "")
  rm -f "$TMPFILE"
  PROJECT_ID=$("$PYTHON" -c "
import json, sys
raw = sys.argv[1].strip()
if not raw:
    print('')
else:
    try:
        data = json.loads(raw)
    except Exception:
        data = {}
    print(data.get('project_id',''))
" "$CREATE_RESULT")
  PROJECT_TITLE="$DIR_NAME"
  if [ -z "$PROJECT_ID" ]; then
    ui_warn "Could not create project (HTTP $HTTP_STATUS). Continuing without project link."
  else
    ui_success "Created: $PROJECT_TITLE"
  fi

else
  # Multiple matches — show list and let user pick
  printf "  %sMultiple matches found — select one:%s\n" "$C_BOLD" "$C_RESET"
  "$PYTHON" - "$SEARCH_RESULT" <<'PYEOF'
import json, sys
projects = json.loads(sys.argv[1]).get("projects", [])[:10]
for i, p in enumerate(projects, 1):
    print(f"    [{i}] {p['title']}")
PYEOF
  echo
  while true; do
    SELECTION=$(ask "Project number" "1")
    if echo "$SELECTION" | grep -qE '^[0-9]+$'; then
      IDX=$((SELECTION - 1))
      # List endpoint returns 'id'; the create endpoint returns 'project_id' — these are intentionally different
      PROJECT_ID=$("$PYTHON" -c "import json,sys; ps=json.loads(sys.argv[1]).get('projects',[]); print(ps[$IDX]['id'] if $IDX < len(ps) else '')" "$SEARCH_RESULT")
      PROJECT_TITLE=$("$PYTHON" -c "import json,sys; ps=json.loads(sys.argv[1]).get('projects',[]); print(ps[$IDX]['title'] if $IDX < len(ps) else '')" "$SEARCH_RESULT")
      if [ -z "$PROJECT_ID" ]; then
        ui_warn "Invalid selection."
      else
        ui_success "Selected: $PROJECT_TITLE"
        break
      fi
    else
      ui_warn "Please enter a number."
    fi
  done
fi

echo

# ── Step 3/4: Claude setup ───────────────────────────────────────────────────

ui_step 3 "Claude Code setup"
MCP_URL="$ARCHON_MCP_URL/mcp"
ui_info "Configuring MCP endpoint: $MCP_URL"

# Remove any existing archon MCP from all scopes so the URL is always up to date
claude mcp remove archon -s local   >/dev/null 2>&1 || true
claude mcp remove archon -s user    >/dev/null 2>&1 || true
claude mcp remove archon -s project >/dev/null 2>&1 || true

if claude mcp add --transport http -s local archon "$MCP_URL" >/dev/null 2>&1; then
  ui_success "MCP server configured: $MCP_URL"
else
  ui_warn "Could not configure MCP automatically."
  ui_info "Run manually: claude mcp add --transport http archon $MCP_URL"
fi
echo

printf "  %sInstall scope:%s\n" "$C_BOLD" "$C_RESET"
echo "    [1] This project only (recommended)"
echo "        Uses .claude/ in this repository."
echo "    [2] Global (all projects)"
echo "        Uses ~/.claude/ in your home directory."
echo

while true; do
  install_scope=$(ask "Install scope (1 or 2)" "1")
  if [ "$install_scope" = "1" ]; then
    INSTALL_DIR=".claude"
    INSTALL_SCOPE_LABEL="project"
    break
  fi
  if [ "$install_scope" = "2" ]; then
    INSTALL_DIR="$HOME/.claude"
    INSTALL_SCOPE_LABEL="global"
    break
  fi
  ui_warn "Please enter 1 or 2."
done
echo

# ── Check for existing claude-mem plugin ────────────────────────────────────

SKIP_PLUGIN_INSTALL=false
if [ -d "$HOME/.claude/plugins/cache/thedotmack/claude-mem" ] || [ -d ".claude/plugins/claude-mem" ]; then
  ui_warn "Detected existing plugin: claude-mem"
  echo "  The archon-memory plugin replaces claude-mem with Archon integration."
  echo
  echo "    [1] Remove claude-mem and install archon-memory (recommended)"
  echo "    [2] Keep both (not recommended - duplicate hooks and tools)"
  echo "    [3] Skip plugin installation"
  echo

  while true; do
    claude_mem_choice=$(ask "Plugin action (1, 2, or 3)" "1")
    if [ "$claude_mem_choice" = "1" ]; then
      rm -rf "$HOME/.claude/plugins/cache/thedotmack/claude-mem"
      rm -rf ".claude/plugins/claude-mem"
      ui_success "Removed claude-mem"
      break
    fi
    if [ "$claude_mem_choice" = "2" ]; then
      break
    fi
    if [ "$claude_mem_choice" = "3" ]; then
      SKIP_PLUGIN_INSTALL=true
      break
    fi
    ui_warn "Please enter 1, 2, or 3."
  done
  echo
fi

# ── Install archon-memory plugin ─────────────────────────────────────────────

PLUGIN_DIR="$INSTALL_DIR/plugins/archon-memory"

if [ "$SKIP_PLUGIN_INSTALL" = "false" ]; then
  ui_info "Installing archon-memory plugin..."
  mkdir -p "$INSTALL_DIR/plugins"
  if curl -sf "${ARCHON_MCP_URL}/archon-setup/plugin/archon-memory.tar.gz" | \
    tar xz -C "$INSTALL_DIR/plugins/" 2>/dev/null; then
    ui_success "Plugin installed to $PLUGIN_DIR/"

    # Fix permissions — tarball may extract with restrictive modes
    chmod -R u+r "$PLUGIN_DIR/" 2>/dev/null

    # Remove any stale venv from a previous install (different Python version, broken symlinks, etc.)
    if [ -d "$PLUGIN_DIR/.venv" ]; then
      rm -rf "$PLUGIN_DIR/.venv"
    fi

    # Create isolated venv and install dependencies
    VENV_DIR="$PLUGIN_DIR/.venv"
    REQUIREMENTS="$PLUGIN_DIR/requirements.txt"
    if [ -f "$REQUIREMENTS" ]; then
      ui_info "Creating plugin virtual environment..."
      # Use the best available Python (>=3.10 required for tree-sitter 0.24+)
      BEST_PYTHON=""
      for candidate in python3.13 python3.12 python3.11 python3.10 python3 python; do
        if command -v "$candidate" &>/dev/null; then
          PY_VER=$("$candidate" -c "import sys; print(sys.version_info[:2] >= (3,10))" 2>/dev/null)
          if [ "$PY_VER" = "True" ]; then
            BEST_PYTHON="$candidate"
            break
          fi
        fi
      done

      if [ -z "$BEST_PYTHON" ]; then
        ui_warn "Python 3.10+ required for plugin. Found only:"
        "$PYTHON" --version 2>&1 | sed 's/^/    /'
        ui_info "Install Python 3.10+ and re-run this script."
      elif "$BEST_PYTHON" -m venv "$VENV_DIR" 2>/dev/null; then
        ui_success "Created venv ($($BEST_PYTHON --version 2>&1))"
        # Upgrade pip before installing packages
        "$VENV_DIR/bin/pip" install -q --upgrade pip 2>/dev/null
        ui_info "Installing plugin dependencies..."
        if "$VENV_DIR/bin/pip" install -q -r "$REQUIREMENTS" 2>/dev/null; then
          ui_success "Plugin dependencies installed in venv"
        else
          ui_warn "pip install failed. Run manually:"
          ui_info "$VENV_DIR/bin/pip install -r $REQUIREMENTS"
        fi

        # Verify the venv works
        if ! "$VENV_DIR/bin/python" -c "import httpx" 2>/dev/null; then
          ui_warn "Verification failed — httpx not importable. Run manually:"
          ui_info "$VENV_DIR/bin/pip install -r $REQUIREMENTS"
        fi
      else
        ui_warn "Could not create venv. Falling back to system pip..."
        if "$PYTHON" -m pip install -q -r "$REQUIREMENTS" 2>/dev/null; then
          ui_success "Plugin dependencies installed (system-wide)"
        else
          ui_warn "Could not install plugin dependencies. Run manually:"
          ui_info "pip3 install -r $REQUIREMENTS"
        fi
      fi
    fi
  else
    ui_warn "Plugin download failed. Install manually from Archon."
  fi
  echo
fi

# Determine the Python executable for plugin scripts
# Prefer venv python if available, fall back to detected system python
if [ -x "$PLUGIN_DIR/.venv/bin/python" ]; then
  PLUGIN_PYTHON="$PLUGIN_DIR/.venv/bin/python"
else
  PLUGIN_PYTHON="$PYTHON"
fi

# ── Register hooks in Claude Code settings ──────────────────────────────────
#
# Claude Code limitation: SessionStart and Stop hooks only work in the global
# ~/.claude/settings.json. PostToolUse works in project settings.local.json.
# So we split: lifecycle hooks → global, observation hook → project or global.

if [ "$SKIP_PLUGIN_INSTALL" = "false" ]; then
  GLOBAL_SETTINGS="$HOME/.claude/settings.json"

  if [ "$INSTALL_SCOPE_LABEL" = "project" ]; then
    # Project scope: lifecycle hooks in global settings use $CLAUDE_PROJECT_DIR
    # for dynamic resolution. PostToolUse in project settings uses relative path.
    PROJECT_SETTINGS="$INSTALL_DIR/settings.local.json"
    LIFECYCLE_PYTHON='$CLAUDE_PROJECT_DIR/.claude/plugins/archon-memory/.venv/bin/python'
    LIFECYCLE_SCRIPTS='$CLAUDE_PROJECT_DIR/.claude/plugins/archon-memory/scripts'
    PTU_PYTHON=".claude/plugins/archon-memory/.venv/bin/python"
    PTU_SCRIPTS=".claude/plugins/archon-memory/scripts"
  else
    # Global scope: everything uses absolute paths
    PROJECT_SETTINGS=""
    LIFECYCLE_PYTHON="$PLUGIN_DIR/.venv/bin/python"
    LIFECYCLE_SCRIPTS="$PLUGIN_DIR/scripts"
    PTU_PYTHON="$PLUGIN_DIR/.venv/bin/python"
    PTU_SCRIPTS="$PLUGIN_DIR/scripts"
  fi

  # Fall back to detected system python if venv doesn't exist
  if [ ! -x "$PLUGIN_DIR/.venv/bin/python" ] && [ "$INSTALL_SCOPE_LABEL" != "project" ]; then
    LIFECYCLE_PYTHON="$PYTHON"
    PTU_PYTHON="$PYTHON"
  fi

  # Helper: merge archon hooks into a settings file
  merge_hooks() {
    local target_file="$1"
    shift
    # Remaining args are event:command pairs
    "$PYTHON" - "$target_file" "$@" <<'PYEOF'
import json, sys
from pathlib import Path

settings_path = Path(sys.argv[1])
pairs = sys.argv[2:]  # event:command:timeout triples

if settings_path.is_file():
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        settings = {}
else:
    settings = {}

hooks = settings.setdefault("hooks", {})

i = 0
while i < len(pairs):
    event = pairs[i]
    command = pairs[i + 1]
    timeout = int(pairs[i + 2])
    i += 3

    existing = hooks.get(event, [])
    cleaned = [h for h in existing if not any("archon-memory" in hk.get("command", "") for hk in h.get("hooks", []))]
    cleaned.append({
        "matcher": "",
        "hooks": [{"type": "command", "command": command, "timeout": timeout}],
    })
    hooks[event] = cleaned

settings_path.parent.mkdir(parents=True, exist_ok=True)
settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
PYEOF
  }

  # Register SessionStart + Stop in global settings (required by Claude Code)
  ui_info "Registering lifecycle hooks in ~/.claude/settings.json..."
  merge_hooks "$GLOBAL_SETTINGS" \
    "SessionStart" "test -f \"${LIFECYCLE_SCRIPTS}/session_start_hook.py\" && \"${LIFECYCLE_PYTHON}\" \"${LIFECYCLE_SCRIPTS}/session_start_hook.py\" || true" "10" \
    "Stop" "test -f \"${LIFECYCLE_SCRIPTS}/session_end_hook.py\" && \"${LIFECYCLE_PYTHON}\" \"${LIFECYCLE_SCRIPTS}/session_end_hook.py\" || true" "30"
  if [ $? -eq 0 ]; then
    ui_success "SessionStart + Stop hooks → ~/.claude/settings.json"
  else
    ui_warn "Could not register lifecycle hooks."
  fi

  # Register PostToolUse in project or global settings
  if [ -n "$PROJECT_SETTINGS" ]; then
    ui_info "Registering PostToolUse hook in settings.local.json..."
    merge_hooks "$PROJECT_SETTINGS" \
      "PostToolUse" "test -f \"${PTU_SCRIPTS}/observation_hook.py\" && \"${PTU_PYTHON}\" \"${PTU_SCRIPTS}/observation_hook.py\" || true" "5"
    if [ $? -eq 0 ]; then
      ui_success "PostToolUse hook → settings.local.json"
    else
      ui_warn "Could not register PostToolUse hook."
    fi
  else
    ui_info "Registering PostToolUse hook in ~/.claude/settings.json..."
    merge_hooks "$GLOBAL_SETTINGS" \
      "PostToolUse" "test -f \"${PTU_SCRIPTS}/observation_hook.py\" && \"${PTU_PYTHON}\" \"${PTU_SCRIPTS}/observation_hook.py\" || true" "5"
    if [ $? -eq 0 ]; then
      ui_success "PostToolUse hook → ~/.claude/settings.json"
    else
      ui_warn "Could not register PostToolUse hook."
    fi
  fi
  echo
fi

# ── Download and install extensions ──────────────────────────────────────────

ui_info "Installing extensions..."
mkdir -p "$INSTALL_DIR/skills"
if curl -sf "${ARCHON_MCP_URL}/archon-setup/extensions.tar.gz" | \
    tar xz -C "$INSTALL_DIR/skills/" 2>/dev/null; then
  EXT_COUNT=$(find "$INSTALL_DIR/skills" -maxdepth 2 -name "SKILL.md" 2>/dev/null | wc -l | tr -d ' ')
  ui_success "Installed $EXT_COUNT extension(s) to $INSTALL_DIR/skills/"
else
  ui_warn "Extension download failed. /archon-setup will handle installation."
fi
echo

# ── Write archon-config.json ─────────────────────────────────────────────────

mkdir -p "$INSTALL_DIR"
machine_fingerprint=$("$PYTHON" -c "import hashlib,socket,os; print(hashlib.md5((socket.gethostname()+str(os.getuid())).encode()).hexdigest()[:16])")

cat > "$INSTALL_DIR/archon-config.json" << CONFIGEOF
{
  "archon_api_url": "$ARCHON_API_URL",
  "archon_mcp_url": "$ARCHON_MCP_URL",
  "project_id": "$PROJECT_ID",
  "project_title": "$PROJECT_TITLE",
  "machine_id": "$machine_fingerprint",
  "install_scope": "$INSTALL_SCOPE_LABEL",
  "installed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
CONFIGEOF
ui_success "Wrote $INSTALL_DIR/archon-config.json"
echo

# ── Update .gitignore ────────────────────────────────────────────────────────

for entry in ".claude/plugins/" ".claude/skills/" ".claude/archon-config.json" ".claude/archon-state.json" ".claude/archon-memory-buffer.jsonl" ".claude/settings.local.json" ".archon/"; do
  grep -qxF "$entry" .gitignore 2>/dev/null || echo "$entry" >> .gitignore
done
ui_success "Updated .gitignore with Archon local paths."
echo

# ── Step 4/4: Install /archon-setup command ─────────────────────────────────

ui_step 4 "Install slash commands"
mkdir -p "$HOME/.claude/commands"
if curl -sf "${ARCHON_MCP_URL}/archon-setup/commands.tar.gz" | tar xz -C "$HOME/.claude/commands/"; then
  ui_success "Slash commands installed from registry"
else
  ui_warn "Could not download commands from registry, trying individual files..."
  curl -sf "$ARCHON_MCP_URL/archon-setup.md" -o "$HOME/.claude/commands/archon-setup.md" 2>/dev/null || true
  curl -sf "$ARCHON_MCP_URL/scan-projects.md" -o "$HOME/.claude/commands/scan-projects.md" 2>/dev/null || true
fi
echo

# ── Write initial state ──────────────────────────────────────────────────────

mkdir -p ".claude"
STATE_FILE=".claude/archon-state.json"

# Merge with existing state if present
if [ -f "$STATE_FILE" ]; then
  EXISTING=$(cat "$STATE_FILE")
else
  EXISTING="{}"
fi

"$PYTHON" - "$EXISTING" "$SYSTEM_NAME" "$PROJECT_ID" <<'PYEOF'
import json, sys
state = json.loads(sys.argv[1])
state["system_name"] = sys.argv[2]
if sys.argv[3]:
    state["archon_project_id"] = sys.argv[3]
with open(".claude/archon-state.json", "w") as f:
    json.dump(state, f, indent=2)
PYEOF

# ── Done ─────────────────────────────────────────────────────────────────────

printf "%s%sSetup complete!%s\n\n" "$C_BOLD" "$C_GREEN" "$C_RESET"
echo "  Open Claude Code in this directory and run:"
printf "    %s/archon-setup%s\n\n" "$C_BOLD" "$C_RESET"
echo "  This will sync extensions and project context."
echo
