import { Fragment, useState } from "react";
import { CalendarClock, ChevronDown, ChevronRight, Clock, Server } from "lucide-react";
import RunCollectionButton from "../components/RunCollectionButton";
import { Alert, Badge, Card, EmptyState, ErrorState, PageHeader, Skeleton, StatCard, StatusBadge } from "../components/ui";
import { api } from "../lib/api";
import { duration, formatDate } from "../lib/format";
import { useAsync } from "../lib/hooks";
import type { CollectionRun, CollectionStatus } from "../lib/types";

export default function AutomationPage() {
  const status = useAsync(() => api<CollectionStatus>("/collection/status"), []);
  const runs = useAsync(() => api<CollectionRun[]>("/collection/runs", { query: { limit: 50 } }), []);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [notice, setNotice] = useState<{ kind: "success" | "warning" | "error"; text: string } | null>(null);

  const s = status.data;

  return (
    <>
      <PageHeader
        title="Automation"
        description="Scheduled and manual data collection runs."
        actions={
          <RunCollectionButton
            onStarted={() => {
              setNotice(null);
              runs.reload();
            }}
            onDone={(run) => {
              setNotice({ kind: run.status === "success" ? "success" : run.status === "partial" ? "warning" : "error", text: `Run #${run.id} ${run.status}: ${run.items_new} new items, ${run.items_duplicate} duplicates skipped, ${run.error_count} errors.` });
              runs.reload();
              status.reload();
            }}
            onError={(msg) => setNotice({ kind: "error", text: msg })}
          />
        }
      />
      {notice && <div className="mb-4"><Alert kind={notice.kind}>{notice.text}</Alert></div>}
      {s?.demo_mode && <div className="mb-4"><Alert kind="warning">Demo mode is on: collectors serve a bundled sample dataset about fictional companies instead of live sources.</Alert></div>}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Scheduler" value={s ? (s.scheduler_enabled ? "In API process" : "Collector service") : "…"} icon={<Server className="h-4 w-4" />} hint={s && !s.scheduler_enabled ? "Scheduled by the separate collector worker" : "APScheduler inside the API server"} />
        <StatCard label="Interval" value={s ? `Every ${s.interval_minutes} min` : "…"} icon={<Clock className="h-4 w-4" />} />
        <StatCard label="Next scheduled run" value={s?.next_run_at ? (new Date(s.next_run_at) <= new Date() ? "Due now" : formatDate(s.next_run_at, true)) : "After first run"} icon={<CalendarClock className="h-4 w-4" />} />
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-sm font-medium text-slate-500">Active collectors</p>
          <div className="mt-3 flex flex-wrap gap-1.5">{s?.collectors.map((c) => <Badge key={c} color="indigo">{c}</Badge>)}</div>
        </div>
      </div>

      <Card title="Collection runs" className="mt-6">
        {runs.loading && !runs.data ? (
          <div className="space-y-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-10" />)}</div>
        ) : runs.error ? (
          <ErrorState message={runs.error} onRetry={runs.reload} />
        ) : !runs.data?.length ? (
          <EmptyState title="No runs yet" description="Runs appear here when the scheduler fires or you click “Run collection now”." />
        ) : (
          <div className="-mx-5 overflow-x-auto">
            <table className="w-full min-w-[720px] text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
                  <th className="px-5 py-2.5" />
                  <th className="py-2.5">Run</th>
                  <th className="py-2.5">Status</th>
                  <th className="py-2.5">Started</th>
                  <th className="py-2.5">Duration</th>
                  <th className="py-2.5 text-right">Fetched</th>
                  <th className="py-2.5 text-right">New</th>
                  <th className="py-2.5 text-right">Duplicates</th>
                  <th className="px-5 py-2.5 text-right">Errors</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {runs.data.map((r) => (
                  <Fragment key={r.id}>
                    <tr className="cursor-pointer hover:bg-slate-50" onClick={() => setExpanded(expanded === r.id ? null : r.id)}>
                      <td className="px-5 py-3 text-slate-400">{expanded === r.id ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}</td>
                      <td className="py-3"><span className="font-medium">#{r.id}</span> <Badge color={r.trigger === "manual" ? "blue" : "slate"}>{r.trigger}</Badge></td>
                      <td className="py-3"><StatusBadge status={r.status} /></td>
                      <td className="py-3 text-slate-600">{formatDate(r.started_at, true)}</td>
                      <td className="py-3 text-slate-600">{duration(r.started_at, r.finished_at)}</td>
                      <td className="py-3 text-right tabular-nums">{r.items_fetched}</td>
                      <td className="py-3 text-right font-medium tabular-nums text-emerald-700">{r.items_new}</td>
                      <td className="py-3 text-right tabular-nums text-slate-500">{r.items_duplicate}</td>
                      <td className="px-5 py-3 text-right tabular-nums">{r.error_count ? <span className="text-rose-600">{r.error_count}</span> : 0}</td>
                    </tr>
                    {expanded === r.id && (
                      <tr className="bg-slate-50/70">
                        <td colSpan={9} className="px-5 py-4">
                          <div className="grid gap-6 md:grid-cols-2">
                            <div>
                              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Per source</p>
                              {r.details.sources && Object.keys(r.details.sources).length ? (
                                <table className="w-full text-xs">
                                  <thead><tr className="text-left text-slate-500"><th>Source</th><th className="text-right">Fetched</th><th className="text-right">New</th><th className="text-right">Dup</th><th className="text-right">Invalid</th><th className="text-right">Errors</th></tr></thead>
                                  <tbody>
                                    {Object.entries(r.details.sources).map(([k, v]) => (
                                      <tr key={k}><td className="py-1 font-medium">{k}</td><td className="text-right">{v.fetched}</td><td className="text-right">{v.new}</td><td className="text-right">{v.duplicate}</td><td className="text-right">{v.invalid}</td><td className="text-right">{v.errors}</td></tr>
                                    ))}
                                  </tbody>
                                </table>
                              ) : (
                                <p className="text-xs text-slate-500">{r.details.note ?? (r.status === "running" ? "Run in progress…" : "No source activity.")}</p>
                              )}
                              <p className="mt-2 text-xs text-slate-500">{r.companies_processed} companies processed · {r.items_invalid} invalid items dropped</p>
                            </div>
                            <div>
                              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Errors</p>
                              {r.details.errors?.length ? (
                                <ul className="space-y-1.5 text-xs">
                                  {r.details.errors.map((e, i) => (
                                    <li key={i} className="rounded border border-rose-100 bg-white px-2 py-1.5 text-rose-700">
                                      {e.company && <span className="font-medium">{e.company} · {e.source}: </span>}{e.error}
                                    </li>
                                  ))}
                                </ul>
                              ) : (
                                <p className="text-xs text-slate-500">No errors.</p>
                              )}
                              {!!r.details.skipped?.length && (
                                <p className="mt-2 text-xs text-amber-700">
                                  {r.details.skipped.length} fetches skipped after a provider rate limit ({[...new Set(r.details.skipped.map((s) => s.source))].join(", ")}); they will be retried next run.
                                </p>
                              )}
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
