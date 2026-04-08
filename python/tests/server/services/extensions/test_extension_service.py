"""
Unit tests for ExtensionService.

Tests CRUD operations, version management, content hashing,
and project extension overrides using mocked Supabase client.
"""

from unittest.mock import MagicMock, call

import pytest

from src.server.services.extensions.extension_service import ExtensionService


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_supabase():
    """Create a mock Supabase client with chainable query methods."""
    client = MagicMock()

    # Each table() call returns a fresh query builder so tests
    # can configure different chains independently.
    def _table(name):
        builder = MagicMock(name=f"table({name})")
        # Chainable: select/insert/update/delete/upsert -> eq/neq/order/limit -> execute
        for method in ("select", "insert", "update", "delete", "upsert"):
            getattr(builder, method).return_value = builder
        builder.eq.return_value = builder
        builder.neq.return_value = builder
        builder.order.return_value = builder
        builder.limit.return_value = builder
        return builder

    client.table.side_effect = _table
    return client


@pytest.fixture
def service(mock_supabase):
    """Create an ExtensionService instance with mocked Supabase."""
    return ExtensionService(supabase_client=mock_supabase)


# ── Content Hashing ────────────────────────────────────────────────────────


class TestComputeContentHash:
    def test_returns_sha256_hex_digest(self):
        """Hash output should be a 64-character hex string (SHA-256)."""
        result = ExtensionService.compute_content_hash("hello world")
        assert isinstance(result, str)
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_same_content_same_hash(self):
        """Identical content must produce the same hash."""
        content = "---\nname: my-extension\n---\n## Body"
        assert ExtensionService.compute_content_hash(content) == ExtensionService.compute_content_hash(content)

    def test_different_content_different_hash(self):
        """Different content must produce different hashes."""
        hash_a = ExtensionService.compute_content_hash("content A")
        hash_b = ExtensionService.compute_content_hash("content B")
        assert hash_a != hash_b


# ── create_extension ────────────────────────────────────────────────────────


class TestCreateExtension:
    def test_inserts_extension_and_saves_version(self, service, mock_supabase):
        """create_extension should insert into extensions table and save version 1."""
        extension_row = {
            "id": "extension-uuid-1",
            "name": "my-extension",
            "description": "A useful extension",
            "content": "# Extension content",
            "content_hash": ExtensionService.compute_content_hash("# Extension content"),
            "current_version": 1,
            "created_by": "user-1",
        }

        # Configure extensions table insert
        extensions_builder = MagicMock()
        extensions_builder.insert.return_value = extensions_builder
        extensions_builder.execute.return_value = MagicMock(data=[extension_row])

        # Configure versions table insert
        versions_builder = MagicMock()
        versions_builder.insert.return_value = versions_builder
        versions_builder.execute.return_value = MagicMock(data=[{"id": "version-uuid-1"}])

        def _table(name):
            if name == "archon_extensions":
                return extensions_builder
            if name == "archon_extension_versions":
                return versions_builder
            return MagicMock()

        mock_supabase.table.side_effect = _table

        result = service.create_extension(
            name="my-extension",
            description="A useful extension",
            content="# Extension content",
            created_by="user-1",
        )

        assert result["id"] == "extension-uuid-1"
        assert result["name"] == "my-extension"
        assert result["current_version"] == 1

        # Verify insert was called on extensions table
        extensions_builder.insert.assert_called_once()
        insert_data = extensions_builder.insert.call_args[0][0]
        assert insert_data["name"] == "my-extension"
        assert insert_data["current_version"] == 1
        assert insert_data["content_hash"] == ExtensionService.compute_content_hash("# Extension content")

        # Verify version was saved
        versions_builder.insert.assert_called_once()

    def test_create_extension_raises_on_empty_response(self, service, mock_supabase):
        """create_extension should raise RuntimeError when insert returns no data."""
        builder = MagicMock()
        builder.insert.return_value = builder
        builder.execute.return_value = MagicMock(data=[])

        mock_supabase.table.side_effect = lambda name: builder

        with pytest.raises(RuntimeError, match="Failed to create extension"):
            service.create_extension(
                name="bad-extension",
                description="Will fail",
                content="# Content",
                created_by="user-1",
            )


