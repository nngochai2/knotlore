/** Source/sink display labels, shared by Ingest and Instances — mirrors
 * the backend's registered source_types (app/pipeline/registry.py's
 * SOURCES) and sink_types (SINKS, minus the test-only "dryrun"). Only
 * "neo4j" is wired to a real sink adapter today; a "vector" option isn't
 * listed until the vector-sink ticket registers "chroma" there. */
export const SOURCE_TYPES: { value: string; label: string; pathPlaceholder: string }[] = [
  { value: "obsidian", label: "Obsidian vault", pathPlaceholder: "/path/to/vault" },
  { value: "docx", label: "Documents folder", pathPlaceholder: "/path/to/folder" },
  {
    value: "azure_devops",
    label: "Azure DevOps project",
    pathPlaceholder: "https://server/collection/project  (or fixture:/path/to/fixtures)",
  },
];
export const SINK_OPTIONS: { value: string; label: string }[] = [{ value: "neo4j", label: "Knowledge graph (Neo4j)" }];

export function sourceLabel(sourceType: string): string {
  return SOURCE_TYPES.find((s) => s.value === sourceType)?.label ?? sourceType;
}

export function sourcePathPlaceholder(sourceType: string): string {
  return SOURCE_TYPES.find((s) => s.value === sourceType)?.pathPlaceholder ?? "/path/to/vault-or-folder";
}

export function sinkLabel(sinks: string[]): string {
  return sinks.map((s) => SINK_OPTIONS.find((o) => o.value === s)?.label ?? s).join(", ") || "—";
}

/** Resolves an instance's "config in use" (spec §9) — the config_id of its
 * most recent job — to that config's title. `configId` is `null` for an
 * instance with no runs yet. */
export function configTitle(configs: { id: string; title: string }[], configId: string | null): string {
  if (!configId) return "No runs yet";
  return configs.find((c) => c.id === configId)?.title ?? configId;
}
