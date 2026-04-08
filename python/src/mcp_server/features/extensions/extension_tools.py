"""
Extensions management tools for Archon MCP Server.

Provides two consolidated tools:
- find_extensions: List, search, and get extension details
- manage_extensions: Sync, upload, validate, install, remove, and bootstrap extensions
"""

import json
import logging
import re
from urllib.parse import urljoin

import httpx
from mcp.server.fastmcp import Context, FastMCP

from src.mcp_server.utils.error_handling import MCPErrorFormatter
from src.mcp_server.utils.timeout_config import get_default_timeout
from src.server.config.service_discovery import get_api_url

logger = logging.getLogger(__name__)

# Optimization constants
MAX_DESCRIPTION_LENGTH = 500
DEFAULT_PAGE_SIZE = 20


def truncate_text(text: str, max_length: int = MAX_DESCRIPTION_LENGTH) -> str:
    """Truncate text to maximum length with ellipsis."""
    if text and len(text) > max_length:
        return text[:max_length - 3] + "..."
    return text


def optimize_extension_response(extension: dict, include_content: bool = False) -> dict:
    """Optimize extension object for MCP response by trimming large fields."""
    extension = extension.copy()

    if "description" in extension and extension["description"]:
        extension["description"] = truncate_text(extension["description"])

    if not include_content and "content" in extension:
        content = extension.pop("content", "")
        if content:
            extension["content_length"] = len(content)

    return extension


def _parse_yaml_frontmatter(content: str) -> dict:
    """
    Extract YAML frontmatter metadata from extension content.

    Looks for a block delimited by --- at the start of the content.
    Returns extracted fields: name, description, version, tags.
    """
    metadata: dict = {}
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not match:
        return metadata

    frontmatter = match.group(1)
    for line in frontmatter.split("\n"):
        line = line.strip()
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip().lower()
            value = value.strip().strip("\"'")
            if key == "name":
                metadata["name"] = value
            elif key == "description":
                metadata["description"] = value
            elif key == "version":
                metadata["version"] = value
            elif key == "tags":
                # Handle both inline list [a, b] and plain comma-separated
                value = value.strip("[]")
                metadata["tags"] = [t.strip().strip("\"'") for t in value.split(",") if t.strip()]

    return metadata