# ── list_extensions ─────────────────────────────────────────────────────────


class TestListExtensions:
    def test_returns_extensions_without_content(self, service, mock_supabase):
        """list_extensions should select specific fields excluding content."""
        extensions_data = [
            {"id": "s1", "name": "extension-a", "description": "Desc A", "current_version": 1, "created_at": "2026-01-01"},
            {"id": "s2", "name": "extension-b", "description": "Desc B", "current_version": 2, "created_at": "2026-01-02"},
        ]

        builder = MagicMock()
        builder.select.return_value = builder
        builder.order.return_value = builder
        builder.execute.return_value = MagicMock(data=extensions_data)

        mock_supabase.table.side_effect = lambda name: builder

        result = service.list_extensions()

        assert len(result) == 2
        assert result[0]["name"] == "extension-a"
        assert result[1]["name"] == "extension-b"

        # Verify select was called with fields that exclude the full content column.
        # The select string may contain "content_hash" which is fine -- we check
        # that a bare "content" field (preceded by space or comma) is absent.
        builder.select.assert_called_once()
        select_arg = builder.select.call_args[0][0]
        fields = [f.strip() for f in select_arg.split(",")]
        assert "content" not in fields, "list_extensions should not select the 'content' column"


# ── get_extension ───────────────────────────────────────────────────────────


class TestGetExtension:
    def test_returns_full_extension_by_id(self, service, mock_supabase):
        """get_extension should return the full extension record including content."""
        extension_row = {
            "id": "s1",
            "name": "my-extension",
            "content": "# Full content",
            "current_version": 3,
        }

        builder = MagicMock()
        builder.select.return_value = builder
        builder.eq.return_value = builder
        builder.execute.return_value = MagicMock(data=[extension_row])

        mock_supabase.table.side_effect = lambda name: builder

        result = service.get_extension("s1")

        assert result is not None
        assert result["id"] == "s1"
        assert result["content"] == "# Full content"
        builder.select.assert_called_once_with("*")
        builder.eq.assert_called_once_with("id", "s1")

    def test_returns_none_for_missing_id(self, service, mock_supabase):
        """get_extension should return None when no extension is found."""
        builder = MagicMock()
        builder.select.return_value = builder
        builder.eq.return_value = builder
        builder.execute.return_value = MagicMock(data=[])

        mock_supabase.table.side_effect = lambda name: builder

        result = service.get_extension("nonexistent-id")

        assert result is None


# ── find_by_name ────────────────────────────────────────────────────────────


class TestFindByName:
    def test_finds_extension_by_name(self, service, mock_supabase):
        """find_by_name should look up an extension by its unique name."""
        extension_row = {"id": "s1", "name": "archon-memory", "content": "# Memory"}

        builder = MagicMock()
        builder.select.return_value = builder
        builder.eq.return_value = builder
        builder.limit.return_value = builder
        builder.execute.return_value = MagicMock(data=[extension_row])

        mock_supabase.table.side_effect = lambda name: builder

        result = service.find_by_name("archon-memory")

        assert result is not None
        assert result["name"] == "archon-memory"
        builder.eq.assert_called_once_with("name", "archon-memory")

    def test_returns_none_for_unknown_name(self, service, mock_supabase):
        """find_by_name should return None when no extension matches."""
        builder = MagicMock()
        builder.select.return_value = builder
        builder.eq.return_value = builder
        builder.limit.return_value = builder
        builder.execute.return_value = MagicMock(data=[])

        mock_supabase.table.side_effect = lambda name: builder

        result = service.find_by_name("nonexistent-extension")
        assert result is None


