import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowDownRight, ArrowUpRight, Building2, Database, Newspaper, Sparkles } from "lucide-react";
import { ActivityChart, HBarChart, TrendChart } from "../components/charts";
import AnalysisView from "../components/AnalysisView";
import ItemRow from "../components/ItemRow";
import RunCollectionButton from "../components/RunCollectionButton";
import { Alert, Badge, Button, Card, EmptyState, ErrorState, PageHeader, Skeleton, StatCard, StatusBadge } from "../components/ui";
import { api } from "../lib/api";
import { num, timeAgo } from "../lib/format";
import { useAsync } from "../lib/hooks";
import type { Dashboard } from "../lib/types";

export default function DashboardPage() {
  const [days, setDays] = useState(30);
  const [notice, setNotice] = useState<{ kind: "success" | "error" | "warning"; text: string } | null>(null);
  const { data, error, loading, reload } = useAsync(() => api<Dashboard>("/analytics/dashboard", { query: { days } }), [days]);

  const periodSelect = (
    <select
      value={days}
      onChange={(e) => setDays(Number(e.target.value))}
      className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
      aria-label="Time window"
    >
      <option value={7}>Last 7 days</option>
      <option value={30}>Last 30 days</option>
      <option value={90}>Last 90 days</option>
    </select>
  );

  const header = (
    <PageHeader
      title="Dashboard"
      description="An overview of activity across the companies you track."
      actions={
        <>
          {periodSelect}
          <RunCollectionButton
            onDone={(run) => {
              setNotice({
                kind: run.status === "success" ? "success" : run.status === "partial" ? "warning" : "error",
                text: `Collection ${run.status}: ${run.items_new} new, ${run.items_duplicate} duplicates skipped${run.error_count ? `, ${run.error_count} source errors (see Automation)` : ""}.`,
              });
              reload();
            }}
            onError={(msg) => setNotice({ kind: "error", text: msg })}
          />
        </>
      }
    />
  );

  if (loading && !data) {
    return (
      <>
        {header}
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-28" />)}
        </div>
        <Skeleton className="mt-6 h-80" />
      </>
    );
  }
  if (error || !data) return <>{header}<ErrorState message={error ?? "Failed to load"} onRetry={reload} /></>;

  const o = data.overview;
  const delta = o.items_last_7d - o.items_prev_7d;

  if (o.tracked_companies === 0) {
    return (
      <>
        {header}
        <Card>
          <EmptyState
            icon={<Building2 className="h-6 w-6" />}
            title="Start by tracking a company"
            description="Add your company and competitors. The collector will then gather public news about them automatically."
            action={<Link to="/companies"><Button>Add a company</Button></Link>}
          />
        </Card>
      </>
    );
  }

  return (
    <>
      {header}
      {notice && <div className="mb-4"><Alert kind={notice.kind}>{notice.text}</Alert></div>}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Tracked companies" value={o.tracked_companies} icon={<Building2 className="h-4 w-4" />} />
        <StatCard label="Collected data points" value={num(o.total_items)} icon={<Database className="h-4 w-4" />} hint="All time" />
        <StatCard
          label="New items (7 days)"
          value={num(o.items_last_7d)}
          icon={<Newspaper className="h-4 w-4" />}
          hint={
            <span className={delta >= 0 ? "text-emerald-600" : "text-rose-600"}>
              {delta >= 0 ? <ArrowUpRight className="inline h-3 w-3" /> : <ArrowDownRight className="inline h-3 w-3" />}
              {delta >= 0 ? "+" : "−"}{Math.abs(delta)} vs previous 7 days
            </span>
          }
        />
        <StatCard
          label="Last collection"
          value={o.last_run ? timeAgo(o.last_run.finished_at ?? o.last_run.started_at) : "Never"}
          icon={<Sparkles className="h-4 w-4" />}
          hint={o.last_run ? <span className="inline-flex items-center gap-1.5"><StatusBadge status={o.last_run.status} /> {o.last_run.items_new} new items</span> : "Run a collection to fetch data"}
        />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card title="Market activity over time" className="lg:col-span-2">
          <ActivityChart data={data.activity} />
        </Card>
        <Card title="Activity by category">
          <HBarChart data={data.by_category} dataKey="count" labelKey="category" />
        </Card>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card title="Data points by company">
          <HBarChart data={data.by_company} dataKey="count" labelKey="company" color="#0ea5e9" />
        </Card>
        <Card title="Most mentioned companies">
          <HBarChart data={data.mentions} dataKey="mentions" labelKey="company" color="#8b5cf6" valueLabel="Mentions" />
        </Card>
        <Card title="Trending terms">
          <TrendChart data={data.trends.slice(0, 8)} />
        </Card>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-5">
        <Card
          title="AI market insights"
          className="lg:col-span-3"
          action={<Link to="/analysis" className="text-xs font-medium text-indigo-600 hover:text-indigo-500">Open analysis →</Link>}
        >
          {data.latest_market_analysis ? (
            <AnalysisView analysis={data.latest_market_analysis} compact />
          ) : (
            <EmptyState
              icon={<Sparkles className="h-6 w-6" />}
              title="No market analysis yet"
              description="Generate an AI analysis based on the data you've collected."
              action={<Link to="/analysis"><Button variant="secondary">Analyze market</Button></Link>}
            />
          )}
        </Card>
        <div className="space-y-6 lg:col-span-2">
          <Card title="Competitor activity">
            {data.competitors.length ? (
              <ul className="space-y-3">
                {data.competitors.slice(0, 5).map((c) => (
                  <li key={c.id} className="text-sm">
                    <div className="flex items-center gap-2">
                      <Badge color="amber">{c.company}</Badge>
                      <span className="text-xs text-slate-400">{timeAgo(c.published_at)}</span>
                    </div>
                    <a href={c.url} target="_blank" rel="noopener noreferrer" className="mt-1 block text-slate-700 hover:text-indigo-600">
                      {c.title}
                    </a>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState title="No competitor activity" description="Mark companies as competitors to see their recent moves here." />
            )}
          </Card>
          <Card title="Recent market activity" action={<Link to="/data" className="text-xs font-medium text-indigo-600 hover:text-indigo-500">View all →</Link>}>
            {data.recent_items.length ? (
              <ul className="-my-3 divide-y divide-slate-100">
                {data.recent_items.slice(0, 5).map((i) => <ItemRow key={i.id} item={i} />)}
              </ul>
            ) : (
              <EmptyState title="Nothing collected yet" description="Run a collection to pull the latest public news." />
            )}
          </Card>
        </div>
      </div>
    </>
  );
}
