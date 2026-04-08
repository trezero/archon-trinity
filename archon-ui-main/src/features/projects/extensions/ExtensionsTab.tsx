import { Plus } from "lucide-react";
import { useState } from "react";
import { Button } from "@/features/ui/primitives";
import { AddExtensionDialog } from "./components/AddExtensionDialog";
import { SystemCard } from "./components/SystemCard";
import { SystemExtensionList } from "./components/SystemExtensionList";
import {
  useInstallExtension,
  useProjectExtensions,
  useRemoveExtension,
  useUnlinkSystem,
} from "./hooks/useExtensionQueries";

interface ExtensionsTabProps {
  projectId: string;
}

export function ExtensionsTab({ projectId }: ExtensionsTabProps) {
  const { data, isLoading, error } = useProjectExtensions(projectId);
  const installExtension = useInstallExtension();
  const removeExtension = useRemoveExtension();
  const unlinkSystem = useUnlinkSystem();
  const [selectedSystemId, setSelectedSystemId] = useState<string | null>(null);
  const [addDialogOpen, setAddDialogOpen] = useState(false);

  if (isLoading) {
    return <div className="flex items-center justify-center py-12 text-zinc-400">Loading extensions...</div>;
  }

  if (error) {
    return (
      <div className="flex items-center justify-center py-12 text-red-400">
        Failed to load extensions: {error.message}
      </div>
    );
  }

  const systems = data?.systems ?? [];
  const allExtensions = data?.all_extensions ?? [];
  const selectedSystem = systems.find((s) => s.id === selectedSystemId) ?? systems[0];

  const handleInstall = (extensionId: string) => {
    if (!selectedSystem) return;
    installExtension.mutate({ projectId, extensionId, systemIds: [selectedSystem.id] });
  };

  const handleRemove = (extensionId: string) => {
    if (!selectedSystem) return;
    removeExtension.mutate({ projectId, extensionId, systemIds: [selectedSystem.id] });
  };

  const handleUnlink = (systemId: string) => {
    unlinkSystem.mutate({ projectId, systemId });
    if (selectedSystemId === systemId) setSelectedSystemId(null);
  };

  return (
    <div className="space-y-4">
      {/* Header row with + Extension button */}
      <div className="flex justify-end">
        <Button size="sm" onClick={() => setAddDialogOpen(true)}>
          <Plus className="w-3.5 h-3.5 mr-1.5" />
          Extension
        </Button>
      </div>

      {systems.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 text-zinc-400 space-y-2">
          <p className="text-sm">No systems registered to this project yet.</p>
          <p className="text-xs text-zinc-500">
            Systems are registered when they connect via the Archon MCP server and run an extension sync.
          </p>
          {allExtensions.length > 0 && (
            <p className="text-xs text-zinc-500">
              {allExtensions.length} extension{allExtensions.length !== 1 ? "s" : ""} linked to this project.
            </p>
          )}
        </div>
      ) : (
        <div className="flex gap-4 h-full">
          {/* Systems list */}
          <div className="w-64 flex-shrink-0 space-y-2">
            <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Systems</h3>
            {systems.map((system) => (
              <SystemCard
                key={system.id}
                system={system}
                isSelected={system.id === (selectedSystem?.id ?? null)}
                onClick={() => setSelectedSystemId(system.id)}
                onUnlink={handleUnlink}
              />
            ))}
          </div>

          {/* Detail panel */}
          <div className="flex-1 min-w-0">
            {selectedSystem && (
              <div className="space-y-4">
                <div className="border-b border-white/10 pb-3">
                  <h3 className="text-lg font-medium text-white">{selectedSystem.name}</h3>
                  <div className="flex gap-4 mt-1 text-xs text-zinc-400">
                    {selectedSystem.hostname && <span>Host: {selectedSystem.hostname}</span>}
                    {selectedSystem.os && <span>OS: {selectedSystem.os}</span>}
                    <span>Last seen: {new Date(selectedSystem.last_seen_at).toLocaleString()}</span>
                  </div>
                </div>
                <SystemExtensionList
                  systemExtensions={selectedSystem.extensions}
                  allExtensions={allExtensions}
                  onInstall={handleInstall}
                  onRemove={handleRemove}
                />
              </div>
            )}
          </div>
        </div>
      )}

      <AddExtensionDialog
        open={addDialogOpen}
        onOpenChange={setAddDialogOpen}
        projectId={projectId}
        linkedExtensions={allExtensions}
      />
    </div>
  );
}