# ── update_extension ────────────────────────────────────────────────────────


class TestUpdateExtension:
    def test_bumps_version_and_saves_history(self, service, mock_supabase):
        """update_extension should increment version and save to version history."""
        updated_row = {
            "id": "s1",
            "name": "my-extension",
            "content": "# Updated content",
            "content_hash": ExtensionService.compute_content_hash("# Updated content"),
            "current_version": 3,
        }

        # Configure extensions table for update
        extensions_builder = MagicMock()
        extensions_builder.update.return_value = extensions_builder
        extensions_builder.eq.return_value = extensions_builder
        extensions_builder.execute.return_value = MagicMock(data=[updated_row])

        # Configure versions table for insert
        versions_builder = MagicMock()
        versions_builder.insert.return_value = versions_builder
        versions_builder.execute.return_value = MagicMock(data=[{"id": "v3"}])

        def _table(name):
            if name == "archon_extensions":
                return extensions_builder
            if name == "archon_extension_versions":
                return versions_builder
            return MagicMock()

        mock_supabase.table.side_effect = _table

        result = service.update_extension(
            extension_id="s1",
            content="# Updated content",
            new_version=3,
            updated_by="user-2",
        )

        assert result["current_version"] == 3
        assert result["content"] == "# Updated content"

        # Verify update was called
        extensions_builder.update.assert_called_once()
        update_data = extensions_builder.update.call_args[0][0]
        assert update_data["content"] == "# Updated content"
        assert update_data["current_version"] == 3
        assert "content_hash" in update_data
        assert "updated_at" in update_data

        # Verify version was saved
        versions_builder.insert.assert_called_once()

    def test_update_raises_on_empty_response(self, service, mock_supabase):
        """update_extension should raise RuntimeError when update returns no data."""
        builder = MagicMock()
        builder.update.return_value = builder
        builder.eq.return_value = builder
        builder.execute.return_value = MagicMock(data=[])

        mock_supabase.table.side_effect = lambda name: builder

        with pytest.raises(RuntimeError, match="Failed to update extension"):
            service.update_extension(
                extension_id="nonexistent",
                content="# Content",
                new_version=2,
                updated_by="user-1",
            )


# ── delete_extension ────────────────────────────────────────────────────────


class TestDeleteExtension:
    def test_deletes_extension_by_id(self, service, mock_supabase):
        """delete_extension should issue a delete query filtered by extension ID."""
        builder = MagicMock()
        builder.delete.return_value = builder
        builder.eq.return_value = builder
        builder.execute.return_value = MagicMock(data=[])

        mock_supabase.table.side_effect = lambda name: builder

        service.delete_extension("s1")

        mock_supabase.table.assert_called_with("archon_extensions")
        builder.delete.assert_called_once()
        builder.eq.assert_called_once_with("id", "s1")


# ── get_versions ────────────────────────────────────────────────────────────


class TestGetVersions:
    def test_returns_version_history(self, service, mock_supabase):
        """get_versions should return version history ordered by version number descending."""
        versions_data = [
            {"id": "v2", "extension_id": "s1", "version_number": 2, "content_hash": "abc123"},
            {"id": "v1", "extension_id": "s1", "version_number": 1, "content_hash": "def456"},
        ]

        builder = MagicMock()
        builder.select.return_value = builder
        builder.eq.return_value = builder
        builder.order.return_value = builder
        builder.execute.return_value = MagicMock(data=versions_data)

        mock_supabase.table.side_effect = lambda name: builder

        result = service.get_versions("s1")

        assert len(result) == 2
        assert result[0]["version_number"] == 2
        assert result[1]["version_number"] == 1

        mock_supabase.table.assert_called_with("archon_extension_versions")
        builder.eq.assert_called_once_with("extension_id", "s1")
        builder.order.assert_called_once_with("version_number", desc=True)


# ── save_project_override ───────────────────────────────────────────────────


