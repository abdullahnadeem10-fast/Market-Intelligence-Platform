import { useEffect, useState } from "react";
import { History, RefreshCw, Sparkles } from "lucide-react";
import AnalysisView from "../components/AnalysisView";
import { Alert, Badge, Button, Card, EmptyState, ErrorState, PageHeader, Skeleton, StatusBadge, cx } from "../components/ui";
import { api } from "../lib/api";
import { formatDate } from "../lib/format";
import { useAsync } from "../lib/hooks";
import type { Analysis, Company } from "../lib/types";

export default function AnalysisPage() {
  const [target, setTarget] = useState<string>("market");
  const [days, setDays] = useState(30);
  const [selected, setSelected] = useState<Analysis | null>(null);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  const companies = useAsync(() => api<Company[]>("/companies"), []);
  const historyPath = target === "market" ? "/analysis/market" : `/analysis/company/${target}`;
  const history = useAsync(() => api<Analysis[]>(historyPath, { query: { limit: 15 } }), [historyPath]);

  useEffect(() => {
    setSelected(null);
    setRunError(null);
  }, [target]);

  const shown = selected ?? history.data?.find((a) => a.status === "success") ?? null;

  async function run(force: boolean) {
    setRunning(true);
    setRunError(null);
    const path = target === "market" ? "/analysis/market" : `/analysis/company/${target}`;
    try {
      const a = await api<Analysis>(path, { method: "POST", body: { days, force } });
      setSelected(a);
      history.reload();
    } catch (e) {
      setRunError((e as Error).message);
      history.reload();
    } finally {
      setRunning(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Market Intelligence"
        description="AI analysis built only from the information you've collected. Every insight cites its sources."
      />
      <Card className="mb-6">
        <div className="flex flex-col gap-3 md:flex-row md:items-end">
          <label className="flex-1">
            <span className="mb-1.5 block text-sm font-medium text-slate-700">Scope</span>
            <select value={target} onChange={(e) => setTarget(e.target.value)} className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm">
              <option value="market">Entire market (all tracked companies)</option>
              {companies.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </label>
          <label>
            <span className="mb-1.5 block text-sm font-medium text-slate-700">Time window</span>
            <select value={days} onChange={(e) => setDays(Number(e.target.value))} className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm md:w-40">
              <option value={7}>Last 7 days</option>
              <option value={30}>Last 30 days</option>
              <option value={90}>Last 90 days</option>
            </select>
          </label>
          <div className="flex gap-2">
            <Button onClick={() => run(false)} loading={running}>{!running && <Sparkles className="h-4 w-4" />} Analyze market</Button>
            <Button variant="secondary" onClick={() => run(true)} disabled={running} title="Ignore cached result and call the model again">
              <RefreshCw className="h-4 w-4" /> Force refresh
            </Button>
          </div>
        </div>
        <p className="mt-3 text-xs text-slate-500">
          Identical requests (same sources) within the cache window reuse the stored analysis, so they cost no extra tokens.
        </p>
      </Card>

      {runError && <div className="mb-4"><Alert kind={runError.includes("No collected data") ? "info" : "error"}>{runError}</Alert></div>}

      <div className="grid gap-6 lg:grid-cols-4">
        <Card title="Analysis" className="lg:col-span-3">
          {running && <div className="mb-4"><Alert kind="info">Analyzing collected sources… this can take up to a minute with an LLM.</Alert></div>}
          {history.loading && !history.data ? (
            <div className="space-y-3"><Skeleton className="h-20" /><Skeleton className="h-48" /></div>
          ) : history.error ? (
            <ErrorState message={history.error} onRetry={history.reload} />
          ) : shown ? (
            <AnalysisView analysis={shown} />
          ) : (
            <EmptyState icon={<Sparkles className="h-6 w-6" />} title="No analysis yet" description="Choose a scope and click Analyze market." />
          )}
        </Card>
        <Card title={<span className="inline-flex items-center gap-2"><History className="h-4 w-4" /> History</span>}>
          {!history.data?.length ? (
            <p className="text-sm text-slate-400">No previous analyses.</p>
          ) : (
            <ul className="-mx-2 space-y-1">
              {history.data.map((a) => (
                <li key={a.id}>
                  <button
                    onClick={() => setSelected(a)}
                    className={cx("w-full rounded-lg px-2 py-2 text-left hover:bg-slate-50", shown?.id === a.id && "bg-indigo-50 hover:bg-indigo-50")}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-medium text-slate-700">{formatDate(a.created_at, true)}</span>
                      <StatusBadge status={a.status} />
                    </div>
                    <div className="mt-1 flex flex-wrap gap-1.5 text-xs text-slate-500">
                      <Badge>{a.provider === "extractive" ? "extractive" : a.model}</Badge>
                      <span>{a.context_item_count} sources</span>
                    </div>
                    {a.error && <p className="mt-1 line-clamp-2 text-xs text-rose-600">{a.error}</p>}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </>
  );
}
