import type { JobStatus } from "@/api/jobs";
import { STATUS_STYLES } from "@/lib/job-status";
import { cn } from "@/lib/utils";

/** A job status pill, shared by the Instances list (last run's status) and
 * an instance's job-history table. */
export function StatusBadge({ status }: { status: JobStatus }) {
  return (
    <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-semibold", STATUS_STYLES[status])}>{status}</span>
  );
}