class TestSaveProjectOverride:
    def test_upserts_into_project_extensions(self, service, mock_supabase):
        """save_project_override should upsert into archon_project_extensions."""
        override_row = {
            "project_id": "proj-1",
            "extension_id": "s1",
            "custom_content": "# Custom instructions",
            "is_enabled": True,
        }

        builder = MagicMock()
        builder.upsert.return_value = builder
        builder.execute.return_value = MagicMock(data=[override_row])

        mock_supabase.table.side_effect = lambda name: builder

        result = service.save_project_override(
            project_id="proj-1",
            extension_id="s1",
            custom_content="# Custom instructions",
            is_enabled=True,
        )

        assert result["project_id"] == "proj-1"
        assert result["extension_id"] == "s1"

        mock_supabase.table.assert_called_with("archon_project_extensions")
        builder.upsert.assert_called_once()
        upsert_data = builder.upsert.call_args[0][0]
        assert upsert_data["project_id"] == "proj-1"
        assert upsert_data["extension_id"] == "s1"
        assert upsert_data["custom_content"] == "# Custom instructions"
        assert upsert_data["is_enabled"] is True


# ── get_project_extensions ──────────────────────────────────────────────────


class TestGetProjectExtensions:
    def test_returns_project_extensions(self, service, mock_supabase):
        """get_project_extensions should return extensions linked to a project."""
        project_extensions_data = [
            {"project_id": "proj-1", "extension_id": "s1", "is_enabled": True, "custom_content": None},
            {"project_id": "proj-1", "extension_id": "s2", "is_enabled": False, "custom_content": "# Override"},
        ]

        builder = MagicMock()
        builder.select.return_value = builder
        builder.eq.return_value = builder
        builder.execute.return_value = MagicMock(data=project_extensions_data)

        mock_supabase.table.side_effect = lambda name: builder

        result = service.get_project_extensions("proj-1")

        assert len(result) == 2
        mock_supabase.table.assert_called_with("archon_project_extensions")
        builder.eq.assert_called_once_with("project_id", "proj-1")


# ── create_extension with type / plugin_manifest ────────────────────────────


class TestCreateExtensionWithType:
    def test_creates_extension_with_command_type(self, service, mock_supabase):
        """create_extension with type='command' should include type in the insert payload."""
        content = "# Archon Setup\n\nSome content."
        extension_row = {
            "id": "cmd-uuid-1",
            "name": "archon-setup",
            "type": "command",
            "content": content,
            "content_hash": ExtensionService.compute_content_hash(content),
        }

        extensions_builder = MagicMock()
        extensions_builder.insert.return_value = extensions_builder
        extensions_builder.execute.return_value = MagicMock(data=[extension_row])

        versions_builder = MagicMock()
        versions_builder.insert.return_value = versions_builder
        versions_builder.execute.return_value = MagicMock(data=[{"id": "v1"}])

        def _table(name):
            if name == "archon_extensions":
                return extensions_builder
            return versions_builder

        mock_supabase.table.side_effect = _table

        result = service.create_extension(
            name="archon-setup",
            description="Setup command",
            content=content,
            created_by="test",
            type="command",
        )

        insert_call = extensions_builder.insert.call_args
        assert insert_call[0][0]["type"] == "command"
        assert result["type"] == "command"

    def test_creates_extension_with_plugin_manifest(self, service, mock_supabase):
        """create_extension with plugin_manifest should include it in the insert payload."""
        manifest = {"command_group": "archon", "filename": "archon-prime.md"}
        extension_row = {
            "id": "cmd-uuid-2",
            "name": "archon-prime",
            "type": "command",
            "plugin_manifest": manifest,
        }

        extensions_builder = MagicMock()
        extensions_builder.insert.return_value = extensions_builder
        extensions_builder.execute.return_value = MagicMock(data=[extension_row])

        versions_builder = MagicMock()
        versions_builder.insert.return_value = versions_builder
        versions_builder.execute.return_value = MagicMock(data=[{"id": "v1"}])

        def _table(name):
            if name == "archon_extensions":
                return extensions_builder
            return versions_builder

        mock_supabase.table.side_effect = _table

        result = service.create_extension(
            name="archon-prime",
            description="Prime command",
            content="# Prime",
            created_by="test",
            type="command",
            plugin_manifest=manifest,
        )

        insert_call = extensions_builder.insert.call_args
        assert insert_call[0][0]["plugin_manifest"] == manifest

    def test_creates_extension_without_type_uses_db_default(self, service, mock_supabase):
        """create_extension without type should NOT include type in the payload (DB default applies)."""
        extension_row = {"id": "ext-uuid-1", "name": "my-skill"}

        extensions_builder = MagicMock()
        extensions_builder.insert.return_value = extensions_builder
        extensions_builder.execute.return_value = MagicMock(data=[extension_row])

        versions_builder = MagicMock()
        versions_builder.insert.return_value = versions_builder
        versions_builder.execute.return_value = MagicMock(data=[{"id": "v1"}])

        def _table(name):
            if name == "archon_extensions":
                return extensions_builder
            return versions_builder

        mock_supabase.table.side_effect = _table

        service.create_extension(
            name="my-skill",
            description="A skill",
            content="---\nname: my-skill\n---\n# Content",
            created_by="test",
        )

        insert_call = extensions_builder.insert.call_args
        assert "type" not in insert_call[0][0]
        assert "plugin_manifest" not in insert_call[0][0]


