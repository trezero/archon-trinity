---
name: archon-extension-sync
description: Sync local Claude Code skills, commands, and plugins with the Archon extension registry. Detects new extensions, local modifications, and pending installs across all three types. Use when "sync extensions", "check extensions", "update extensions", or at startup when sync is stale.
---

# Archon Extension Sync

Synchronizes local Claude Code **skills**, **commands**, and **plugins** with the Archon extension registry. Detects drift, handles conflict resolution, installs pending extensions, and uploads new local extensions across all extension types.

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

Initialize an empty `local_extensions` list: `[{name, content_hash, type, source_path, local_mtime}]`

### 1a. Determine install scope

Read `.claude/archon-config.json` if it exists (fall back to `~/.claude/archon-config.json`). Extract:
- `install_scope` -> `<install_scope>` (may be absent)

Determine `<install_dir>`:
- If `<install_scope>` is `"global"` -> `~/.claude`
- Otherwise (including `"project"` or absent) -> `.claude`

### 1b. Find all skill definition files

Scan these directories for SKILL.md files:
- `<install_dir>/skills/` (user-installed skills)
- `integrations/claude-code/extensions/` (repo skills, if in Archon repo)
- Any directory listed in `.claude/archon-state.json` under `extension_directories`

```
Glob: <install_dir>/skills/**/SKILL.md
Glob: integrations/claude-code/extensions/**/SKILL.md
```

### 1c. Parse each skill

For each SKILL.md file found:
1. Read the file content
2. Parse YAML frontmatter to extract `name`
3. Compute SHA256 hash of the full content:
   ```bash
   sha256sum <filepath> | cut -d' ' -f1
   ```
4. Get the file's last modification time as a Unix timestamp (integer seconds since epoch):
   ```bash
   date -r <filepath> +%s
   ```
   (Works on both Linux and macOS. On Windows use PowerShell: `[int](Get-Item '<filepath>').LastWriteTimeUtc.Subtract([datetime]'1970-01-01').TotalSeconds`)
5. Add to `local_extensions`: `{name, content_hash, type: "skill", source_path, local_mtime: <integer>}`

### 1d. Find all command files

Scan for command `.md` files:
- `<install_dir>/commands/` (user-installed commands)
- `.claude/commands/` (project-level commands, if different from install_dir)
- `integrations/claude-code/commands/` (repo commands, if in Archon repo)

```
Glob: <install_dir>/commands/**/*.md
Glob: .claude/commands/**/*.md
Glob: integrations/claude-code/commands/**/*.md
```

Deduplicate by absolute path (project and install_dir may overlap).

### 1e. Parse each command

For each command `.md` file found:
1. Read the file content
2. Derive the command name from its path:
   - Root-level file (e.g. `commands/commit.md`): name = `commit`
   - Grouped file (e.g. `commands/archon/archon-prime.md`): name = `archon-prime`
   - Grouped file where stem doesn't include group (e.g. `commands/archon/rca.md`): name = `archon-rca`
   - Nested deeper (e.g. `commands/core_piv_loop/plan-feature.md`): name = `core_piv_loop-plan-feature`
3. Compute SHA256 hash of the full content:
   ```bash
   sha256sum <filepath> | cut -d' ' -f1
   ```
4. Get the file's last modification time as a Unix timestamp (integer seconds since epoch):
   ```bash
   date -r <filepath> +%s
   ```
   (Works on both Linux and macOS. On Windows use PowerShell: `[int](Get-Item '<filepath>').LastWriteTimeUtc.Subtract([datetime]'1970-01-01').TotalSeconds`)
5. Add to `local_extensions`: `{name, content_hash, type: "command", source_path, local_mtime: <integer>}`

### 1f. Find all plugin directories

Scan for plugin manifest files:
- `<install_dir>/plugins/*/` (user-installed plugins — look for `.mcp.json` or `.claude-plugin/`)
- `integrations/claude-code/plugins/*/` (repo plugins, if in Archon repo)

```
Glob: <install_dir>/plugins/*/.mcp.json
Glob: integrations/claude-code/plugins/*/.mcp.json
```

Exclude Claude Code internal files (`blocklist.json`, `installed_plugins.json`, `cache/`, `data/`, `marketplaces/`, `known_marketplaces.json`, `install-counts-cache.json`).

### 1g. Parse each plugin

For each plugin directory found (containing `.mcp.json`):
1. Read the `.mcp.json` file content
2. Derive the plugin name from the directory name (e.g. `plugins/archon-memory/` -> `archon-memory`)
3. Compute a combined SHA256 hash of `.mcp.json` content:
   ```bash
   sha256sum <plugin_dir>/.mcp.json | cut -d' ' -f1
   ```
