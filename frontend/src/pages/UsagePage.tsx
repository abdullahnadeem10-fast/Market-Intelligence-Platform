import { Activity, Coins, Cpu, Timer } from "lucide-react";
import { TokensChart } from "../components/charts";
import { Alert, Badge, Card, EmptyState, ErrorState, PageHeader, Skeleton, StatCard, StatusBadge } from "../components/ui";
import { api } from "../lib/api";
import { formatDate, num, usd } from "../lib/format";
import { useAsync } from "../lib/hooks";
import type { Usage } from "../lib/types";

export default function UsagePage() {
  const { data, error, loading, reload } = useAsync(() => api<Usage>("/usage/ai"), []);

  return (
    <>
      <PageHeader title="AI Usage" description="Token consumption, cost and latency of AI analyses." />
      {loading && !data ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-28" />)}</div>
      ) : error || !data ? (
        <ErrorState message={error ?? "Failed to load"} onRetry={reload} />
      ) : (
        <>
          {data.provider === "extractive" && (
            <div className="mb-4">
              <Alert kind="info">
                No LLM is configured (LLM_PROVIDER=extractive). Analyses are built with rule-based extraction and use no tokens.
                Set LLM_PROVIDER=openai and LLM_API_KEY in the backend .env to enable AI analysis.
              </Alert>
            </div>
          )}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard label="Analyses" value={data.total_analyses} icon={<Activity className="h-4 w-4" />} hint={`${data.successful_analyses} succeeded · ${data.failed_analyses} failed`} />
            <StatCard label="Tokens" value={num(data.input_tokens + data.output_tokens)} icon={<Cpu className="h-4 w-4" />} hint={`${num(data.input_tokens)} input · ${num(data.output_tokens)} output`} />
            <StatCard label="Approximate cost" value={usd(data.estimated_cost_usd)} icon={<Coins className="h-4 w-4" />} hint={`Model: ${data.model}`} />
            <StatCard label="Avg. response time" value={`${(data.avg_latency_ms / 1000).toFixed(2)}s`} icon={<Timer className="h-4 w-4" />} hint="Successful analyses" />
          </div>

          <Card title="Tokens per day" className="mt-6">
            <TokensChart data={data.by_day} />
          </Card>

          <Card title="Recent analyses" className="mt-6">
            {!data.recent.length ? (
              <EmptyState title="No analyses yet" />
            ) : (
              <div className="-mx-5 overflow-x-auto">
                <table className="w-full min-w-[720px] text-sm">
                  <thead>
                    <tr className="border-b border-slate-100 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
                      <th className="px-5 py-2.5">When</th><th>Scope</th><th>Status</th><th>Model</th>
                      <th className="text-right">Input</th><th className="text-right">Output</th><th className="text-right">Cost</th><th className="px-5 text-right">Latency</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {data.recent.map((r) => (
                      <tr key={r.id}>
                        <td className="px-5 py-2.5 text-slate-600">{formatDate(r.created_at, true)}</td>
                        <td>{r.company ?? <Badge color="indigo">Market</Badge>}</td>
                        <td>
                          <StatusBadge status={r.status} />
                          {r.error && <span className="ml-2 text-xs text-rose-600" title={r.error}>{r.error.slice(0, 40)}</span>}
                        </td>
                        <td className="text-slate-600">{r.model}</td>
                        <td className="text-right tabular-nums">{num(r.input_tokens)}{r.tokens_estimated && "*"}</td>
                        <td className="text-right tabular-nums">{num(r.output_tokens)}</td>
                        <td className="text-right tabular-nums">{usd(r.cost_usd)}</td>
                        <td className="px-5 text-right tabular-nums">{(r.latency_ms / 1000).toFixed(2)}s</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="px-5 pt-3 text-xs text-slate-400">* estimated (~4 characters per token) when the provider did not report usage.</p>
              </div>
            )}
          </Card>
        </>
      )}
    </>
  );
}