# ── list_extensions with type filter ────────────────────────────────────────


class TestListExtensionsTypeFilter:
    def test_list_extensions_filters_by_type(self, service, mock_supabase):
        """list_extensions with type='command' should add an eq filter on type."""
        command_extensions = [
            {"id": "c1", "name": "archon-setup", "type": "command"},
        ]

        builder = MagicMock()
        builder.select.return_value = builder
        builder.eq.return_value = builder
        builder.order.return_value = builder
        builder.execute.return_value = MagicMock(data=command_extensions)

        mock_supabase.table.side_effect = lambda name: builder

        result = service.list_extensions(type="command")

        assert len(result) == 1
        builder.eq.assert_called_once_with("type", "command")

    def test_list_extensions_no_type_filter_skips_eq(self, service, mock_supabase):
        """list_extensions without type param should not add a type eq filter."""
        builder = MagicMock()
        builder.select.return_value = builder
        builder.order.return_value = builder
        builder.execute.return_value = MagicMock(data=[])

        mock_supabase.table.side_effect = lambda name: builder

        service.list_extensions()

        builder.eq.assert_not_called()

    def test_list_extensions_full_filters_by_type(self, service, mock_supabase):
        """list_extensions_full with type='command' should add an eq filter on type."""
        builder = MagicMock()
        builder.select.return_value = builder
        builder.eq.return_value = builder
        builder.order.return_value = builder
        builder.execute.return_value = MagicMock(data=[{"id": "c1", "name": "cmd", "type": "command"}])

        mock_supabase.table.side_effect = lambda name: builder

        result = service.list_extensions_full(type="command")

        assert len(result) == 1
        builder.eq.assert_called_once_with("type", "command")

    def test_list_extensions_full_no_type_filter_skips_eq(self, service, mock_supabase):
        """list_extensions_full without type param should not add a type eq filter."""
        builder = MagicMock()
        builder.select.return_value = builder
        builder.order.return_value = builder
        builder.execute.return_value = MagicMock(data=[])

        mock_supabase.table.side_effect = lambda name: builder

        service.list_extensions_full()

        builder.eq.assert_not_called()

    def test_list_extensions_select_includes_type_field(self, service, mock_supabase):
        """list_extensions should include 'type' in the selected fields."""
        builder = MagicMock()
        builder.select.return_value = builder
        builder.order.return_value = builder
        builder.execute.return_value = MagicMock(data=[])

        mock_supabase.table.side_effect = lambda name: builder

        service.list_extensions()

        builder.select.assert_called_once()
        select_arg = builder.select.call_args[0][0]
        fields = [f.strip() for f in select_arg.split(",")]
        assert "type" in fields, "list_extensions should select the 'type' column"


