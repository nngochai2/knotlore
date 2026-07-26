import { NavLink } from "react-router-dom";
import { cn } from "@/lib/utils";

/** Persistent top nav shell (ADR-0013), amended to 4 tabs by ADR-0026.
 * Colors match the validated prototype's vB-nav (prototype/loom-ui-flow). */
const TABS = [
  { to: "/ingest", label: "Ingest" },
  { to: "/rules", label: "Rules" },
  { to: "/graph", label: "Graph" },
  { to: "/instances", label: "Instances" },
];

export function TopNav() {
  return (
    <header className="border-b border-[var(--border)] bg-[var(--surface)]">
      <div className="flex h-14 items-center gap-8 px-6">
        <span className="text-sm font-bold tracking-tight text-[var(--ink)]">Loom</span>
        <nav className="flex h-full gap-1">
          {TABS.map((tab) => (
            <NavLink
              key={tab.to}
              to={tab.to}
              className={({ isActive }) =>
                cn(
                  "flex items-center border-b-2 px-3 text-sm font-medium transition-colors",
                  isActive
                    ? "border-[var(--accent)] text-[var(--ink)] font-semibold"
                    : "border-transparent text-[var(--ink-muted)] hover:text-[var(--ink)]",
                )
              }
            >
              {tab.label}
            </NavLink>
          ))}
        </nav>
      </div>
    </header>
  );
}
