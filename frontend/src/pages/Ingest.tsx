import * as React from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@/api/http";
import { createInstance, listInstances, type Instance } from "@/api/instances";
import { cancelJob, createJob, getJob, type DocOutcome, type Job } from "@/api/jobs";
import { listConfigs } from "@/api/configs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useConfirm } from "@/components/confirm-dialog";
import { toast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import { configTitle, SINK_OPTIONS, sinkLabel, SOURCE_TYPES, sourceLabel, sourcePathPlaceholder } from "@/lib/registry";

const STEPS = ["Source", "Destination", "Path & config", "Review & run"] as const;
const NEW_INSTANCE = "__new__";

const TERMINAL_STATUSES = new Set(["completed", "failed", "cancelled"]);

const OUTCOME_STYLES: Record<DocOutcome, string> = {
  updated: "bg-[var(--ok-soft)] text-[var(--ok)]",
  skipped: "bg-[var(--surface-2)] text-[var(--ink-muted)]",
  removed: "bg-[var(--surface-2)] text-[var(--ink-muted)]",
  failed: "bg-[var(--fail-soft)] text-[var(--fail)]",
};

interface Draft {
  name: string;
  sourceType: string;
  sourcePath: string;
  sinks: string[];
}

/** A step-1/2 pick, styled like the validated prototype's vB-opt cards
 * (prototype/loom-ui-flow, variant B "Guided Wizard"). */
function OptionCard({
  label,
  chosen,
  disabled,
  onClick,
}: {
  label: string;
  chosen: boolean;
  disabled?: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "rounded-lg border px-4 py-2.5 text-left text-sm transition-colors disabled:cursor-default",
        chosen
          ? "border-[var(--accent)] bg-[var(--accent-soft)] font-semibold text-[var(--accent-ink)]"
          : "border-[var(--border)] text-[var(--ink)] enabled:hover:border-[var(--accent)]",
      )}
    >
      {label}
    </button>
  );
}