def register_extension_tools(mcp: FastMCP):
    """Register extensions management tools with the MCP server."""

    @mcp.tool()
    async def find_extensions(
        ctx: Context,
        extension_id: str | None = None,
        query: str | None = None,
        project_id: str | None = None,
        include_content: bool = False,
        extension_type: str | None = None,
    ) -> str:
        """
        List, search, and retrieve extensions.

        Args:
            extension_id: Get a specific extension by ID (returns full details including content)
            query: Search extensions by name or description keyword
            project_id: List extensions for a specific project (includes installation state)
            include_content: Include full extension content in list results (default: False)
            extension_type: Filter extensions by type: "skill", "command", or "plugin"

        Returns:
            JSON with extension(s) data

        Examples:
            find_extensions()  # List all extensions
            find_extensions(query="memory")  # Search by keyword
            find_extensions(extension_id="ext-123")  # Get specific extension
            find_extensions(project_id="proj-1")  # Extensions for a project
        """
        try:
            api_url = get_api_url()
            timeout = get_default_timeout()

            async with httpx.AsyncClient(timeout=timeout) as client:
                # Single extension by ID
                if extension_id:
                    response = await client.get(urljoin(api_url, f"/api/extensions/{extension_id}"))

                    if response.status_code == 200:
                        extension = response.json()
                        return json.dumps({"success": True, "extension": extension})
                    elif response.status_code == 404:
                        return MCPErrorFormatter.format_error(
                            error_type="not_found",
                            message=f"Extension {extension_id} not found",
                            suggestion="Verify the extension ID is correct",
                            http_status=404,
                        )
                    else:
                        return MCPErrorFormatter.from_http_error(response, "get extension")

                # Extensions for a specific project
                if project_id:
                    project_params: dict = {}
                    if extension_type:
                        project_params["type"] = extension_type
                    response = await client.get(
                        urljoin(api_url, f"/api/projects/{project_id}/extensions"), params=project_params
                    )

                    if response.status_code == 200:
                        data = response.json()
                        extensions = data.get("all_extensions", [])
                        optimized = [optimize_extension_response(e, include_content) for e in extensions]
                        return json.dumps({
                            "success": True,
                            "extensions": optimized,
                            "count": len(optimized),
                            "project_id": project_id,
                        })
                    else:
                        return MCPErrorFormatter.from_http_error(response, "list project extensions")

                # List all extensions
                params: dict = {}
                if extension_type:
                    params["type"] = extension_type
                response = await client.get(urljoin(api_url, "/api/extensions"), params=params)

                if response.status_code == 200:
                    data = response.json()
                    extensions = data.get("extensions", [])

                    # Client-side keyword filter
                    if query:
                        query_lower = query.lower()
                        extensions = [
                            e for e in extensions
                            if query_lower in e.get("name", "").lower()
                            or query_lower in e.get("description", "").lower()
                        ]

                    optimized = [optimize_extension_response(e, include_content) for e in extensions]

                    return json.dumps({
                        "success": True,
                        "extensions": optimized,
                        "count": len(optimized),
                        "query": query,
                    })
                else:
                    return MCPErrorFormatter.from_http_error(response, "list extensions")

        except httpx.RequestError as e:
            return MCPErrorFormatter.from_exception(e, "find extensions")
        except Exception as e:
            logger.error(f"Error finding extensions: {e}", exc_info=True)
            return MCPErrorFormatter.from_exception(e, "find extensions")

    @mcp.tool()
    async def manage_extensions(
        ctx: Context,
        action: str,
        # For sync
        local_extensions: list | None = None,
        system_fingerprint: str | None = None,
        system_name: str | None = None,
        hostname: str | None = None,
        os: str | None = None,
        project_id: str | None = None,
        # For upload / validate
        extension_content: str | None = None,
        extension_name: str | None = None,
        extension_type: str | None = None,
        # For install / remove
        extension_id: str | None = None,
        system_id: str | None = None,
    ) -> str:
        """
        Manage extensions: sync, upload, validate, install, remove, or bootstrap.

        Args:
            action: "sync" | "upload" | "validate" | "install" | "remove" | "bootstrap"
            local_extensions: Array of local extension objects for sync (each with name, content_hash, version)
            system_fingerprint: Unique fingerprint identifying this system (for sync/bootstrap)
            system_name: Human-readable name for this system (for sync/bootstrap)
            hostname: Machine hostname, e.g. output of `hostname` (for bootstrap)
            os: Operating system name, e.g. output of `uname -s` (for bootstrap)
            project_id: Project ID for sync/install/remove context
            extension_content: Full extension file content (for upload/validate)
            extension_name: Extension name override (for upload, otherwise parsed from content)
            extension_type: Extension type for upload: "skill" (default), "command", or "plugin"
            extension_id: Extension ID (for install/remove)
            system_id: System ID (for install/remove)

        Returns:
            JSON with action result

        Examples:
            manage_extensions("validate", extension_content="---\\nname: my-ext\\n---\\n# Content")
            manage_extensions("upload", extension_content="---\\nname: my-ext\\n---\\n# Content")
            manage_extensions("install", extension_id="ext-1", project_id="proj-1", system_id="sys-1")
            manage_extensions("remove", extension_id="ext-1", project_id="proj-1", system_id="sys-1")
            manage_extensions("sync", local_extensions=[...], system_fingerprint="fp-abc", project_id="proj-1")
            manage_extensions("bootstrap", system_fingerprint="fp-abc", system_name="my-machine", hostname="my-machine.local", os="Linux", project_id="proj-1")
        """
        try:
            api_url = get_api_url()
            timeout = get_default_timeout()

            async with httpx.AsyncClient(timeout=timeout) as client:
                if action == "validate":
                    return await _handle_validate(client, api_url, extension_content)

                elif action == "upload":
                    return await _handle_upload(
                        client, api_url, extension_content, extension_name, project_id, extension_type
                    )

                elif action == "sync":
                    return await _handle_sync(
                        client, api_url, local_extensions, system_fingerprint, system_name, project_id
                    )

                elif action == "install":
                    return await _handle_install(client, api_url, extension_id, project_id, system_id)

                elif action == "remove":
                    return await _handle_remove(client, api_url, extension_id, project_id, system_id)

                elif action == "bootstrap":
                    return await _handle_bootstrap(
                        client, api_url, system_fingerprint, system_name, hostname, os, project_id
                    )

                else:
                    return MCPErrorFormatter.format_error(
                        "invalid_action",
                        f"Unknown action: {action}. Valid actions: sync, upload, validate, install, remove, bootstrap",
                    )

        except httpx.RequestError as e:
            return MCPErrorFormatter.from_exception(e, f"{action} extension")
        except Exception as e:
            logger.error(f"Error managing extensions ({action}): {e}", exc_info=True)
            return MCPErrorFormatter.from_exception(e, f"{action} extension")


