import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Globe, RefreshCw, Sparkles, Trash2 } from "lucide-react";
import { ActivityChart, HBarChart } from "../components/charts";
import AnalysisView from "../components/AnalysisView";
import ItemRow from "../components/ItemRow";
import { Alert, Button, Card, EmptyState, ErrorState, RelationBadge, Skeleton, StatCard } from "../components/ui";
import { api } from "../lib/api";
import { formatDate, timeAgo } from "../lib/format";
import { useAsync } from "../lib/hooks";
import type { Analysis, CompanyDetail } from "../lib/types";

export default function CompanyDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { data, error, loading, reload } = useAsync(() => api<CompanyDetail>(`/companies/${id}`), [id]);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);

  async function analyze(force: boolean) {
    setAnalyzing(true);
    setAnalysisError(null);
    try {
      setAnalysis(await api<Analysis>(`/analysis/company/${id}`, { method: "POST", body: { days: 30, force } }));
    } catch (e) {
      setAnalysisError((e as Error).message);
    } finally {
      setAnalyzing(false);
    }
  }

  async function remove() {
    if (!data || !window.confirm(`Stop tracking ${data.company.name}? All collected data for it will be deleted.`)) return;
    try {
      await api(`/companies/${id}`, { method: "DELETE" });
      navigate("/companies");
    } catch (e) {
      setAnalysisError((e as Error).message);
    }
  }

  if (loading && !data) return <div className="space-y-4"><Skeleton className="h-24" /><Skeleton className="h-72" /></div>;
  if (error || !data) {
    return (
      <>
        <Link to="/companies" className="mb-4 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700"><ArrowLeft className="h-4 w-4" /> Companies</Link>
        <ErrorState message={error ?? "Not found"} onRetry={reload} />
      </>
    );
  }

  const { company, stats } = data;
  const shown = analysis ?? data.latest_analysis;

  return (
    <>
      <Link to="/companies" className="mb-4 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700"><ArrowLeft className="h-4 w-4" /> Companies</Link>
      <div className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="max-w-3xl">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-semibold tracking-tight">{company.name}</h1>
            <RelationBadge relation={company.relation} />
            {company.ticker && <span className="text-sm font-medium text-slate-500">{company.ticker}</span>}
          </div>
          <p className="mt-2 text-sm leading-relaxed text-slate-600">{company.description || "No description available."}</p>
          <div className="mt-2 flex flex-wrap gap-4 text-xs text-slate-500">
            {company.industry && <span>{company.industry}</span>}
            {company.website && <a href={company.website} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 hover:text-indigo-600"><Globe className="h-3 w-3" />{company.website}</a>}
            <span>Search terms: {company.search_terms || company.name}</span>
            <span>Last collected {timeAgo(company.last_collected_at)}</span>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="danger" onClick={remove}><Trash2 className="h-4 w-4" /> Remove</Button>
          <Button onClick={() => analyze(false)} loading={analyzing}>{!analyzing && <Sparkles className="h-4 w-4" />} Analyze company</Button>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Total data points" value={stats.total_items} />
        <StatCard label="Last 7 days" value={stats.items_last_7d} />
        <StatCard label="Last 30 days" value={stats.items_last_30d} />
        <StatCard
          label="Sources"
          value={Object.keys(stats.sources).length}
          hint={Object.entries(stats.sources).map(([k, v]) => `${k}: ${v}`).join(" · ") || "No data yet"}
        />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card title="Activity timeline (30 days)" className="lg:col-span-2"><ActivityChart data={data.timeline} height={220} /></Card>
        <Card title="Categories (90 days)"><HBarChart data={data.categories} dataKey="count" labelKey="category" /></Card>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-5">
        <Card
          title="AI summary"
          className="lg:col-span-3"
          action={shown && (
            <Button variant="ghost" className="text-xs" onClick={() => analyze(true)} loading={analyzing}>
              {!analyzing && <RefreshCw className="h-3.5 w-3.5" />} Regenerate
            </Button>
          )}
        >
          {analysisError && <div className="mb-4"><Alert kind={analysisError.includes("No collected data") ? "info" : "error"}>{analysisError}</Alert></div>}
          {analyzing && !shown ? (
            <div className="space-y-3"><Skeleton className="h-16" /><Skeleton className="h-32" /></div>
          ) : shown ? (
            <AnalysisView analysis={shown} />
          ) : (
            <EmptyState
              icon={<Sparkles className="h-6 w-6" />}
              title="No AI summary yet"
              description={stats.total_items ? "Generate a summary grounded in this company's collected items." : "Collect data first, then generate a summary."}
              action={stats.total_items > 0 && <Button variant="secondary" onClick={() => analyze(false)}>Analyze company</Button>}
            />
          )}
        </Card>
        <Card
          title="Recent collected information"
          className="lg:col-span-2"
          action={<Link to={`/data?company_id=${company.id}`} className="text-xs font-medium text-indigo-600 hover:text-indigo-500">Search all →</Link>}
        >
          {data.recent_items.length ? (
            <ul className="-my-3 divide-y divide-slate-100">{data.recent_items.map((i) => <ItemRow key={i.id} item={i} showCompany={false} />)}</ul>
          ) : (
            <EmptyState title="No items yet" description="Run a collection from the Dashboard or Automation page." />
          )}
          {stats.first_item_at && (
            <p className="mt-4 text-xs text-slate-400">Coverage: {formatDate(stats.first_item_at)} – {formatDate(stats.last_item_at)}</p>
          )}
        </Card>
      </div>
    </>
  );
}
