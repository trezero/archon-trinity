-- Convert skill_group (single text) to skill_groups (text array) so an
-- extension can be visible to multiple projects.
--
-- Values inside the array:
--   'template'       → shared with all projects
--   <project_id UUID> → visible to that specific project

ALTER TABLE archon_extensions ADD COLUMN IF NOT EXISTS skill_groups TEXT[] NOT NULL DEFAULT '{template}';

-- Copy existing single-value skill_group into the new array column
UPDATE archon_extensions SET skill_groups = ARRAY[skill_group];

-- Drop the old scalar column and its index
DROP INDEX IF EXISTS idx_archon_extensions_skill_group;
ALTER TABLE archon_extensions DROP COLUMN IF EXISTS skill_group;

-- GIN index for efficient array overlap queries
CREATE INDEX IF NOT EXISTS idx_archon_extensions_skill_groups ON archon_extensions USING GIN(skill_groups);