4. Get the manifest's last modification time as a Unix timestamp (integer seconds since epoch):
   ```bash
   date -r <plugin_dir>/.mcp.json +%s
   ```
   (Works on both Linux and macOS. On Windows use PowerShell: `[int](Get-Item '<plugin_dir>\.mcp.json').LastWriteTimeUtc.Subtract([datetime]'1970-01-01').TotalSeconds`)
5. Add to `local_extensions`: `{name, content_hash, type: "plugin", source_path, local_mtime: <integer>}`

**Note:** Plugins are complex multi-file structures (Python code, MCP servers, hooks). The sync tracks them by their `.mcp.json` manifest hash for drift detection. Full plugin content sync (uploading all plugin files) is not yet supported — only metadata registration and drift alerts.

### 1h. Summary before sync

Log the scan results:
> "Scanned local extensions: <N> skills, <M> commands, <P> plugins"

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
1. Check the `type` field to determine where to write:
   - **`type == "command"`**: Read `plugin_manifest` for `command_group` and `filename`. Write `content` to `<install_dir>/commands/{command_group}/{filename}` (create directory if needed). If no `command_group`, write to `<install_dir>/commands/{filename}`.
   - **`type == "skill"`** (or absent): Write `content` to `<install_dir>/skills/<name>/SKILL.md`
   - **`type == "plugin"`**: Log a notice — plugin installation requires manual setup. Report the plugin name and suggest the user install it from the repo.
2. Report: "Installed {type}: <name>"

### 3b. Remove pending extensions

For each item in `pending_remove`:
1. Check the `type` field:
   - **`type == "command"`**: Read `plugin_manifest` for path info. Delete `<install_dir>/commands/{command_group}/{filename}` (or `<install_dir>/commands/{filename}`).
   - **`type == "skill"`** (or absent): Delete `<install_dir>/skills/<name>/SKILL.md`
   - **`type == "plugin"`**: Log a notice — plugin removal requires manual cleanup. Report the plugin name.
2. Report: "Removed {type}: <name>"

### 3c. Resolve local changes

The `direction` field in each `local_changes` item indicates which copy is newer:
- `local_newer` — local file mtime is later than Archon's `updated_at`
- `archon_newer` — Archon's `updated_at` is later than local file mtime
- `conflict` — timestamps are within the clock-skew threshold (genuine ambiguity)
- `unknown` — one or both timestamps were not available

Format timestamps for display: convert `local_mtime` (Unix seconds) and `archon_updated_at` (ISO string) to human-readable UTC dates.

**For `direction == "local_newer"`:**

> "Extension **<name>** ({type}): your local copy is newer (local: `<local date>`, Archon last updated: `<archon date>`).
> **Recommended: Push local version to Archon.**
> Choose: [Push to Archon] / [Keep Archon version] / [Skip]"

- **Push to Archon:** Read local file content, then:
  ```
  manage_extensions(action="upload", extension_content="<local content>", extension_type="<type>")
  ```
- **Keep Archon version:** Fetch Archon version via `find_extensions(extension_id="<extension_id>")` and overwrite local file.
- **Skip:** Leave both as-is and continue.

**For `direction == "archon_newer"`:**

> "Extension **<name>** ({type}): Archon has a newer version (Archon last updated: `<archon date>`, local: `<local date>`).
> **Recommended: Pull from Archon (update local file).**
> Choose: [Pull from Archon] / [Keep local version] / [Skip]"

- **Pull from Archon:** Fetch Archon version via `find_extensions(extension_id="<extension_id>")` and overwrite local file.
- **Keep local version:** Read local file content, then push to Archon:
  ```
  manage_extensions(action="upload", extension_content="<local content>", extension_type="<type>")
  ```
- **Skip:** Leave both as-is and continue.

**For `direction == "conflict"` or `direction == "unknown"`:**

> "Extension **<name>** ({type}) has diverged (local hash: `<local_hash>`, Archon hash: `<archon_hash>`). Unable to determine which is newer. What would you like to do?"

Options:
- **Update Source** — Push local content to Archon as a new version
- **Save as Project Version** — Store as a project-specific override
- **Create New Extension** — Upload as a new extension with a different name
- **Discard Changes** — Overwrite local with Archon version

**If Update Source:**
Read the local file content, then:
```
manage_extensions(action="upload", extension_content="<local content>", extension_type="<type>")
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
manage_extensions(action="upload", extension_content="<local content>", extension_name="<new-name>", extension_type="<type>")
```

**If Discard Changes:**
Fetch the Archon version via `find_extensions(extension_id="<extension_id>")` and overwrite the local file.

