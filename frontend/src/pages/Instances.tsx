import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { listInstances } from "@/api/instances";
import { listConfigs } from "@/api/configs";
import { configTitle, sinkLabel, sourceLabel } from "@/lib/registry";
import { StatusBadge } from "@/components/status-badge";

export function Instances() {
  const navigate = useNavigate();
  const instancesQuery = useQuery({ queryKey: ["instances"], queryFn: listInstances });
  const configsQuery = useQuery({ queryKey: ["configs"], queryFn: listConfigs });

  const instances = instancesQuery.data?.instances ?? [];
  const configs = configsQuery.data?.configs ?? [];

  return (
    <div className="pb-10">
      <div className="mb-3 flex items-center justify-between">
        <h1 className="text-lg font-semibold text-[var(--ink)]">Instances</h1>
      </div>

      <div className="flex flex-col gap-2.5">
        {instances.length === 0 && instancesQuery.isSuccess && (
          <p className="text-sm text-[var(--ink-faint)]">
            No instances yet — start one from the Ingest page.
          </p>
        )}
        {instances.map((instance) => (
          <div
            key={instance.id}
            role="link"
            tabIndex={0}
            onClick={() => navigate(`/instances/${instance.id}`)}
            onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && navigate(`/instances/${instance.id}`)}
            className="grid cursor-pointer grid-cols-[1.4fr_1fr_1fr_1fr_auto] items-center gap-3.5 rounded-lg border border-[var(--border)] px-4.5 py-3.5 transition-colors hover:border-[var(--accent)]"
          >
            <div className="text-sm font-bold">{instance.name}</div>
            <div className="text-xs text-[var(--ink-muted)]">
              {sourceLabel(instance.source_type)}
              <br />
              <span className="text-[var(--ink-faint)]">{instance.source_path}</span>
            </div>
            <div className="text-xs text-[var(--ink-muted)]">
              {sinkLabel(instance.sinks)}
              <br />
              <span className="text-[var(--ink-faint)]">{configTitle(configs, instance.last_config_id)}</span>
            </div>
            <div className="text-xs text-[var(--ink-muted)]">
              {instance.job_count} run{instance.job_count === 1 ? "" : "s"}
            </div>
            <div className="text-right text-xs text-[var(--ink-muted)]">
              {instance.last_status && <StatusBadge status={instance.last_status} />}
              <br />
              {instance.last_run_at ? new Date(instance.last_run_at).toLocaleString() : "—"}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
