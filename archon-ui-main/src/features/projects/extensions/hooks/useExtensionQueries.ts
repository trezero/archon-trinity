import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { DISABLED_QUERY_KEY, STALE_TIMES } from "@/features/shared/config/queryPatterns";
import { extensionService } from "../services/extensionService";

export const extensionKeys = {
  all: ["extensions"] as const,
  lists: () => [...extensionKeys.all, "list"] as const,
  byProject: (projectId: string) => ["projects", projectId, "extensions"] as const,
  projectSystems: (projectId: string) => ["projects", projectId, "systems"] as const,
};

export function useProjectExtensions(projectId: string | undefined) {
  return useQuery({
    queryKey: projectId ? extensionKeys.byProject(projectId) : DISABLED_QUERY_KEY,
    queryFn: () => (projectId ? extensionService.getProjectExtensions(projectId) : Promise.reject("No project ID")),
    enabled: !!projectId,
    staleTime: STALE_TIMES.normal,
  });
}

export function useProjectSystems(projectId: string | undefined) {
  return useQuery({
    queryKey: projectId ? extensionKeys.projectSystems(projectId) : DISABLED_QUERY_KEY,
    queryFn: () => (projectId ? extensionService.getProjectSystems(projectId) : Promise.reject("No project ID")),
    enabled: !!projectId,
    staleTime: STALE_TIMES.normal,
  });
}

export function useAllExtensions() {
  return useQuery({
    queryKey: extensionKeys.lists(),
    queryFn: () => extensionService.getAllExtensions(),
    staleTime: STALE_TIMES.normal,
  });
}

export function useInstallExtension() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      projectId,
      extensionId,
      systemIds,
    }: {
      projectId: string;
      extensionId: string;
      systemIds: string[];
    }) => extensionService.installExtension(projectId, extensionId, systemIds),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: extensionKeys.byProject(variables.projectId) });
    },
  });
}

export function useRemoveExtension() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      projectId,
      extensionId,
      systemIds,
    }: {
      projectId: string;
      extensionId: string;
      systemIds: string[];
    }) => extensionService.removeExtension(projectId, extensionId, systemIds),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: extensionKeys.byProject(variables.projectId) });
    },
  });
}

export function useUnlinkSystem() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ projectId, systemId }: { projectId: string; systemId: string }) =>
      extensionService.unlinkSystem(projectId, systemId),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: extensionKeys.projectSystems(variables.projectId) });
      queryClient.invalidateQueries({ queryKey: extensionKeys.byProject(variables.projectId) });
    },
  });
}

export function useLinkExtensions() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ projectId, extensionIds }: { projectId: string; extensionIds: string[] }) =>
      Promise.all(extensionIds.map((id) => extensionService.linkExtension(projectId, id))),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: extensionKeys.byProject(variables.projectId) });
    },
  });
}

export function useUnlinkExtension() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ projectId, extensionId }: { projectId: string; extensionId: string }) =>
      extensionService.unlinkExtension(projectId, extensionId),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: extensionKeys.byProject(variables.projectId) });
    },
  });
}

export function useSetExtensionDefault() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ extensionId, isDefault }: { extensionId: string; isDefault: boolean }) =>
      extensionService.setExtensionDefault(extensionId, isDefault),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: extensionKeys.lists() });
    },
  });
}