### 3d. Handle unknown local extensions

For each item in `unknown_local`, ask the user:

> "Found local {type} **<name>** not in Archon. Would you like to upload it to the registry?"

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
manage_extensions(action="upload", extension_content="<content>", extension_type="<type>")
```
If validation has errors, show them and ask user to fix.

**Note for plugins:** Since plugins are multi-file, uploading only registers the plugin metadata (name and `.mcp.json` manifest). The full plugin source lives in the repo and must be distributed via git.

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

Report after Phase 5 completes (include duplicates removed count):

> "**Extension sync complete:**
> - Scanned: <N> skills, <M> commands, <P> plugins
> - In sync: <count>
> - Installed: <list or 'none'>
> - Removed: <list or 'none'>
> - Updated: <list or 'none'>
> - Uploaded: <list or 'none'>
> - Skipped: <list or 'none'>
> - Global duplicates removed: <count or 'none'>"

---

## Phase 5: Clean Up Global Duplicates

**Skip this entire phase** if `<install_scope>` is `"global"` — in that case `<install_dir>` and `~/.claude` are the same directory and there is nothing to deduplicate.

### 5a. Scan global extension directories

Scan `~/.claude` for all installed extensions using the same glob patterns as Phase 1:

```
Glob: ~/.claude/skills/**/SKILL.md
Glob: ~/.claude/commands/**/*.md
Glob: ~/.claude/plugins/*/.mcp.json
```

Apply the same name-derivation rules as Phase 1c, 1e, and 1g to build a `global_extensions` list: `[{name, type, path, content_hash}]`.

Compute the SHA256 hash of each file found:
```bash
sha256sum <filepath> | cut -d' ' -f1
```

### 5b. Find duplicates

Cross-reference `global_extensions` against the `local_extensions` list collected in Phase 1 (the project `.claude/` scan).

A **duplicate** is any entry where the same `name` + `type` appears in both lists. The project-scoped copy in `.claude/` always takes precedence.

If no duplicates are found, log:
> "No global duplicates found in ~/.claude."

and skip to Phase 4b summary.

### 5c. Remove global duplicates

For each duplicate, before deleting check whether the hashes differ:

**If hashes match** (identical content):
- Delete silently — no user prompt needed.
- Report: "Removed duplicate <type> **<name>** from `~/.claude/` (identical to project copy)"

**If hashes differ** (content diverged):
- Warn the user:
  > "Global `~/.claude/<type>/<name>` differs from the project copy in `.claude/`. The project version will be kept.
  > Delete the global copy?"
- If user confirms: delete.
- If user declines: skip this entry and leave both copies in place.

**Deletion commands by type:**
- Skill: `rm -rf ~/.claude/skills/<name>/`
- Command (grouped): `rm ~/.claude/commands/<group>/<filename>.md` — also remove the group directory if it becomes empty: `rmdir ~/.claude/commands/<group>/ 2>/dev/null || true`
- Command (root): `rm ~/.claude/commands/<filename>.md`
- Plugin: `rm -rf ~/.claude/plugins/<name>/`

### 5d. Phase 5 summary

> "Global duplicate cleanup: removed <N> extension(s) from `~/.claude/` — project `.claude/` is now the single source."

---

## Important Notes

### Sync Freshness

Other Archon extensions check sync freshness in their Phase 0:
```
Read .claude/archon-state.json
If last_extension_sync is missing or older than 24h:
  -> Run /archon-extension-sync before continuing
```

### Extension File Locations

**Skills:**
- Installed: `<install_dir>/skills/<name>/SKILL.md`
  - Project scope: `.claude/skills/`
  - Global scope: `~/.claude/skills/`
- Repo source: `integrations/claude-code/extensions/<name>/SKILL.md`
- Identified by: YAML frontmatter `name` field

**Commands:**
- Installed: `<install_dir>/commands/{group}/{filename}.md` or `<install_dir>/commands/{filename}.md`
- Project-level: `.claude/commands/{group}/{filename}.md`
- Repo source: `integrations/claude-code/commands/{group}/{filename}.md`
- Identified by: file path (group + filename stem)

**Plugins:**
- Installed: `<install_dir>/plugins/<name>/` (directory with `.mcp.json`)
- Repo source: `integrations/claude-code/plugins/<name>/`
- Identified by: directory name containing `.mcp.json`
- Sync scope: metadata tracking only (drift detection via `.mcp.json` hash)

### Error Recovery

- If Archon is unreachable, skip sync and continue with stale state
- If a single extension install/upload fails, continue with remaining operations
- Always save the sync timestamp even if some operations failed (prevents retry loops)