async def _handle_validate(client: httpx.AsyncClient, api_url: str, extension_content: str | None) -> str:
    """Validate extension content without persisting."""
    if not extension_content:
        return MCPErrorFormatter.format_error(
            "validation_error",
            "extension_content is required for validate action",
        )

    response = await client.post(
        urljoin(api_url, "/api/extensions/validate"),
        json={"content": extension_content},
    )

    if response.status_code == 200:
        return json.dumps({"success": True, **response.json()})
    else:
        return MCPErrorFormatter.from_http_error(response, "validate extension")


async def _handle_upload(
    client: httpx.AsyncClient,
    api_url: str,
    extension_content: str | None,
    extension_name: str | None,
    project_id: str | None = None,
    extension_type: str | None = None,
) -> str:
    """Upload or update an extension from content."""
    if not extension_content:
        return MCPErrorFormatter.format_error(
            "validation_error",
            "extension_content is required for upload action",
        )

    # Parse frontmatter for metadata
    metadata = _parse_yaml_frontmatter(extension_content)
    name = extension_name or metadata.get("name")
    if not name:
        return MCPErrorFormatter.format_error(
            "validation_error",
            "Extension name is required. Provide extension_name parameter or include 'name' in YAML frontmatter.",
        )

    description = metadata.get("description", "")

    create_payload = {
        "name": name,
        "description": description,
        "content": extension_content,
        "created_by": "mcp-upload",
    }
    if project_id:
        create_payload["skill_groups"] = [project_id]
    if extension_type:
        create_payload["type"] = extension_type

    # Try to create
    response = await client.post(urljoin(api_url, "/api/extensions"), json=create_payload)

    if response.status_code in (200, 201):
        result = response.json()
        return json.dumps({
            "success": True,
            "extension": result.get("extension", result),
            "message": "Extension uploaded successfully",
            "created": True,
        })

    elif response.status_code == 409:
        # Extension already exists — use the ID from the 409 response if available,
        # otherwise fall back to a list lookup.
        conflict_detail = response.json().get("detail", {})
        existing_id = conflict_detail.get("existing_id") if isinstance(conflict_detail, dict) else None

        if not existing_id:
            list_response = await client.get(urljoin(api_url, "/api/extensions"))
            if list_response.status_code != 200:
                return MCPErrorFormatter.from_http_error(list_response, "find existing extension for update")

            extensions = list_response.json().get("extensions", [])
            existing = next((e for e in extensions if e.get("name") == name), None)

            if not existing:
                return MCPErrorFormatter.format_error(
                    "conflict",
                    f"Extension '{name}' reported as existing (409) but could not be found by name",
                    suggestion="Try deleting the conflicting extension first, then re-upload",
                )

            existing_id = existing["id"]
        update_payload = {
            "content": extension_content,
            "updated_by": "mcp-upload",
        }
        if description:
            update_payload["description"] = description

        update_response = await client.put(
            urljoin(api_url, f"/api/extensions/{existing_id}"),
            json=update_payload,
        )

        if update_response.status_code == 200:
            result = update_response.json()
            return json.dumps({
                "success": True,
                "extension": result.get("extension", result),
                "message": f"Extension '{name}' updated (already existed)",
                "created": False,
            })
        else:
            return MCPErrorFormatter.from_http_error(update_response, "update existing extension")

    else:
        return MCPErrorFormatter.from_http_error(response, "upload extension")


async def _handle_sync(
    client: httpx.AsyncClient,
    api_url: str,
    local_extensions: list | None,
    system_fingerprint: str | None,
    system_name: str | None,
    project_id: str | None,
) -> str:
    """Sync local extensions with the remote registry via the project sync endpoint."""
    if local_extensions is None:
        return MCPErrorFormatter.format_error(
            "validation_error",
            "local_extensions array is required for sync action",
        )

    if not system_fingerprint:
        return MCPErrorFormatter.format_error(
            "validation_error",
            "system_fingerprint is required for sync action",
        )

    if not project_id:
        return MCPErrorFormatter.format_error(
            "validation_error",
            "project_id is required for sync action",
        )

    payload = {
        "fingerprint": system_fingerprint,
        "local_extensions": local_extensions,
    }
    if system_name:
        payload["system_name"] = system_name

    response = await client.post(
        urljoin(api_url, f"/api/projects/{project_id}/sync"),
        json=payload,
    )

    if response.status_code != 200:
        return MCPErrorFormatter.from_http_error(response, "sync system with project")

    data = response.json()
    system = data.get("system", {})

    return json.dumps({
        "success": True,
        "system": system,
        "pending_install": data.get("pending_install", []),
        "pending_remove": data.get("pending_remove", []),
        "local_changes": data.get("local_changes", []),
        "unknown_local": data.get("unknown_local", []),
        "in_sync": data.get("in_sync", []),
        "message": (
            f"Sync complete: {len(data.get('in_sync', []))} in sync, "
            f"{len(data.get('pending_install', []))} to install, "
            f"{len(data.get('local_changes', []))} with local changes, "
            f"{len(data.get('unknown_local', []))} unknown local"
        ),
    })


