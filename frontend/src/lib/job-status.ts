import type { JobStatus } from "@/api/jobs";

/** Shared pill styling for a job's status, used by the Instances list
 * (its last run's status) and an instance's job-history table. */
export const STATUS_STYLES: Record<JobStatus, string> = {
  completed: "bg-[var(--ok-soft)] text-[var(--ok)]",
  failed: "bg-[var(--fail-soft)] text-[var(--fail)]",
  cancelled: "bg-[var(--surface-2)] text-[var(--ink-muted)]",
  running: "bg-[var(--accent-soft)] text-[var(--accent-ink)]",
  pending: "bg-[var(--surface-2)] text-[var(--ink-muted)]",
};
