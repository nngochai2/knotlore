import * as React from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@/api/http";
import { deleteInstance, getInstance, renameInstance } from "@/api/instances";
import { listJobs, type Job } from "@/api/jobs";
import { listConfigs } from "@/api/configs";
import { configTitle, sinkLabel, sourceLabel } from "@/lib/registry";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useConfirm } from "@/components/confirm-dialog";
import { StatusBadge } from "@/components/status-badge";
import { toast } from "@/hooks/use-toast";

const JOB_HISTORY_LIMIT = 50;

function jobDetail(job: Job): string {
  if (job.status === "failed") return job.error ?? "Failed";
  if (job.status === "pending" || job.status === "running") return "In progress";
  if (job.status === "cancelled") return "Cancelled";
  const counts = new Map<string, number>();
  for (const doc of job.doc_statuses) counts.set(doc.outcome, (counts.get(doc.outcome) ?? 0) + 1);
  if (counts.size === 0) return "No changes";
  return [...counts.entries()].map(([outcome, n]) => `${n} ${outcome}`).join(", ");
}

export function InstanceDetail() {
  const { id } = useParams<{ id: string }>();
  const instanceId = id!;
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const confirm = useConfirm();

  const [renameOpen, setRenameOpen] = React.useState(false);
  const [renameValue, setRenameValue] = React.useState("");

  const instanceQuery = useQuery({
    queryKey: ["instance", instanceId],
    queryFn: () => getInstance(instanceId),
    // A 404 won't fix itself — show "doesn't exist" now instead of after retries.
    retry: (failureCount, error) => !(error instanceof ApiError && error.status === 404) && failureCount < 3,
  });
  const jobsQuery = useQuery({
    queryKey: ["jobs", "forInstance", instanceId],
    queryFn: () => listJobs({ instanceId, limit: JOB_HISTORY_LIMIT }),
  });
  const configsQuery = useQuery({ queryKey: ["configs"], queryFn: listConfigs });

  const instance = instanceQuery.data;

  const renameMutation = useMutation({
    mutationFn: (name: string) => renameInstance(instanceId, name),
    onSuccess: () => {
      setRenameOpen(false);
      queryClient.invalidateQueries({ queryKey: ["instance", instanceId] });
      queryClient.invalidateQueries({ queryKey: ["instances"] });
      toast({ title: "Instance renamed" });
    },
    onError: () => toast({ variant: "destructive", title: "Rename failed" }),
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteInstance(instanceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["instances"] });
      toast({ title: "Instance deleted" });
      navigate("/instances");
    },
    onError: () => toast({ variant: "destructive", title: "Delete failed" }),
  });

  const handleDelete = async () => {
    const confirmed = await confirm({
      title: "Delete this instance?",
      description:
        "This removes the instance and its job history only — graph/vector data already written by its runs is left exactly as-is (ADR-0025).",
      confirmLabel: "Delete instance",
    });
    if (confirmed) deleteMutation.mutate();
  };

  const submitRename = () => {
    const name = renameValue.trim();
    if (name !== "" && !renameMutation.isPending) renameMutation.mutate(name);
  };

  if (instanceQuery.isPending) return <p className="text-sm text-[var(--ink-faint)]">Loading instance…</p>;
  if (!instance) {
    const notFound = instanceQuery.error instanceof ApiError && instanceQuery.error.status === 404;
    return (
      <div className="pb-10">
        <Link to="/instances" className="mb-3.5 inline-block text-[12.5px] text-[var(--accent)]">
          ← All instances
        </Link>
        <p className="text-sm text-[var(--ink-muted)]">
          {notFound ? "This instance doesn't exist — it may have been deleted." : "Couldn't load this instance."}
        </p>
        {!notFound && (
          <Button variant="outline" className="mt-3" onClick={() => instanceQuery.refetch()}>
            Retry
          </Button>
        )}
      </div>
    );
  }

  return (
    <div className="pb-10">
      <Link to="/instances" className="mb-3.5 inline-block text-[12.5px] text-[var(--accent)]">
        ← All instances
      </Link>

      <div className="mb-4 flex items-start justify-between">
        <div>
          <h1 className="mb-1 text-lg font-semibold text-[var(--ink)]">{instance.name}</h1>
          <div className="text-xs text-[var(--ink-muted)]">
            {sourceLabel(instance.source_type)} <span className="font-mono">{instance.source_path}</span> ·{" "}
            {sinkLabel(instance.sinks)} ·{" "}
            <span className="font-mono">{configTitle(configsQuery.data?.configs ?? [], instance.last_config_id)}</span>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => navigate(`/ingest?instance_id=${instance.id}`)}>
            Run again
          </Button>
          <Button
            variant="outline"
            onClick={() => {
              setRenameValue(instance.name);
              setRenameOpen(true);
            }}
          >
            Rename
          </Button>
          <Button
            variant="outline"
            className="border-[var(--fail)] text-[var(--fail)] hover:bg-[var(--fail-soft)]"
            onClick={handleDelete}
          >
            Delete
          </Button>
        </div>
      </div>

      <div className="mt-6">
        <h2 className="mb-2.5 text-xs font-semibold uppercase tracking-wide text-[var(--ink-faint)]">
          Job history ({instance.job_count})
        </h2>
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-[var(--border)] text-[var(--ink-faint)]">
              <th className="py-1 font-medium">Job</th>
              <th className="py-1 font-medium">Started</th>
              <th className="py-1 font-medium">Status</th>
              <th className="py-1 font-medium">Detail</th>
            </tr>
          </thead>
          <tbody>
            {jobsQuery.data?.jobs.map((job) => (
              <tr key={job.id} className="border-b border-[var(--border)] align-top">
                <td className="py-1.5 font-mono text-xs">{job.id.slice(0, 8)}</td>
                <td className="py-1.5">{new Date(job.created_at).toLocaleString()}</td>
                <td className="py-1.5">
                  <StatusBadge status={job.status} />
                </td>
                <td className="py-1.5 text-[var(--ink-muted)]">{jobDetail(job)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {jobsQuery.isError && (
          <p className="mt-3 text-sm text-[var(--fail)]">Couldn't load this instance's job history.</p>
        )}
        {jobsQuery.data?.jobs.length === 0 && (
          <p className="mt-3 text-sm text-[var(--ink-faint)]">No runs yet.</p>
        )}
        {jobsQuery.data && jobsQuery.data.total > jobsQuery.data.jobs.length && (
          <p className="mt-3 text-xs text-[var(--ink-faint)]">
            Showing the {JOB_HISTORY_LIMIT} most recent of {jobsQuery.data.total} runs.
          </p>
        )}
      </div>

      <Dialog open={renameOpen} onOpenChange={setRenameOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rename instance</DialogTitle>
          </DialogHeader>
          <form
            id="rename-instance"
            onSubmit={(e) => {
              e.preventDefault();
              submitRename();
            }}
          >
            <Input autoFocus value={renameValue} onChange={(e) => setRenameValue(e.target.value)} />
          </form>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRenameOpen(false)}>
              Cancel
            </Button>
            <Button
              type="submit"
              form="rename-instance"
              disabled={renameValue.trim() === "" || renameMutation.isPending}
            >
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