# ── list_extensions_for_project ──────────────────────────────────────────────


class TestListExtensionsForProject:
    def test_filters_by_project_id_via_overlaps(self, service, mock_supabase):
        """list_extensions_for_project should filter by project_id using overlaps on skill_groups."""
        project_extensions = [
            {"id": "e1", "name": "proj-skill", "type": "skill", "skill_groups": ["proj-uuid-1"]},
        ]

        builder = MagicMock()
        builder.select.return_value = builder
        builder.overlaps.return_value = builder
        builder.order.return_value = builder
        builder.execute.return_value = MagicMock(data=project_extensions)

        mock_supabase.table.side_effect = lambda name: builder

        result = service.list_extensions_for_project("proj-uuid-1")

        assert len(result) == 1
        assert result[0]["name"] == "proj-skill"
        builder.overlaps.assert_called_once_with("skill_groups", ["proj-uuid-1"])

    def test_type_filter_adds_eq_constraint(self, service, mock_supabase):
        """list_extensions_for_project with type='command' should add an eq filter on type."""
        builder = MagicMock()
        builder.select.return_value = builder
        builder.overlaps.return_value = builder
        builder.eq.return_value = builder
        builder.order.return_value = builder
        builder.execute.return_value = MagicMock(data=[])

        mock_supabase.table.side_effect = lambda name: builder

        service.list_extensions_for_project("proj-uuid-1", type="command")

        builder.overlaps.assert_called_once_with("skill_groups", ["proj-uuid-1"])
        builder.eq.assert_called_once_with("type", "command")

    def test_no_type_filter_skips_eq(self, service, mock_supabase):
        """list_extensions_for_project without type param should not add a type eq filter."""
        builder = MagicMock()
        builder.select.return_value = builder
        builder.overlaps.return_value = builder
        builder.order.return_value = builder
        builder.execute.return_value = MagicMock(data=[])

        mock_supabase.table.side_effect = lambda name: builder

        service.list_extensions_for_project("proj-uuid-1")

        builder.eq.assert_not_called()

    def test_include_content_false_excludes_content_column(self, service, mock_supabase):
        """list_extensions_for_project with include_content=False should not select the content column."""
        builder = MagicMock()
        builder.select.return_value = builder
        builder.overlaps.return_value = builder
        builder.order.return_value = builder
        builder.execute.return_value = MagicMock(data=[])

        mock_supabase.table.side_effect = lambda name: builder

        service.list_extensions_for_project("proj-uuid-1", include_content=False)

        builder.select.assert_called_once()
        select_arg = builder.select.call_args[0][0]
        fields = [f.strip() for f in select_arg.split(",")]
        assert "content" not in fields, "include_content=False should not select the 'content' column"

    def test_include_content_true_selects_all_columns(self, service, mock_supabase):
        """list_extensions_for_project with include_content=True should select all columns."""
        builder = MagicMock()
        builder.select.return_value = builder
        builder.overlaps.return_value = builder
        builder.order.return_value = builder
        builder.execute.return_value = MagicMock(data=[])

        mock_supabase.table.side_effect = lambda name: builder

        service.list_extensions_for_project("proj-uuid-1", include_content=True)

        builder.select.assert_called_once_with("*")


# ── link_extension_to_project ──────────────────────────────────────────────


