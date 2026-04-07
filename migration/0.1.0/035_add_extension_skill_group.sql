-- Add skill_group column to archon_extensions for scoping extensions.
--
-- Values:
--   'template'  → shared with all projects (Archon built-in extensions)
--   <project_id UUID> → scoped to a specific project only
--
-- Existing extensions default to 'template' (global/shared).

ALTER TABLE archon_extensions ADD COLUMN IF NOT EXISTS skill_group TEXT NOT NULL DEFAULT 'template';

CREATE INDEX IF NOT EXISTS idx_archon_extensions_skill_group ON archon_extensions(skill_group);
