---
name: archon-extension-sync
description: Sync local Claude Code extensions with the Archon extension registry. Detects new extensions, local modifications, and pending installs. Use when "sync extensions", "check extensions", "update extensions", or at startup when sync is stale.
---

# Archon Extension Sync

Synchronizes local Claude Code extensions with the Archon extension registry. Detects drift, handles conflict resolution, installs pending extensions, and uploads new local extensions.

**Invocation:** `/archon-extension-sync`
**Auto-trigger:** Runs automatically when any Archon extension detects last_extension_sync > 24h in `.claude/archon-state.json`

---

## Phase 0: Compute Machine Fingerprint

### 0a. Gather system info

```bash
hostname
```

```bash
whoami
```

```bash
uname -s
```

### 0b. Compute fingerprint

Concatenate: `<hostname>|<username>|<os>` and compute SHA256:

```bash
echo -n "$(hostname)|$(whoami)|$(uname -s)" | sha256sum | cut -d' ' -f1
```

Store as `system_fingerprint`.

---

## Phase 1: Scan Local Extensions

### 1a. Determine install scope

Read `.claude/archon-config.json` if it exists (fall back to `~/.claude/archon-config.json`). Extract:
- `install_scope` → `<install_scope>` (may be absent)

Determine `<install_dir>`:
- If `<install_scope>` is `"project"` → `.claude`
- If `<install_scope>` is `"global"` or absent → `~/.claude`

### 1b. Find all extension definition files

Scan these directories for SKILL.md extension definition files:
- `<install_dir>/skills/` (user-installed extensions)
- `integrations/claude-code/extensions/` (repo extensions, if in Archon repo)
- Any directory listed in `.claude/archon-state.json` under `extension_directories`

```
Glob: <install_dir>/skills/**/SKILL.md
Glob: integrations/claude-code/extensions/**/SKILL.md
```

### 1c. Parse each extension

For each extension definition file found:
1. Read the file content
2. Parse YAML frontmatter to extract `name`
3. Compute SHA256 hash of the full content:
   ```bash
   sha256sum <filepath> | cut -d' ' -f1
   ```

Build `local_extensions` list: `[{name, content_hash}]`

---

## Phase 2: Sync with Archon

### 2a. Read project state

Read `.claude/archon-state.json` for `archon_project_id`.

If no project ID:
> "No Archon project linked. Run `/link-to-project` first to associate this repo with an Archon project."

Stop here.

### 2b. Call sync

```
manage_extensions(
    action="sync",
    local_extensions=<local_extensions list>,
    system_fingerprint="<fingerprint>",
    project_id="<archon_project_id>"
)
```

### 2c. Handle first-time registration

If response has `system.is_new == true`:

Ask the user:
> "This is the first time this machine is connecting to Archon. What name should we use for this system?"
>
> Suggestion: `<hostname>`

Store the user's choice, then re-call:
```
manage_extensions(
    action="sync",
    local_extensions=<local_extensions list>,
    system_fingerprint="<fingerprint>",
    system_name="<user-provided-name>",
    project_id="<archon_project_id>"
)
```

---

## Phase 3: Process Sync Results

### 3a. Install pending extensions

For each item in `pending_install`:
1. Write the `content` to `<install_dir>/skills/<name>/SKILL.md` (extension definition file)
2. Report: "Installed extension: <name>"

### 3b. Remove pending extensions

For each item in `pending_remove`:
1. Delete `<install_dir>/skills/<name>/SKILL.md` (extension definition file)
2. Report: "Removed extension: <name>"

### 3c. Resolve local changes

For each item in `local_changes`, ask the user:

> "Extension **<name>** has local modifications (local hash: `<local_hash>`, Archon hash: `<archon_hash>`). What would you like to do?"

Options:
- **Update Source** — Push local content to Archon as a new version
- **Save as Project Version** — Store as a project-specific override
- **Create New Extension** — Upload as a new extension with a different name
- **Discard Changes** — Overwrite local with Archon version

**If Update Source:**
Read the local file content, then:
```
manage_extensions(action="upload", extension_content="<local content>")
```

**If Save as Project Version:**
Read the local file content. The backend stores it as a project override (future API call).

**If Create New Extension:**
Ask for a new name, then:
```
manage_extensions(action="validate", extension_content="<local content>")
```
If validation passes:
```
manage_extensions(action="upload", extension_content="<local content>", extension_name="<new-name>", project_id="<archon_project_id>")
```

**If Discard Changes:**
Fetch the Archon version via `find_extensions(extension_id="<extension_id>")` and overwrite the local file.

### 3d. Handle unknown local extensions

For each item in `unknown_local`, ask the user:

> "Found local extension **<name>** not in Archon. Would you like to upload it to the registry?"

Options:
- **Upload** — Validate and upload
- **Skip** — Leave as local-only

**If Upload:**
Read the local file, then:
```
manage_extensions(action="validate", extension_content="<content>")
```
If validation passes (or user accepts warnings):
```
manage_extensions(action="upload", extension_content="<content>", project_id="<archon_project_id>")
```
This scopes the extension to the current project so it is not distributed to other projects.
If validation has errors, show them and ask user to fix.

### 3e. Update slash commands

Download the latest command files from the Archon server so slash commands like
`/scan-projects` and `/archon-setup` stay up to date without re-running the setup script.

Read `archon_mcp_url` from `.claude/archon-config.json` (or `~/.claude/archon-config.json`).

```bash
mkdir -p ~/.claude/commands && curl -sf "<archon_mcp_url>/archon-setup/commands.tar.gz" | tar xz -C ~/.claude/commands/
```

If the download fails, warn the user but continue:
> "Could not update slash commands from Archon server. Existing commands will continue to work."

---

## Phase 4: Update State

### 4a. Write sync timestamp

Update `.claude/archon-state.json`:
```json
{
  "last_extension_sync": "<ISO timestamp>",
  "system_fingerprint": "<fingerprint>",
  "system_name": "<name>"
}
```

Merge with existing state — do not overwrite other fields.

### 4b. Summary

> "**Extension sync complete:**
> - In sync: <N> extensions
> - Installed: <list or 'none'>
> - Removed: <list or 'none'>
> - Updated: <list or 'none'>
> - Uploaded: <list or 'none'>
> - Skipped: <list or 'none'>
> - Slash commands: updated"

---

## Important Notes

### Sync Freshness

Other Archon extensions check sync freshness in their Phase 0:
```
Read .claude/archon-state.json
If last_extension_sync is missing or older than 24h:
  → Run /archon-extension-sync before continuing
```

### Extension File Locations

- **Installed extensions:** `<install_dir>/skills/<name>/SKILL.md` (extension definition file)
  - Project scope (`install_scope: "project"`): `.claude/skills/`
  - Global scope (`install_scope: "global"`): `~/.claude/skills/`
- **Repo extensions:** `integrations/claude-code/extensions/<name>/SKILL.md`
- Extensions are identified by their frontmatter `name` field, not directory name

### Error Recovery

- If Archon is unreachable, skip sync and continue with stale state
- If a single extension install/upload fails, continue with remaining operations
- Always save the sync timestamp even if some operations failed (prevents retry loops)