async def _handle_install(
    client: httpx.AsyncClient, api_url: str, extension_id: str | None, project_id: str | None, system_id: str | None
) -> str:
    """Install an extension for a project."""
    if not extension_id:
        return MCPErrorFormatter.format_error(
            "validation_error",
            "extension_id is required for install action",
        )
    if not project_id:
        return MCPErrorFormatter.format_error(
            "validation_error",
            "project_id is required for install action",
        )
    if not system_id:
        return MCPErrorFormatter.format_error(
            "validation_error",
            "system_id is required for install action",
        )

    payload = {"system_ids": [system_id]}

    response = await client.post(
        urljoin(api_url, f"/api/projects/{project_id}/extensions/{extension_id}/install"),
        json=payload,
    )

    if response.status_code in (200, 201):
        result = response.json()
        return json.dumps({
            "success": True,
            "message": result.get("message", f"Extension {extension_id} install queued for project {project_id}"),
        })
    else:
        return MCPErrorFormatter.from_http_error(response, "install extension")


async def _handle_remove(
    client: httpx.AsyncClient, api_url: str, extension_id: str | None, project_id: str | None, system_id: str | None
) -> str:
    """Remove an extension from a project."""
    if not extension_id:
        return MCPErrorFormatter.format_error(
            "validation_error",
            "extension_id is required for remove action",
        )
    if not project_id:
        return MCPErrorFormatter.format_error(
            "validation_error",
            "project_id is required for remove action",
        )
    if not system_id:
        return MCPErrorFormatter.format_error(
            "validation_error",
            "system_id is required for remove action",
        )

    payload = {"system_ids": [system_id]}

    response = await client.post(
        urljoin(api_url, f"/api/projects/{project_id}/extensions/{extension_id}/remove"),
        json=payload,
    )

    if response.status_code == 200:
        result = response.json()
        return json.dumps({
            "success": True,
            "message": result.get("message", f"Extension {extension_id} removal queued for project {project_id}"),
        })
    else:
        return MCPErrorFormatter.from_http_error(response, "remove extension")


async def _handle_bootstrap(
    client: httpx.AsyncClient,
    api_url: str,
    system_fingerprint: str | None,
    system_name: str | None,
    hostname: str | None,
    os: str | None,
    project_id: str | None,
) -> str:
    """Register the system and return extension metadata (content delivered via HTTP tarball)."""
    # Fetch extensions without content — content is downloaded separately via
    # /archon-setup/extensions.tar.gz to avoid bloating the LLM context window.
    response = await client.get(urljoin(api_url, "/api/extensions"), params={"include_content": False})

    if response.status_code != 200:
        return MCPErrorFormatter.from_http_error(response, "fetch extensions for bootstrap")

    data = response.json()
    raw_extensions = data.get("extensions", [])

    # Return metadata only — no content
    extensions = [
        {
            "name": e.get("name", ""),
            "display_name": e.get("display_name", ""),
        }
        for e in raw_extensions
    ]

    # Register system with project when both fingerprint and project_id are provided
    system = None
    if system_fingerprint and project_id:
        # The setup script downloads ALL registry extensions via tarball before
        # bootstrap runs, so report them as locally installed so the sync endpoint
        # can mark them as "installed" in archon_system_extensions.
        local_extensions = [
            {"name": e.get("name", ""), "content_hash": e.get("content_hash", "")}
            for e in raw_extensions
            if e.get("name") and e.get("content_hash")
        ]

        payload: dict = {
            "fingerprint": system_fingerprint,
            "local_extensions": local_extensions,
        }
        if system_name:
            payload["system_name"] = system_name
        if hostname:
            payload["hostname"] = hostname
        if os:
            payload["os"] = os

        sync_response = await client.post(
            urljoin(api_url, f"/api/projects/{project_id}/sync"),
            json=payload,
        )

        if sync_response.status_code == 200:
            system = sync_response.json().get("system")

    return json.dumps({
        "success": True,
        "extensions": extensions,
        "system": system,
        "message": f"Bootstrap complete: {len(extensions)} extension(s) ready to install",
    })
