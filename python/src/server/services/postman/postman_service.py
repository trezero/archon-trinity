"""Orchestration layer for Postman API operations."""

import json
from typing import Any

from src.server.config.logfire_config import get_logger
from src.server.services.credential_service import credential_service

from .config import PostmanConfig
from .postman_client import PostmanClient

logger = get_logger(__name__)


class PostmanService:
    """Thin orchestration layer over PostmanClient using centralized credentials."""

    async def get_sync_mode(self) -> str:
        """Get the current Postman sync mode from settings."""
        mode = await credential_service.get_credential("POSTMAN_SYNC_MODE", decrypt=False)
        if mode is None:
            return "disabled"
        return mode if mode in ("api", "git", "disabled") else "disabled"

    async def _get_client(self) -> PostmanClient:
        """Create a PostmanClient using credentials from archon_settings."""
        api_key = await credential_service.get_credential("POSTMAN_API_KEY", decrypt=True)
        workspace_id = await credential_service.get_credential("POSTMAN_WORKSPACE_ID", decrypt=False)

        if not api_key:
            raise ValueError("POSTMAN_API_KEY not configured in Archon Settings.")

        config = PostmanConfig(
            api_key=api_key,
            workspace_id=workspace_id or "",
        )
        config.validate()
        return PostmanClient(config=config)

    async def get_or_create_collection(self, project_name: str) -> str:
        """Find a collection by name or create it. Returns the collection UID."""
        client = await self._get_client()
        collections = client.list_collections()

        for col in collections:
            if col.get("name") == project_name:
                logger.info(f"Found existing collection | name={project_name} | uid={col['uid']}")
                return col["uid"]

        result = client.create_collection({
            "info": {
                "name": project_name,
                "description": f"API collection for {project_name}.",
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            },
            "item": [],
        })
        uid = result.get("uid", result.get("id", ""))
        logger.info(f"Created new collection | name={project_name} | uid={uid}")
        return uid

    async def upsert_request(
        self,
        collection_uid: str,
        folder_name: str,
        request_data: dict[str, Any],
    ) -> None:
        """Add or update a request in a collection folder. Creates the folder if needed."""
        client = await self._get_client()
        collection = client.get_collection(collection_uid)
        items = collection.get("item", [])

        # Find or create folder
        folder = None
        for item in items:
            if item.get("name") == folder_name and "item" in item:
                folder = item
                break

        if folder is None:
            folder = {"name": folder_name, "item": []}
            items.append(folder)

        # Build the Postman request object
        request_name = request_data.get("name", "Unnamed Request")
        postman_request = self._build_postman_request(request_data)

        # Find existing request by name and update, or append
        existing_idx = None
        for i, req in enumerate(folder["item"]):
            if req.get("name") == request_name:
                existing_idx = i
                break

        request_item: dict[str, Any] = {"name": request_name, "request": postman_request}

        # Attach pre-request and test scripts as Postman events if provided
        events: list[dict[str, Any]] = []
        pre_request_script = request_data.get("pre_request_script")
        if pre_request_script:
            events.append({
                "listen": "prerequest",
                "script": {"type": "text/javascript", "exec": pre_request_script.split("\n")},
            })
        test_script = request_data.get("test_script")
        if test_script:
            events.append({
                "listen": "test",
                "script": {"type": "text/javascript", "exec": test_script.split("\n")},
            })
        if events:
            request_item["event"] = events

        if existing_idx is not None:
            folder["item"][existing_idx] = request_item
            logger.info(f"Updated request | folder={folder_name} | name={request_name}")
        else:
            folder["item"].append(request_item)
            logger.info(f"Added request | folder={folder_name} | name={request_name}")

        collection["item"] = items
        client.update_collection(collection_uid, collection)

    async def upsert_environment(self, env_name: str, variables: dict[str, str]) -> dict[str, Any]:
        """Create or update an environment with auto-secret detection."""
        client = await self._get_client()
        envs = client.list_environments()

        existing = None
        for env in envs:
            if not isinstance(env, dict):
                continue
            if env.get("name") == env_name:
                existing = env
                break

        values = [{"key": k, "value": v, "enabled": True} for k, v in variables.items()]

        if existing:
            result = client.update_environment(existing["uid"], name=env_name, values=values)
            logger.info(f"Updated environment | name={env_name}")
        else:
            result = client.create_environment(env_name, variables)
            logger.info(f"Created environment | name={env_name}")

        return result

    async def list_collection_structure(self, collection_uid: str) -> dict[str, list[dict[str, str]]]:
        """Return a dict of folder_name -> list of {name, method, url} for dedup checking."""
        client = await self._get_client()
        collection = client.get_collection(collection_uid)
        items = collection.get("item", [])

        structure: dict[str, list[dict[str, str]]] = {}
        for item in items:
            if "item" in item:
                folder_name = item["name"]
                structure[folder_name] = []
                for req in item["item"]:
                    request = req.get("request", {})
                    url = request.get("url", "")
                    if isinstance(url, dict):
                        url = url.get("raw", "")
                    structure[folder_name].append({
                        "name": req.get("name", ""),
                        "method": request.get("method", ""),
                        "url": url,
                    })
        return structure

    def _build_postman_request(self, request_data: dict[str, Any]) -> dict[str, Any]:
        """Convert simplified request dict to Postman collection format."""
        url = request_data.get("url", "")
        postman_req: dict[str, Any] = {
            "method": request_data.get("method", "GET"),
            "header": [{"key": k, "value": v} for k, v in request_data.get("headers", {}).items()],
            "url": url,
            "description": request_data.get("description", ""),
        }

        body = request_data.get("body")
        if body:
            postman_req["body"] = {
                "mode": "raw",
                "raw": json.dumps(body, indent=2) if isinstance(body, dict) else str(body),
                "options": {"raw": {"language": "json"}},
            }

        return postman_req