export function Ingest() {
  const [searchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const confirm = useConfirm();

  // "Run again" from an instance's detail page (ADR-0026) links here with
  // ?instance_id= — everything else about that instance (source/path/sinks,
  // its last config) comes from the same existing-instance pre-fill below,
  // not duplicated into its own set of query params.
  const prefilledInstanceId = searchParams.get("instance_id");
  const [wizardStep, setWizardStep] = React.useState(1);
  const [mode, setMode] = React.useState<"existing" | "new">(prefilledInstanceId ? "existing" : "new");
  const isExisting = mode === "existing";
  const [selectedInstanceId, setSelectedInstanceId] = React.useState<string>(prefilledInstanceId ?? "");
  const [draft, setDraft] = React.useState<Draft>({
    name: "",
    sourceType: searchParams.get("source_type") ?? "",
    sourcePath: searchParams.get("source_path") ?? "",
    sinks: searchParams.get("sinks")?.split(",").filter(Boolean) ?? [],
  });
  const [configId, setConfigId] = React.useState("");
  const [jobId, setJobId] = React.useState<string | null>(null);

  const instancesQuery = useQuery({ queryKey: ["instances"], queryFn: listInstances });
  const configsQuery = useQuery({ queryKey: ["configs"], queryFn: listConfigs });

  const selectedInstance: Instance | undefined = instancesQuery.data?.instances.find(
    (i) => i.id === selectedInstanceId,
  );

  function pickInstance(value: string) {
    setWizardStep(1);
    if (value === NEW_INSTANCE) {
      setMode("new");
      setSelectedInstanceId("");
    } else {
      setMode("existing");
      setSelectedInstanceId(value);
    }
  }

  // An existing instance's source/path/sinks (its identity, ADR-0025) are
  // locked once chosen; its config is deliberately left editable — ADR-0025
  // keeps config out of instance identity precisely so a re-run can use a
  // different one. `last_config_id` (the instance's most recent job's
  // config) just seeds the field with that value, same as source/path/sinks.
  // Seeding happens once per selection, not on every refetch of the
  // instances list: a run elsewhere changes that instance's last_* fields,
  // and re-seeding then would silently discard a config the user just picked.
  const seededInstanceId = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (!isExisting) {
      seededInstanceId.current = null;
      return;
    }
    if (!selectedInstance || seededInstanceId.current === selectedInstance.id) return;
    seededInstanceId.current = selectedInstance.id;
    setDraft((prev) => ({
      ...prev,
      sourceType: selectedInstance.source_type,
      sourcePath: selectedInstance.source_path,
      sinks: selectedInstance.sinks,
    }));
    setConfigId(selectedInstance.last_config_id ?? "");
  }, [isExisting, selectedInstance]);

  const jobQuery = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => getJob(jobId!),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const job = query.state.data as Job | undefined;
      return job && TERMINAL_STATUSES.has(job.status) ? false : 1000;
    },
  });
  const job = jobQuery.data;

  // Toast once per job the moment polling observes it land in a terminal,
  // unsuccessful state — the inline banner below covers the same case for
  // anyone still looking at the page, this covers the "walked away" case
  // ADR-0016 has in mind for "job failed" feedback.
  const lastToastedStatus = React.useRef<Job["status"] | undefined>(undefined);
  React.useEffect(() => {
    if (!job || job.status === lastToastedStatus.current) return;
    lastToastedStatus.current = job.status;
    if (job.status === "failed") {
      toast({ variant: "destructive", title: "Job failed", description: job.error ?? undefined });
    } else if (job.status === "cancelled") {
      toast({ title: "Job cancelled" });
    }
  }, [job]);

  const runMutation = useMutation({
    mutationFn: async () => {
      const instanceId = isExisting
        ? selectedInstanceId
        : (
            await createInstance({
              name: draft.name.trim() || undefined,
              source_type: draft.sourceType,
              source_path: draft.sourcePath,
              sinks: draft.sinks,
            })
          ).instance_id;
      return createJob({ instance_id: instanceId, config_id: configId });
    },
    onSuccess: (data) => {
      setJobId(data.job_id);
      queryClient.invalidateQueries({ queryKey: ["instances"] });
    },
    onError: (error: unknown) => {
      const message =
        error instanceof ApiError && error.status === 409
          ? "An instance with this source and sink(s) already exists."
          : "Failed to start the job.";
      toast({ variant: "destructive", title: "Run failed", description: message });
    },
  });

  const cancelMutation = useMutation({
    mutationFn: () => cancelJob(jobId!),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["job", jobId] }),
    onError: (error: unknown) => {
      const message =
        error instanceof ApiError && error.status === 409
          ? "That job already finished."
          : "Failed to cancel the job.";
      toast({ variant: "destructive", title: "Cancel failed", description: message });
    },
  });

  const availableConfigs = (configsQuery.data?.configs ?? []).filter((c) => c.source_type === draft.sourceType);
  const identityLocked = isExisting;

  const stepValid = [
    draft.sourceType !== "",
    draft.sinks.length > 0,
    draft.sourcePath.trim() !== "" && configId !== "",
    true,
  ];
  const canRun =
    stepValid[0] && stepValid[1] && stepValid[2] && (!isExisting || selectedInstanceId !== "") && !runMutation.isPending;

  const handleCancel = async () => {
    const confirmed = await confirm({
      title: "Cancel this job?",
      description: "The job will stop at its next document boundary.",
      confirmLabel: "Cancel job",
    });
    if (confirmed) cancelMutation.mutate();
  };

  const instanceChipLabel = isExisting ? selectedInstance?.name ?? "…" : "New instance";

  return (
    <div className="pb-10">
      <h1 className="mb-4 text-lg font-semibold text-[var(--ink)]">Ingest</h1>

      <div className="overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface)]">
        <div className="grid min-h-[420px] grid-cols-[210px_1fr]">
          <div className="border-r border-[var(--border)] py-5">
            {STEPS.map((label, i) => {
              const n = i + 1;
              const done = n < wizardStep;
              const current = n === wizardStep;
              return (
                <div
                  key={label}
                  className={cn(
                    "flex items-start gap-2.5 px-5 py-3 text-sm",
                    current ? "font-bold text-[var(--ink)]" : "text-[var(--ink-faint)]",
                  )}
                >
                  <div
                    className={cn(
                      "flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2 text-[11px]",
                      done && "border-[var(--ok)] bg-[var(--ok)] text-white",
                      current && !done && "border-[var(--accent)] text-[var(--accent)]",
                      !done && !current && "border-[var(--border)]",
                    )}
                  >
                    {done ? "✓" : n}
                  </div>
                  {label}
                </div>
              );
            })}
          </div>

          <div className="p-7">
            <Select value={isExisting ? selectedInstanceId : NEW_INSTANCE} onValueChange={pickInstance}>
              <SelectTrigger className="mb-4 h-auto w-fit gap-1.5 rounded-full border-0 bg-[var(--accent-soft)] px-3 py-1.5 text-xs font-semibold text-[var(--accent-ink)]">
                <span>Instance: {instanceChipLabel}</span>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NEW_INSTANCE}>+ New instance</SelectItem>
                {instancesQuery.data?.instances.map((instance) => (
                  <SelectItem key={instance.id} value={instance.id}>
                    {instance.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            {wizardStep === 1 && (
              <div>
                <h2 className="mb-4 text-base font-semibold">Step 1 — Source</h2>
                <div className="flex gap-2.5">
                  {SOURCE_TYPES.map((s) => (
                    <OptionCard
                      key={s.value}
                      label={s.label}
                      chosen={draft.sourceType === s.value}
                      disabled={identityLocked}
                      onClick={() => setDraft((prev) => ({ ...prev, sourceType: s.value }))}
                    />
                  ))}
                </div>
              </div>
            )}

            {wizardStep === 2 && (
              <div>
                <h2 className="mb-4 text-base font-semibold">Step 2 — Destination</h2>
                <div className="flex gap-2.5">
                  {SINK_OPTIONS.map((sink) => (
                    <OptionCard
                      key={sink.value}
                      label={sink.label}
                      chosen={draft.sinks.includes(sink.value)}
                      disabled={identityLocked}
                      onClick={() =>
                        setDraft((prev) => ({
                          ...prev,
                          sinks: prev.sinks.includes(sink.value)
                            ? prev.sinks.filter((s) => s !== sink.value)
                            : [...prev.sinks, sink.value],
                        }))
                      }
                    />
                  ))}
                </div>
              </div>
            )}

            {wizardStep === 3 && (
              <div className="max-w-md space-y-4">
                <h2 className="text-base font-semibold">Step 3 — Path & config</h2>
                {!isExisting && (
                  <div>
                    <Label htmlFor="instance-name">Name (optional)</Label>
                    <Input
                      id="instance-name"
                      value={draft.name}
                      onChange={(e) => setDraft((prev) => ({ ...prev, name: e.target.value }))}
                      placeholder="Auto-named from the path if left blank"
                    />
                  </div>
                )}
                <div>
                  <Label htmlFor="source-path">Path</Label>
                  <Input
                    id="source-path"
                    value={draft.sourcePath}
                    onChange={(e) => setDraft((prev) => ({ ...prev, sourcePath: e.target.value }))}
                    disabled={identityLocked}
                    placeholder={sourcePathPlaceholder(draft.sourceType)}
                  />
                </div>
                <div>
                  <Label htmlFor="config">Config</Label>
                  <Select value={configId} onValueChange={setConfigId} disabled={draft.sourceType === ""}>
                    <SelectTrigger id="config">
                      <SelectValue placeholder="Choose a rule config…" />
                    </SelectTrigger>
                    <SelectContent>
                      {availableConfigs.map((c) => (
                        <SelectItem key={c.id} value={c.id}>
                          {c.title}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            )}

            {wizardStep === 4 && (
              <div className="max-w-md">
                <h2 className="mb-4 text-base font-semibold">Step 4 — Review & run</h2>
                {[
                  ["Instance", instanceChipLabel],
                  ["Source", sourceLabel(draft.sourceType)],
                  ["Destination", sinkLabel(draft.sinks)],
                  ["Path", draft.sourcePath || "—"],
                  ["Config", configTitle(availableConfigs, configId)],
                ].map(([label, value]) => (
                  <div key={label} className="flex justify-between border-b border-[var(--border)] py-2 text-sm">
                    <span className="text-[var(--ink-faint)]">{label}</span>
                    <span className="font-mono text-[13px]">{value}</span>
                  </div>
                ))}
              </div>
            )}

            <div className="mt-7 flex gap-2.5">
              {wizardStep > 1 && (
                <Button variant="outline" onClick={() => setWizardStep((s) => s - 1)}>
                  Back
                </Button>
              )}
              {wizardStep < 4 ? (
                <Button onClick={() => setWizardStep((s) => s + 1)} disabled={!stepValid[wizardStep - 1]}>
                  Next
                </Button>
              ) : (
                <Button onClick={() => runMutation.mutate()} disabled={!canRun}>
                  {runMutation.isPending ? "Starting…" : "Run"}
                </Button>
              )}
            </div>
          </div>
        </div>
      </div>

      {job && (
        <section className="mt-6 rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium capitalize">{job.status}</span>
            {(job.status === "pending" || job.status === "running") && (
              <Button variant="outline" size="sm" onClick={handleCancel}>
                Cancel job
              </Button>
            )}
          </div>

          <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-[var(--surface-2)]">
            <div
              className="h-full bg-[var(--accent)] transition-all"
              style={{ width: `${Math.round(job.progress * 100)}%` }}
            />
          </div>

          {job.status === "failed" && job.error && (
            <p className="mt-3 rounded-md bg-[var(--fail-soft)] p-2 text-sm text-[var(--fail)]">{job.error}</p>
          )}

          {job.doc_statuses.length > 0 && (
            <table className="mt-4 w-full text-left text-sm">
              <thead>
                <tr className="border-b border-[var(--border)] text-[var(--ink-faint)]">
                  <th className="py-1 font-medium">Document</th>
                  <th className="py-1 font-medium">Outcome</th>
                  <th className="py-1 font-medium">Warning</th>
                </tr>
              </thead>
              <tbody>
                {job.doc_statuses.map((doc) => (
                  <tr key={doc.doc_id} className="border-b border-[var(--border)] align-top">
                    <td className="py-1.5">{doc.doc_id}</td>
                    <td className="py-1.5">
                      <span className={cn("rounded px-1.5 py-0.5 text-xs font-medium", OUTCOME_STYLES[doc.outcome])}>
                        {doc.outcome}
                      </span>
                    </td>
                    <td className="py-1.5">
                      {doc.warning && <span className="text-[var(--fail)]">{doc.warning}</span>}
                      {doc.error && (
                        <details>
                          <summary className="cursor-pointer text-[var(--fail)]">Error</summary>
                          <p className="mt-1 whitespace-pre-wrap text-[var(--ink-muted)]">{doc.error}</p>
                        </details>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {job.orphans.length > 0 && (
            <div className="mt-4">
              <h2 className="text-sm font-medium">Orphaned edges flagged</h2>
              <ul className="mt-1 space-y-1 text-sm text-[var(--ink-muted)]">
                {job.orphans.map((orphan) => (
                  <li key={orphan.edge_id}>
                    {orphan.edge_id} — {orphan.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
