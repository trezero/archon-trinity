"""Extensions management API endpoints for Archon.

Handles:
- Extension CRUD operations with version management
- System registration and lookup
- Project-scoped extension configuration and install queuing
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..config.logfire_config import get_logger, logfire
from ..services.extensions import ExtensionService, ExtensionValidationService, SystemService

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["extensions"])


# ── Request models ────────────────────────────────────────────────────────────


class CreateExtensionRequest(BaseModel):
    name: str
    description: str
    content: str
    created_by: str
    skill_groups: list[str] | None = None
    type: str | None = None
    plugin_manifest: dict | None = None


class UpdateExtensionRequest(BaseModel):
    content: str
    updated_by: str
    description: str | None = None


class ValidateExtensionRequest(BaseModel):
    content: str


class UpdateSystemRequest(BaseModel):
    name: str | None = None
    hostname: str | None = None


class SaveProjectOverrideRequest(BaseModel):
    custom_content: str | None = None
    is_enabled: bool = True


class InstallExtensionRequest(BaseModel):
    system_ids: list[str]


class RemoveExtensionRequest(BaseModel):
    system_ids: list[str]


class RegisterSystemRequest(BaseModel):
    fingerprint: str
    name: str
    hostname: str | None = None
    os: str | None = None


class SyncSystemRequest(BaseModel):
    fingerprint: str
    system_name: str | None = None
    hostname: str | None = None
    os: str | None = None
    local_extensions: list[dict[str, Any]] = []


class SetExtensionDefaultRequest(BaseModel):
    is_default: bool


# ── Extensions CRUD ───────────────────────────────────────────────────────────


@router.post("/extensions/validate")
async def validate_extension_standalone(request: ValidateExtensionRequest):
    """Validate extension content without requiring an existing extension ID."""
    try:
        logfire.debug("Validating extension content (standalone)")
        validator = ExtensionValidationService()
        result = validator.validate(request.content)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logfire.error(f"Failed to validate extension | error={e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(e)}) from e


@router.get("/extensions")
async def list_extensions(
    include_content: bool = Query(False),
    skill_group: str | None = Query(None),
    type: str | None = Query(None),
):
    """List all extensions. Pass ?include_content=true to include full extension content."""
    try:
        logfire.debug(f"Listing all extensions | include_content={include_content}")
        service = ExtensionService()
        if include_content:
            extensions = service.list_extensions_full(skill_group=skill_group, type=type)
        else:
            extensions = service.list_extensions(skill_group=skill_group, type=type)
        return {"extensions": extensions, "count": len(extensions)}
    except HTTPException:
        raise
    except Exception as e:
        logfire.error(f"Failed to list extensions | error={e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(e)}) from e


@router.get("/extensions/{extension_id}")
async def get_extension(extension_id: str):
    """Get a single extension by ID including full content."""
    try:
        logfire.debug(f"Getting extension | extension_id={extension_id}")
        service = ExtensionService()
        extension = service.get_extension(extension_id)
        if extension is None:
            raise HTTPException(status_code=404, detail=f"Extension '{extension_id}' not found")
        return extension
    except HTTPException:
        raise
    except Exception as e:
        logfire.error(f"Failed to get extension | extension_id={extension_id} | error={e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(e)}) from e


@router.post("/extensions")
async def create_extension(request: CreateExtensionRequest):
    """Create a new extension. Validates content before saving.

    Returns 409 Conflict if an extension with the same name already exists,
    allowing callers to fall back to a PUT update.
    """
    try:
        logfire.info(f"Creating extension | name={request.name}")

        service = ExtensionService()

        # Check for duplicate name before inserting
        existing = service.find_by_name(request.name)
        if existing:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": f"Extension '{request.name}' already exists",
                    "existing_id": existing["id"],
                },
            )

        # Validate content first
        validator = ExtensionValidationService()
        validation = validator.validate(request.content, extension_type=request.type or "skill")
        if not validation["valid"]:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Extension content validation failed",
                    "errors": validation["errors"],
                    "warnings": validation["warnings"],
                },
            )

        extension = service.create_extension(
            name=request.name,
            description=request.description,
            content=request.content,
            created_by=request.created_by,
            skill_groups=request.skill_groups,
            type=request.type,
            plugin_manifest=request.plugin_manifest,
        )

        logfire.info(f"Extension created | extension_id={extension.get('id')} | name={request.name}")
        return extension
    except HTTPException:
        raise
    except Exception as e:
        logfire.error(f"Failed to create extension | name={request.name} | error={e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(e)}) from e


@router.put("/extensions/{extension_id}")
async def update_extension(extension_id: str, request: UpdateExtensionRequest):
    """Update an extension's content and bump its version."""
    try:
        logfire.info(f"Updating extension | extension_id={extension_id}")

        service = ExtensionService()

        # Fetch existing extension to compute next version and validate name
        existing = service.get_extension(extension_id)
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Extension '{extension_id}' not found")

        # Validate content (pass existing name so name-change is rejected)
        validator = ExtensionValidationService()
        validation = validator.validate(request.content, existing_name=existing.get("name"))
        if not validation["valid"]:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Extension content validation failed",
                    "errors": validation["errors"],
                    "warnings": validation["warnings"],
                },
            )

        new_version = existing["current_version"] + 1
        extension = service.update_extension(
            extension_id=extension_id,
            content=request.content,
            new_version=new_version,
            updated_by=request.updated_by,
            description=request.description,
        )

        logfire.info(f"Extension updated | extension_id={extension_id} | version={new_version}")
        return extension
    except HTTPException:
        raise
    except Exception as e:
        logfire.error(f"Failed to update extension | extension_id={extension_id} | error={e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(e)}) from e


@router.delete("/extensions/{extension_id}")
async def delete_extension(extension_id: str):
    """Delete an extension and its version history."""
    try:
        logfire.info(f"Deleting extension | extension_id={extension_id}")

        service = ExtensionService()

        # Verify extension exists
        existing = service.get_extension(extension_id)
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Extension '{extension_id}' not found")

        service.delete_extension(extension_id)
        logfire.info(f"Extension deleted | extension_id={extension_id}")
        return {"status": "deleted", "extension_id": extension_id}
    except HTTPException:
        raise
    except Exception as e:
        logfire.error(f"Failed to delete extension | extension_id={extension_id} | error={e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(e)}) from e


@router.post("/extensions/{extension_id}/validate")
async def validate_extension(extension_id: str, request: ValidateExtensionRequest):
    """Validate extension content without saving. Returns errors and warnings."""
    try:
        logfire.debug(f"Validating extension content | extension_id={extension_id}")

        service = ExtensionService()
        existing = service.get_extension(extension_id)
        existing_name = existing.get("name") if existing else None

        validator = ExtensionValidationService()
        result = validator.validate(request.content, existing_name=existing_name)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logfire.error(f"Failed to validate extension | extension_id={extension_id} | error={e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(e)}) from e


@router.get("/extensions/{extension_id}/versions")
async def get_extension_versions(extension_id: str):
    """Get version history for an extension, newest first."""
    try:
        logfire.debug(f"Getting extension versions | extension_id={extension_id}")

        service = ExtensionService()

        # Verify extension exists
        existing = service.get_extension(extension_id)
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Extension '{extension_id}' not found")

        versions = service.get_versions(extension_id)
        return {"versions": versions, "count": len(versions)}
    except HTTPException:
        raise
    except Exception as e:
        logfire.error(f"Failed to get extension versions | extension_id={extension_id} | error={e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(e)}) from e


# ── Systems ───────────────────────────────────────────────────────────────────


@router.post("/systems")
async def register_system(request: RegisterSystemRequest):
    """Register a new system or return existing one if fingerprint already exists."""
    try:
        logfire.info(f"Registering system | fingerprint={request.fingerprint}")
        service = SystemService()

        # Check if system already exists by fingerprint
        existing = service.find_by_fingerprint(request.fingerprint)
        if existing:
            # Update last seen and return existing
            service.update_last_seen(existing["id"])
            return {"system": existing, "is_new": False}

        system = service.register_system(
            fingerprint=request.fingerprint,
            name=request.name,
            hostname=request.hostname,
            os=request.os,
        )
        logfire.info(f"System registered | system_id={system.get('id')}")
        return {"system": system, "is_new": True}
    except HTTPException:
        raise
    except Exception as e:
        logfire.error(f"Failed to register system | fingerprint={request.fingerprint} | error={e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(e)}) from e


@router.get("/systems")
async def list_systems():
    """List all registered systems."""
    try:
        logfire.debug("Listing all systems")
        service = SystemService()
        systems = service.list_systems()
        return {"systems": systems, "count": len(systems)}
    except HTTPException:
        raise
    except Exception as e:
        logfire.error(f"Failed to list systems | error={e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(e)}) from e


@router.get("/systems/{system_id}")
async def get_system(system_id: str):
    """Get a single system by ID."""
    try:
        logfire.debug(f"Getting system | system_id={system_id}")
        service = SystemService()
        system = service.get_system(system_id)
        if system is None:
            raise HTTPException(status_code=404, detail=f"System '{system_id}' not found")
        return system
    except HTTPException:
        raise
    except Exception as e:
        logfire.error(f"Failed to get system | system_id={system_id} | error={e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(e)}) from e


@router.put("/systems/{system_id}")
async def update_system(system_id: str, request: UpdateSystemRequest):
    """Update a system's mutable fields (name, hostname)."""
    try:
        logfire.info(f"Updating system | system_id={system_id}")
        service = SystemService()
        system = service.update_system(
            system_id=system_id,
            name=request.name,
            hostname=request.hostname,
        )
        if system is None:
            raise HTTPException(status_code=404, detail=f"System '{system_id}' not found")

        logfire.info(f"System updated | system_id={system_id}")
        return system
    except HTTPException:
        raise
    except Exception as e:
        logfire.error(f"Failed to update system | system_id={system_id} | error={e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(e)}) from e


@router.delete("/systems/{system_id}")
async def delete_system(system_id: str):
    """Delete a system by ID."""
    try:
        logfire.info(f"Deleting system | system_id={system_id}")
        service = SystemService()
        deleted = service.delete_system(system_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"System '{system_id}' not found")

        logfire.info(f"System deleted | system_id={system_id}")
        return {"status": "deleted", "system_id": system_id}
    except HTTPException:
        raise
    except Exception as e:
        logfire.error(f"Failed to delete system | system_id={system_id} | error={e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(e)}) from e


@router.patch("/extensions/{extension_id}/default")
async def set_extension_default(extension_id: str, request: SetExtensionDefaultRequest):
    """Toggle is_default on a single extension.

    Extensions with is_default=True are included in the default template installed
    on every new Archon-connected application.
    """
    try:
        logfire.info(f"Setting is_default | extension_id={extension_id} | is_default={request.is_default}")
        extension_service = ExtensionService()
        extension = extension_service.set_extension_default(extension_id, request.is_default)
        return extension
    except ValueError as e:
        raise HTTPException(status_code=404, detail={"error": str(e)}) from e
    except Exception as e:
        logfire.error(f"Failed to set is_default | extension_id={extension_id} | error={e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(e)}) from e


# ── Project-scoped extensions ─────────────────────────────────────────────────


@router.post("/projects/{project_id}/sync")
async def sync_system(project_id: str, request: SyncSystemRequest):
    """Register a system for a project and compute a skill sync report.

    Registers the system globally (or updates last_seen), associates it with
    the project so it appears in the Skills tab, then compares the system's
    local extensions against the Archon registry and returns a full sync report.
    """
    try:
        logfire.info(f"Syncing system | project_id={project_id} | fingerprint={request.fingerprint}")

        system_service = SystemService()
        extension_service = ExtensionService()

        from ..services.extensions.extension_sync_service import ExtensionSyncService

        sync_service = ExtensionSyncService()

        # Register or look up system
        existing = system_service.find_by_fingerprint(request.fingerprint)
        if existing:
            system_service.update_last_seen(existing["id"])
            system = existing
            is_new = False
        else:
            name = request.system_name or request.fingerprint
            system = system_service.register_system(
                fingerprint=request.fingerprint,
                name=name,
                hostname=request.hostname,
                os=request.os,
            )
            is_new = True

        system_id = system["id"]

        # Associate system with this project
        sync_service.register_system_for_project(system_id, project_id)

        # Fetch full extension registry (content needed for pending_install items)
        archon_extensions = extension_service.list_extensions_full()

        # Fetch existing system-project install records
        system_extensions = sync_service.get_system_extensions(system_id, project_id)

        # Compute sync report
        report = sync_service.compute_sync_report(
            local_extensions=request.local_extensions,
            archon_extensions=archon_extensions,
            system_extensions=system_extensions,
        )

        # Persist "installed" status for extensions that are in sync locally
        archon_by_name: dict[str, dict[str, Any]] = {e["name"]: e for e in archon_extensions}
        for name in report["in_sync"]:
            ext = archon_by_name.get(name)
            if ext:
                sync_service.set_install_status(
                    system_id=system_id,
                    extension_id=ext["id"],
                    project_id=project_id,
                    status="installed",
                    installed_content_hash=ext.get("content_hash"),
                    installed_version=ext.get("current_version"),
                )

        logfire.info(
            f"Sync complete | project_id={project_id} | system_id={system_id} | "
            f"in_sync={len(report['in_sync'])} | pending_install={len(report['pending_install'])} | "
            f"local_changes={len(report['local_changes'])} | unknown_local={len(report['unknown_local'])}"
        )

        return {
            "system": {**system, "is_new": is_new},
            **report,
        }

    except HTTPException:
        raise
    except Exception as e:
        logfire.error(f"Failed to sync system | project_id={project_id} | error={e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(e)}) from e


@router.get("/projects/{project_id}/extensions")
async def get_project_extensions(project_id: str, type: str | None = Query(None)):
    """Get extensions data for a project.

    Returns all extensions from the registry and systems with their install state,
    matching the frontend ProjectExtensionsResponse shape: {all_extensions, systems}.
    """
    try:
        logfire.debug(f"Getting project extensions | project_id={project_id}")
        extension_service = ExtensionService()
        all_extensions = extension_service.list_extensions_for_project(project_id, type=type)

        # Build systems with nested extension install state
        systems_with_extensions: list[dict[str, Any]] = []
        try:
            from ..services.extensions.extension_sync_service import ExtensionSyncService

            sync_service = ExtensionSyncService()
            systems = sync_service.get_project_systems(project_id)

            for system in systems:
                sys_extensions = sync_service.get_system_project_extensions(system["id"], project_id)
                systems_with_extensions.append({**system, "extensions": sys_extensions})
        except ImportError:
            pass

        return {
            "all_extensions": all_extensions,
            "systems": systems_with_extensions,
        }

    except HTTPException:
        raise
    except Exception as e:
        logfire.error(f"Failed to get project extensions | project_id={project_id} | error={e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(e)}) from e


@router.get("/projects/{project_id}/systems")
async def get_project_systems(project_id: str):
    """Get systems associated with a project."""
    try:
        logfire.debug(f"Getting project systems | project_id={project_id}")

        try:
            from ..services.extensions.extension_sync_service import ExtensionSyncService

            sync_service = ExtensionSyncService()
            systems = sync_service.get_project_systems(project_id)
            return {"systems": systems, "count": len(systems)}
        except ImportError:
            raise HTTPException(
                status_code=501,
                detail="ExtensionSyncService is not yet available. Project-system mapping requires the sync service.",
            ) from None

    except HTTPException:
        raise
    except Exception as e:
        logfire.error(f"Failed to get project systems | project_id={project_id} | error={e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(e)}) from e


@router.delete("/projects/{project_id}/systems/{system_id}")
async def unlink_system_from_project(project_id: str, system_id: str):
    """Remove a system's association with a project.

    The system remains in the global archon_systems table — only the
    project-level link in archon_project_system_registrations is removed.
    """
    try:
        logfire.info(f"Unlinking system | project_id={project_id} | system_id={system_id}")

        from ..services.extensions.extension_sync_service import ExtensionSyncService

        sync_service = ExtensionSyncService()
        found = sync_service.unlink_system_from_project(system_id, project_id)

        if not found:
            raise HTTPException(status_code=404, detail={"error": "System-project association not found"})

        logfire.info(f"System unlinked | project_id={project_id} | system_id={system_id}")
        return {"status": "unlinked", "project_id": project_id, "system_id": system_id}

    except HTTPException:
        raise
    except Exception as e:
        logfire.error(
            f"Failed to unlink system | project_id={project_id} | system_id={system_id} | error={e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail={"error": str(e)}) from e


@router.post("/projects/{project_id}/extensions/{extension_id}/link")
async def link_extension_to_project(project_id: str, extension_id: str):
    """Associate an extension with a project by adding project_id to its skill_groups.

    Idempotent — calling it again when already linked is a no-op.
    """
    try:
        logfire.info(f"Linking extension to project | project_id={project_id} | extension_id={extension_id}")
        extension_service = ExtensionService()
        extension = extension_service.link_extension_to_project(extension_id, project_id)
        return extension
    except ValueError as e:
        raise HTTPException(status_code=404, detail={"error": str(e)}) from e
    except Exception as e:
        logfire.error(
            f"Failed to link extension | project_id={project_id} | extension_id={extension_id} | error={e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail={"error": str(e)}) from e


@router.delete("/projects/{project_id}/extensions/{extension_id}/link")
async def unlink_extension_from_project_route(project_id: str, extension_id: str):
    """Remove an extension from a project by removing project_id from its skill_groups.

    Idempotent — calling it when not linked is a no-op.
    """
    try:
        logfire.info(f"Unlinking extension from project | project_id={project_id} | extension_id={extension_id}")
        extension_service = ExtensionService()
        extension = extension_service.unlink_extension_from_project(extension_id, project_id)
        return extension
    except ValueError as e:
        raise HTTPException(status_code=404, detail={"error": str(e)}) from e
    except Exception as e:
        logfire.error(
            f"Failed to unlink extension | project_id={project_id} | extension_id={extension_id} | error={e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail={"error": str(e)}) from e


@router.post("/projects/{project_id}/extensions/{extension_id}/install")
async def install_extension(project_id: str, extension_id: str, request: InstallExtensionRequest):
    """Queue an extension install on specified systems for a project."""
    try:
        logfire.info(
            f"Queueing extension install | project_id={project_id} | extension_id={extension_id} | "
            f"system_count={len(request.system_ids)}"
        )

        if not request.system_ids:
            raise HTTPException(status_code=422, detail="At least one system_id is required")

        try:
            from ..services.extensions.extension_sync_service import ExtensionSyncService

            sync_service = ExtensionSyncService()
            result = sync_service.queue_install(
                system_ids=request.system_ids,
                extension_id=extension_id,
                project_id=project_id,
            )

            logfire.info(f"Extension install queued | project_id={project_id} | extension_id={extension_id}")
            return {"queued": result, "extension_id": extension_id, "project_id": project_id}
        except ImportError:
            raise HTTPException(
                status_code=501,
                detail="ExtensionSyncService is not yet available. Install queuing requires the sync service.",
            ) from None

    except HTTPException:
        raise
    except Exception as e:
        logfire.error(
            f"Failed to queue extension install | project_id={project_id} | extension_id={extension_id} | error={e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail={"error": str(e)}) from e


@router.post("/projects/{project_id}/extensions/{extension_id}/remove")
async def remove_extension(project_id: str, extension_id: str, request: RemoveExtensionRequest):
    """Queue an extension removal on specified systems for a project."""
    try:
        logfire.info(
            f"Queueing extension removal | project_id={project_id} | extension_id={extension_id} | "
            f"system_count={len(request.system_ids)}"
        )

        if not request.system_ids:
            raise HTTPException(status_code=422, detail="At least one system_id is required")

        try:
            from ..services.extensions.extension_sync_service import ExtensionSyncService

            sync_service = ExtensionSyncService()
            result = sync_service.queue_remove(
                system_ids=request.system_ids,
                extension_id=extension_id,
                project_id=project_id,
            )

            logfire.info(f"Extension removal queued | project_id={project_id} | extension_id={extension_id}")
            return {"queued": result, "extension_id": extension_id, "project_id": project_id}
        except ImportError:
            raise HTTPException(
                status_code=501,
                detail="ExtensionSyncService is not yet available. Removal queuing requires the sync service.",
            ) from None

    except HTTPException:
        raise
    except Exception as e:
        logfire.error(
            f"Failed to queue extension removal | project_id={project_id} | extension_id={extension_id} | error={e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail={"error": str(e)}) from e


@router.put("/projects/{project_id}/extensions/{extension_id}")
async def save_project_override(project_id: str, extension_id: str, request: SaveProjectOverrideRequest):
    """Save a per-project extension override (custom content and/or enabled state)."""
    try:
        logfire.info(f"Saving project extension override | project_id={project_id} | extension_id={extension_id}")

        service = ExtensionService()

        # Verify extension exists
        existing = service.get_extension(extension_id)
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Extension '{extension_id}' not found")

        # Validate custom content if provided
        if request.custom_content is not None:
            validator = ExtensionValidationService()
            validation = validator.validate(request.custom_content, existing_name=existing.get("name"))
            if not validation["valid"]:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "message": "Custom content validation failed",
                        "errors": validation["errors"],
                        "warnings": validation["warnings"],
                    },
                )

        override = service.save_project_override(
            project_id=project_id,
            extension_id=extension_id,
            custom_content=request.custom_content,
            is_enabled=request.is_enabled,
        )

        logfire.info(f"Project extension override saved | project_id={project_id} | extension_id={extension_id}")
        return override
    except HTTPException:
        raise
    except Exception as e:
        logfire.error(
            f"Failed to save project override | project_id={project_id} | extension_id={extension_id} | error={e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail={"error": str(e)}) from e