class TestLinkExtensionToProject:
    def test_appends_project_id_to_skill_groups(self, mock_supabase):
        """link_extension_to_project should add project_id to skill_groups."""
        extension_id = "ext-uuid-1"
        project_id = "proj-uuid-1"

        existing = {
            "id": extension_id,
            "name": "my-skill",
            "skill_groups": ["proj-uuid-0"],
            "updated_at": "2024-01-01T00:00:00+00:00",
        }
        updated = {**existing, "skill_groups": ["proj-uuid-0", project_id]}

        get_builder = MagicMock()
        get_builder.select.return_value = get_builder
        get_builder.eq.return_value = get_builder
        get_builder.execute.return_value = MagicMock(data=[existing])

        update_builder = MagicMock()
        update_builder.update.return_value = update_builder
        update_builder.eq.return_value = update_builder
        update_builder.execute.return_value = MagicMock(data=[updated])

        call_count = {"n": 0}

        def _table(name):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return get_builder
            return update_builder

        mock_supabase.table.side_effect = _table
        service = ExtensionService(supabase_client=mock_supabase)
        result = service.link_extension_to_project(extension_id, project_id)

        assert project_id in result["skill_groups"]
        update_builder.update.assert_called_once()
        update_call_kwargs = update_builder.update.call_args[0][0]
        assert project_id in update_call_kwargs["skill_groups"]

    def test_idempotent_when_already_linked(self, mock_supabase):
        """link_extension_to_project should return early if project_id already present."""
        extension_id = "ext-uuid-1"
        project_id = "proj-uuid-1"

        existing = {
            "id": extension_id,
            "name": "my-skill",
            "skill_groups": [project_id],
        }

        get_builder = MagicMock()
        get_builder.select.return_value = get_builder
        get_builder.eq.return_value = get_builder
        get_builder.execute.return_value = MagicMock(data=[existing])

        mock_supabase.table.side_effect = lambda name: get_builder
        service = ExtensionService(supabase_client=mock_supabase)
        result = service.link_extension_to_project(extension_id, project_id)

        assert result == existing
        # update should NOT be called
        get_builder.update.assert_not_called()

    def test_raises_value_error_when_extension_not_found(self, mock_supabase):
        """link_extension_to_project should raise ValueError for unknown extension_id."""
        get_builder = MagicMock()
        get_builder.select.return_value = get_builder
        get_builder.eq.return_value = get_builder
        get_builder.execute.return_value = MagicMock(data=[])

        mock_supabase.table.side_effect = lambda name: get_builder
        service = ExtensionService(supabase_client=mock_supabase)

        with pytest.raises(ValueError, match="not found"):
            service.link_extension_to_project("bad-id", "proj-1")


# ── unlink_extension_from_project ─────────────────────────────────────────


class TestUnlinkExtensionFromProject:
    def test_removes_project_id_from_skill_groups(self, mock_supabase):
        """unlink_extension_from_project should remove project_id from skill_groups."""
        extension_id = "ext-uuid-1"
        project_id = "proj-uuid-1"

        existing = {
            "id": extension_id,
            "name": "my-skill",
            "skill_groups": ["proj-uuid-0", project_id],
        }
        updated = {**existing, "skill_groups": ["proj-uuid-0"]}

        get_builder = MagicMock()
        get_builder.select.return_value = get_builder
        get_builder.eq.return_value = get_builder
        get_builder.execute.return_value = MagicMock(data=[existing])

        update_builder = MagicMock()
        update_builder.update.return_value = update_builder
        update_builder.eq.return_value = update_builder
        update_builder.execute.return_value = MagicMock(data=[updated])

        call_count = {"n": 0}

        def _table(name):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return get_builder
            return update_builder

        mock_supabase.table.side_effect = _table
        service = ExtensionService(supabase_client=mock_supabase)
        result = service.unlink_extension_from_project(extension_id, project_id)

        assert project_id not in result["skill_groups"]

    def test_idempotent_when_not_linked(self, mock_supabase):
        """unlink_extension_from_project should return early if project_id not present."""
        extension_id = "ext-uuid-1"
        project_id = "proj-uuid-1"

        existing = {"id": extension_id, "name": "my-skill", "skill_groups": []}

        get_builder = MagicMock()
        get_builder.select.return_value = get_builder
        get_builder.eq.return_value = get_builder
        get_builder.execute.return_value = MagicMock(data=[existing])

        mock_supabase.table.side_effect = lambda name: get_builder
        service = ExtensionService(supabase_client=mock_supabase)
        result = service.unlink_extension_from_project(extension_id, project_id)

        assert result == existing
        get_builder.update.assert_not_called()

    def test_raises_value_error_when_extension_not_found(self, mock_supabase):
        """unlink_extension_from_project should raise ValueError for unknown extension_id."""
        get_builder = MagicMock()
        get_builder.select.return_value = get_builder
        get_builder.eq.return_value = get_builder
        get_builder.execute.return_value = MagicMock(data=[])

        mock_supabase.table.side_effect = lambda name: get_builder
        service = ExtensionService(supabase_client=mock_supabase)

        with pytest.raises(ValueError, match="not found"):
            service.unlink_extension_from_project("bad-id", "proj-1")


