"""Extension CRUD and version management service.

Handles creating, reading, updating, and deleting extensions in the
archon_extensions table, maintaining version history in archon_extension_versions,
and managing per-project overrides in archon_project_extensions.
"""

import hashlib
from datetime import UTC, datetime
from typing import Any

from src.server.config.logfire_config import get_logger
from src.server.utils import get_supabase_client

logger = get_logger(__name__)

EXTENSIONS_TABLE = "archon_extensions"
VERSIONS_TABLE = "archon_extension_versions"
PROJECT_EXTENSIONS_TABLE = "archon_project_extensions"


class ExtensionService:
    """Service for extension CRUD operations and version management."""

    def __init__(self, supabase_client=None):
        """Initialize with optional Supabase client (defaults to shared instance)."""
        self.supabase_client = supabase_client or get_supabase_client()

    @staticmethod
    def compute_content_hash(content: str) -> str:
        """Compute SHA-256 hex digest of extension content."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def create_extension(
        self,
        name: str,
        description: str,
        content: str,
        created_by: str,
        skill_groups: list[str] | None = None,
        type: str | None = None,
        plugin_manifest: dict | None = None,
    ) -> dict[str, Any]:
        """Create a new extension and save version 1.

        Args:
            name: Kebab-case extension name (must be unique).
            description: Human-readable description.
            content: Full SKILL.md content.
            created_by: Identifier of the user or agent creating the extension.
            skill_groups: Optional list of skill group tags for project-scoped delivery.
            type: Optional extension type ('skill' or 'command'). When omitted the DB
                default ('skill') applies.
            plugin_manifest: Optional JSONB metadata for command extensions (e.g.
                command_group, filename).

        Returns:
            The created extension row as a dict.

        Raises:
            RuntimeError: If the database insert returns no data.
        """
        content_hash = self.compute_content_hash(content)
        now = datetime.now(UTC).isoformat()

        extension_data: dict[str, Any] = {
            "name": name,
            "display_name": name,
            "description": description,
            "content": content,
            "content_hash": content_hash,
            "current_version": 1,
            "created_by": created_by,
            "created_at": now,
            "updated_at": now,
        }

        if skill_groups is not None:
            extension_data["skill_groups"] = skill_groups
        if type is not None:
            extension_data["type"] = type
        if plugin_manifest is not None:
            extension_data["plugin_manifest"] = plugin_manifest

        response = self.supabase_client.table(EXTENSIONS_TABLE).insert(extension_data).execute()

        if not response.data:
            raise RuntimeError(f"Failed to create extension '{name}': database returned no data")

        extension = response.data[0]
        logger.info(f"Extension created: {extension.get('id')} ({name})")

        # Save initial version
        self._save_version(
            extension_id=extension["id"],
            version_number=1,
            content=content,
            content_hash=content_hash,
            created_by=created_by,
        )

        return extension

    def list_extensions(self, skill_group: str | None = None, type: str | None = None) -> list[dict[str, Any]]:
        """List all extensions without the full content field.

        Args:
            skill_group: Optional skill group tag to filter by.
            type: Optional extension type to filter by ('skill' or 'command').

        Returns:
            List of extension metadata dicts (id, name, description, version, type, timestamps).
        """
        query = (
            self.supabase_client.table(EXTENSIONS_TABLE)
            .select("id, name, display_name, description, current_version, content_hash, type, skill_groups, is_required, is_default, is_validated, tags, created_by, created_at, updated_at")
        )
        if skill_group is not None:
            query = query.contains("skill_groups", [skill_group])
        if type is not None:
            query = query.eq("type", type)
        response = query.order("name").execute()
        return response.data

    def list_extensions_for_project(
        self,
        project_id: str,
        include_content: bool = False,
        type: str | None = None,
    ) -> list[dict[str, Any]]:
        """List extensions that are scoped to a project via skill_groups overlap.

        Args:
            project_id: The project UUID to match against skill_groups.
            include_content: When True, selects all columns including content.
                When False, excludes the content column.
            type: Optional extension type to filter by ('skill' or 'command').

        Returns:
            List of extension dicts for the project.
        """
        if include_content:
            query = self.supabase_client.table(EXTENSIONS_TABLE).select("*")
        else:
            query = (
                self.supabase_client.table(EXTENSIONS_TABLE)
                .select("id, name, display_name, description, current_version, content_hash, type, skill_groups, is_required, is_default, is_validated, tags, created_by, created_at, updated_at")
            )
        query = query.overlaps("skill_groups", [project_id])
        if type is not None:
            query = query.eq("type", type)
        response = query.order("name").execute()
        return response.data

    def list_extensions_full(self, skill_group: str | None = None, type: str | None = None) -> list[dict[str, Any]]:
        """List all extensions including full content (used by sync endpoint).

        Args:
            skill_group: Optional skill group tag to filter by.
            type: Optional extension type to filter by ('skill' or 'command').

        Returns:
            List of full extension dicts including the content field.
        """
        query = self.supabase_client.table(EXTENSIONS_TABLE).select("*")
        if skill_group is not None:
            query = query.contains("skill_groups", [skill_group])
        if type is not None:
            query = query.eq("type", type)
        response = query.order("name").execute()
        return response.data

    def get_extension(self, extension_id: str) -> dict[str, Any] | None:
        """Get a single extension by ID including full content.

        Returns:
            Extension dict or None if not found.
        """
        response = (
            self.supabase_client.table(EXTENSIONS_TABLE)
            .select("*")
            .eq("id", extension_id)
            .execute()
        )
        if response.data:
            return response.data[0]
        return None

    def find_by_name(self, name: str) -> dict[str, Any] | None:
        """Find an extension by its unique kebab-case name.

        Returns:
            Extension dict or None if not found.
        """
        response = (
            self.supabase_client.table(EXTENSIONS_TABLE)
            .select("*")
            .eq("name", name)
            .limit(1)
            .execute()
        )
        if response.data:
            return response.data[0]
        return None

    def update_extension(
        self,
        extension_id: str,
        content: str,
        new_version: int,
        updated_by: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Update an extension's content and bump its version.

        Args:
            extension_id: The extension UUID.
            content: New SKILL.md content.
            new_version: The new version number (caller must compute this).
            updated_by: Identifier of the user or agent performing the update.
            description: Optional updated description.

        Returns:
            The updated extension row as a dict.

        Raises:
            RuntimeError: If the database update returns no data (e.g., extension not found).
        """
        content_hash = self.compute_content_hash(content)
        now = datetime.now(UTC).isoformat()

        update_data: dict[str, Any] = {
            "content": content,
            "content_hash": content_hash,
            "current_version": new_version,
            "updated_at": now,
        }
        if description is not None:
            update_data["description"] = description

        response = (
            self.supabase_client.table(EXTENSIONS_TABLE)
            .update(update_data)
            .eq("id", extension_id)
            .execute()
        )

        if not response.data:
            raise RuntimeError(f"Failed to update extension '{extension_id}': database returned no data")

        extension = response.data[0]
        logger.info(f"Extension updated: {extension_id} -> v{new_version}")

        # Save version history entry
        self._save_version(
            extension_id=extension_id,
            version_number=new_version,
            content=content,
            content_hash=content_hash,
            created_by=updated_by,
        )

        return extension

    def delete_extension(self, extension_id: str) -> None:
        """Delete an extension by ID.

        Version history rows are expected to be cascade-deleted by the database.
        """
        self.supabase_client.table(EXTENSIONS_TABLE).delete().eq("id", extension_id).execute()
        logger.info(f"Extension deleted: {extension_id}")

    def get_versions(self, extension_id: str) -> list[dict[str, Any]]:
        """Get the version history for an extension, newest first.

        Args:
            extension_id: The extension UUID.

        Returns:
            List of version rows ordered by version_number descending.
        """
        response = (
            self.supabase_client.table(VERSIONS_TABLE)
            .select("*")
            .eq("extension_id", extension_id)
            .order("version_number", desc=True)
            .execute()
        )
        return response.data

    def get_project_extensions(self, project_id: str) -> list[dict[str, Any]]:
        """Get all extension overrides for a project.

        Args:
            project_id: The project UUID.

        Returns:
            List of project-extension override rows.
        """
        response = (
            self.supabase_client.table(PROJECT_EXTENSIONS_TABLE)
            .select("*")
            .eq("project_id", project_id)
            .execute()
        )
        return response.data

    def link_extension_to_project(self, extension_id: str, project_id: str) -> dict[str, Any]:
        """Append project_id to an extension's skill_groups, making it part of that project.

        Idempotent — if project_id is already in skill_groups, returns the extension unchanged.

        Raises:
            ValueError: If the extension_id does not exist.
            RuntimeError: If the database update fails.
        """
        ext = self.get_extension(extension_id)
        if ext is None:
            raise ValueError(f"Extension '{extension_id}' not found")

        skill_groups: list[str] = ext.get("skill_groups") or []
        if project_id in skill_groups:
            return ext

        updated_groups = [*skill_groups, project_id]
        response = (
            self.supabase_client.table(EXTENSIONS_TABLE)
            .update({"skill_groups": updated_groups, "updated_at": datetime.now(UTC).isoformat()})
            .eq("id", extension_id)
            .execute()
        )
        if not response.data:
            raise RuntimeError(f"Failed to link extension '{extension_id}' to project '{project_id}'")

        logger.info(f"Extension linked to project: {extension_id} -> {project_id}")
        return response.data[0]

    def unlink_extension_from_project(self, extension_id: str, project_id: str) -> dict[str, Any]:
        """Remove project_id from an extension's skill_groups.

        Idempotent — if project_id is not in skill_groups, returns the extension unchanged.

        Raises:
            ValueError: If the extension_id does not exist.
            RuntimeError: If the database update fails.
        """
        ext = self.get_extension(extension_id)
        if ext is None:
            raise ValueError(f"Extension '{extension_id}' not found")

        skill_groups: list[str] = ext.get("skill_groups") or []
        if project_id not in skill_groups:
            return ext

        updated_groups = [g for g in skill_groups if g != project_id]
        response = (
            self.supabase_client.table(EXTENSIONS_TABLE)
            .update({"skill_groups": updated_groups, "updated_at": datetime.now(UTC).isoformat()})
            .eq("id", extension_id)
            .execute()
        )
        if not response.data:
            raise RuntimeError(f"Failed to unlink extension '{extension_id}' from project '{project_id}'")

        logger.info(f"Extension unlinked from project: {extension_id} -> {project_id}")
        return response.data[0]

    def set_extension_default(self, extension_id: str, is_default: bool) -> dict[str, Any]:
        """Set or clear the is_default flag on an extension.

        Extensions with is_default = True are installed on every new Archon-connected application.

        Raises:
            ValueError: If the extension_id does not exist.
            RuntimeError: If the database update fails.
        """
        ext = self.get_extension(extension_id)
        if ext is None:
            raise ValueError(f"Extension '{extension_id}' not found")

        response = (
            self.supabase_client.table(EXTENSIONS_TABLE)
            .update({"is_default": is_default, "updated_at": datetime.now(UTC).isoformat()})
            .eq("id", extension_id)
            .execute()
        )
        if not response.data:
            raise RuntimeError(f"Failed to update is_default for extension '{extension_id}'")

        logger.info(f"Extension is_default set to {is_default}: {extension_id}")
        return response.data[0]

    def save_project_override(
        self,
        project_id: str,
        extension_id: str,
        custom_content: str | None = None,
        is_enabled: bool = True,
    ) -> dict[str, Any]:
        """Upsert a per-project extension override.

        Args:
            project_id: The project UUID.
            extension_id: The extension UUID.
            custom_content: Optional project-specific content override.
            is_enabled: Whether the extension is enabled for this project.

        Returns:
            The upserted project-extension row.
        """
        now = datetime.now(UTC).isoformat()

        upsert_data = {
            "project_id": project_id,
            "extension_id": extension_id,
            "custom_content": custom_content,
            "is_enabled": is_enabled,
            "updated_at": now,
        }

        response = (
            self.supabase_client.table(PROJECT_EXTENSIONS_TABLE)
            .upsert(upsert_data)
            .execute()
        )
        return response.data[0]

    def _save_version(
        self,
        extension_id: str,
        version_number: int,
        content: str,
        content_hash: str,
        created_by: str,
    ) -> None:
        """Save a version history entry for an extension.

        Args:
            extension_id: The extension UUID.
            version_number: Sequential version number.
            content: Full content snapshot at this version.
            content_hash: SHA-256 hash of the content.
            created_by: Identifier of the user or agent.
        """
        version_data = {
            "extension_id": extension_id,
            "version_number": version_number,
            "content": content,
            "content_hash": content_hash,
            "created_by": created_by,
            "created_at": datetime.now(UTC).isoformat(),
        }

        self.supabase_client.table(VERSIONS_TABLE).insert(version_data).execute()
        logger.debug(f"Version {version_number} saved for extension {extension_id}")
