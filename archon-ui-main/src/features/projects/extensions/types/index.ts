export interface PluginManifest {
  hooks: string[];
  mcp_server: boolean;
  dependencies: string[];
  skills_included: string[];
  min_python_version: string;
}

export interface CommandMetadata {
  command_group: string | null;
  filename: string;
}

export interface Extension {
  id: string;
  name: string;
  display_name: string;
  description: string;
  content?: string;
  content_hash: string;
  current_version: number;
  is_required: boolean;
  is_validated: boolean;
  tags: string[];
  type: "skill" | "plugin" | "command";
  plugin_manifest?: PluginManifest | CommandMetadata | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface System {
  id: string;
  fingerprint: string;
  name: string;
  hostname: string | null;
  os: string | null;
  last_seen_at: string;
  created_at: string;
}

export interface SystemExtension {
  id: string;
  system_id: string;
  extension_id: string;
  project_id: string;
  status: "pending_install" | "installed" | "pending_remove" | "removed";
  installed_content_hash: string | null;
  installed_version: number | null;
  has_local_changes: boolean;
  updated_at: string;
  archon_extensions?: Extension;
}

export interface SystemWithExtensions extends System {
  extensions: SystemExtension[];
}

export interface ProjectExtensionsResponse {
  all_extensions: Extension[];
  systems: SystemWithExtensions[];
}

export interface ProjectSystemsResponse {
  systems: System[];
  count: number;
}

export interface ExtensionsListResponse {
  extensions: Extension[];
  count: number;
}