# ── set_extension_default ─────────────────────────────────────────────────


class TestSetExtensionDefault:
    def test_sets_is_default_true(self, mock_supabase):
        """set_extension_default should update is_default on the extension."""
        extension_id = "ext-uuid-1"
        existing = {"id": extension_id, "name": "my-skill", "content": "# content", "content_hash": "abc", "current_version": 1}
        updated = {"id": extension_id, "name": "my-skill", "is_default": True}

        get_builder = MagicMock()
        get_builder.select.return_value = get_builder
        get_builder.eq.return_value = get_builder
        get_builder.execute.return_value = MagicMock(data=[existing])

        update_builder = MagicMock()
        update_builder.update.return_value = update_builder
        update_builder.eq.return_value = update_builder
        update_builder.execute.return_value = MagicMock(data=[updated])

        call_count = {"n": 0}

        def _table(name):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return get_builder
            return update_builder

        mock_supabase.table.side_effect = _table
        service = ExtensionService(supabase_client=mock_supabase)
        result = service.set_extension_default(extension_id, is_default=True)

        assert result["is_default"] is True
        update_kwargs = update_builder.update.call_args[0][0]
        assert update_kwargs["is_default"] is True

    def test_raises_value_error_when_extension_not_found(self, mock_supabase):
        """set_extension_default should raise ValueError when extension does not exist."""
        get_builder = MagicMock()
        get_builder.select.return_value = get_builder
        get_builder.eq.return_value = get_builder
        get_builder.execute.return_value = MagicMock(data=[])

        mock_supabase.table.side_effect = lambda name: get_builder
        service = ExtensionService(supabase_client=mock_supabase)

        with pytest.raises(ValueError, match="not found"):
            service.set_extension_default("bad-id", is_default=True)

    def test_raises_runtime_error_on_db_failure(self, mock_supabase):
        """set_extension_default should raise RuntimeError if update returns no data (after finding extension)."""
        extension_id = "ext-uuid-1"
        existing = {"id": extension_id, "name": "my-skill", "content": "# content", "content_hash": "abc", "current_version": 1}

        get_builder = MagicMock()
        get_builder.select.return_value = get_builder
        get_builder.eq.return_value = get_builder
        get_builder.execute.return_value = MagicMock(data=[existing])

        update_builder = MagicMock()
        update_builder.update.return_value = update_builder
        update_builder.eq.return_value = update_builder
        update_builder.execute.return_value = MagicMock(data=[])

        call_count = {"n": 0}

        def _table(name):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return get_builder
            return update_builder

        mock_supabase.table.side_effect = _table
        service = ExtensionService(supabase_client=mock_supabase)

        with pytest.raises(RuntimeError, match="Failed to update"):
            service.set_extension_default(extension_id, is_default=True)
