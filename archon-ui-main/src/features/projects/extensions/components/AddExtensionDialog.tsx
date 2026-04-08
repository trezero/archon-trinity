import { Plus, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { useToast } from "@/features/shared/hooks/useToast";
import { Button, Input } from "@/features/ui/primitives";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/features/ui/primitives/dialog";
import { useAllExtensions, useLinkExtensions } from "../hooks/useExtensionQueries";
import type { Extension } from "../types";

interface AddExtensionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string;
  linkedExtensions: Extension[];
}

const TYPE_LABELS: Record<string, string> = {
  skill: "Skills",
  command: "Commands",
  plugin: "Plugins",
};

const TYPE_COLORS: Record<string, string> = {
  skill: "bg-cyan-500/20 text-cyan-400 border-cyan-500/30",
  command: "bg-violet-500/20 text-violet-400 border-violet-500/30",
  plugin: "bg-amber-500/20 text-amber-400 border-amber-500/30",
};

const TYPE_ORDER = ["skill", "command", "plugin"] as const;

export function AddExtensionDialog({ open, onOpenChange, projectId, linkedExtensions }: AddExtensionDialogProps) {
  const { showToast } = useToast();
  const { data: allExtData, isLoading: isLoadingExtensions, isError: isExtensionsError } = useAllExtensions();
  const linkExtensions = useLinkExtensions();

  const [search, setSearch] = useState("");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const linkedIds = useMemo(() => new Set(linkedExtensions.map((e) => e.id)), [linkedExtensions]);

  const available = useMemo(() => {
    const all = allExtData?.extensions ?? [];
    const unlinked = all.filter((e) => !linkedIds.has(e.id));
    if (!search.trim()) return unlinked;
    const q = search.toLowerCase();
    return unlinked.filter(
      (e) =>
        e.name.toLowerCase().includes(q) ||
        (e.display_name ?? "").toLowerCase().includes(q) ||
        (e.description ?? "").toLowerCase().includes(q),
    );
  }, [allExtData, linkedIds, search]);

  const grouped = useMemo(() => {
    const groups: Record<string, Extension[]> = {};
    for (const ext of available) {
      const key = ext.type ?? "skill";
      if (!groups[key]) groups[key] = [];
      groups[key].push(ext);
    }
    return groups;
  }, [available]);

  const toggleSelected = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    if (selectedIds.size === available.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(available.map((e) => e.id)));
    }
  };

  const handleAdd = async () => {
    if (selectedIds.size === 0) return;
    try {
      await linkExtensions.mutateAsync({ projectId, extensionIds: Array.from(selectedIds) });
      showToast(`Added ${selectedIds.size} extension${selectedIds.size > 1 ? "s" : ""} to project`, "success");
      setSelectedIds(new Set());
      setSearch("");
      onOpenChange(false);
    } catch {
      showToast("Failed to add extensions", "error");
    }
  };

  const handleOpenChange = (open: boolean) => {
    if (!open) {
      setSelectedIds(new Set());
      setSearch("");
    }
    onOpenChange(open);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Add Extensions</DialogTitle>
          <DialogDescription>
            Select extensions to add to this project. Only unlinked extensions are shown.
          </DialogDescription>
        </DialogHeader>

        {/* Search */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-400" />
          <Input
            placeholder="Search extensions..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>

        {/* Select all toggle */}
        {available.length > 0 && (
          <div className="flex items-center justify-between text-xs text-zinc-400">
            <button type="button" onClick={toggleAll} className="hover:text-white transition-colors">
              {selectedIds.size === available.length ? "Deselect all" : "Select all"}
            </button>
            <span>{selectedIds.size} selected</span>
          </div>
        )}

        {/* Extension list grouped by type */}
        <div className="max-h-[360px] overflow-y-auto space-y-4 pr-1">
          {isLoadingExtensions && <p className="text-sm text-zinc-500 text-center py-8">Loading extensions...</p>}
          {isExtensionsError && <p className="text-sm text-red-400 text-center py-8">Failed to load extensions.</p>}
          {!isLoadingExtensions && !isExtensionsError && available.length === 0 && (
            <p className="text-sm text-zinc-500 text-center py-8">
              {search ? "No extensions match your search." : "All extensions are already linked to this project."}
            </p>
          )}

          {!isLoadingExtensions &&
            !isExtensionsError &&
            TYPE_ORDER.filter((t) => grouped[t]?.length).map((type) => (
              <div key={type}>
                <h4 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">
                  {TYPE_LABELS[type] ?? type}
                </h4>
                <div className="space-y-1">
                  {grouped[type].map((ext) => (
                    <button
                      key={ext.id}
                      type="button"
                      onClick={() => toggleSelected(ext.id)}
                      className={`w-full flex items-start gap-3 p-2.5 rounded-lg border text-left transition-colors ${
                        selectedIds.has(ext.id)
                          ? "border-cyan-500/50 bg-cyan-500/10"
                          : "border-white/5 bg-white/[0.02] hover:border-white/10 hover:bg-white/[0.04]"
                      }`}
                    >
                      <div
                        className={`mt-0.5 flex-shrink-0 w-4 h-4 rounded border flex items-center justify-center ${
                          selectedIds.has(ext.id) ? "bg-cyan-500 border-cyan-500" : "border-zinc-600"
                        }`}
                      >
                        {selectedIds.has(ext.id) && (
                          <svg
                            className="w-2.5 h-2.5 text-black"
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                            strokeWidth={3}
                            aria-label="Selected"
                            role="img"
                          >
                            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                          </svg>
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-white truncate">
                            {ext.display_name || ext.name}
                          </span>
                          <span
                            className={`flex-shrink-0 px-1.5 py-0.5 text-[10px] rounded border ${
                              TYPE_COLORS[ext.type] ?? "bg-zinc-500/20 text-zinc-400 border-zinc-500/30"
                            }`}
                          >
                            {ext.type}
                          </span>
                        </div>
                        {ext.description && <p className="text-xs text-zinc-400 mt-0.5 truncate">{ext.description}</p>}
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            ))}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 pt-2 border-t border-white/10">
          <Button variant="outline" onClick={() => handleOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleAdd} disabled={selectedIds.size === 0 || linkExtensions.isPending}>
            <Plus className="w-4 h-4 mr-1.5" />
            {linkExtensions.isPending
              ? "Adding..."
              : `Add ${selectedIds.size > 0 ? `${selectedIds.size} ` : ""}Extension${selectedIds.size !== 1 ? "s" : ""}`}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
