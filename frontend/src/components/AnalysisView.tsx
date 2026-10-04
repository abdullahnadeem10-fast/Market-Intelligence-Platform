import { useState } from "react";
import { AlertTriangle, ExternalLink, Lightbulb, Newspaper, Swords, Target, TrendingUp, Zap } from "lucide-react";
import type { Analysis, AnalysisSource, Insight } from "../lib/types";
import { formatDate, num, usd } from "../lib/format";
import { Badge, cx } from "./ui";

const SECTIONS: { key: keyof Omit<NonNullable<Analysis["result"]>, "market_summary">; label: string; icon: typeof Zap; tone: string }[] = [
  { key: "emerging_trends", label: "Emerging trends", icon: TrendingUp, tone: "text-indigo-600 bg-indigo-50" },
  { key: "important_developments", label: "Important developments", icon: Newspaper, tone: "text-sky-600 bg-sky-50" },
  { key: "competitor_activity", label: "Competitor activity", icon: Swords, tone: "text-amber-600 bg-amber-50" },
  { key: "opportunities", label: "Opportunities", icon: Lightbulb, tone: "text-emerald-600 bg-emerald-50" },
  { key: "risks", label: "Risks", icon: AlertTriangle, tone: "text-rose-600 bg-rose-50" },
  { key: "key_takeaways", label: "Key takeaways", icon: Target, tone: "text-violet-600 bg-violet-50" },
];

function Cite({ refs, onFocus }: { refs: number[]; onFocus: (r: number) => void }) {
  return (
    <span className="ml-1 inline-flex flex-wrap gap-1 align-middle">
      {refs.map((r) => (
        <button
          key={r}
          onClick={() => onFocus(r)}
          className="rounded bg-slate-100 px-1.5 text-[11px] font-semibold text-slate-600 hover:bg-indigo-100 hover:text-indigo-700"
          title={`Show source ${r}`}
        >
          {r}
        </button>
      ))}
    </span>
  );
}

function SummaryText({ text, onFocus }: { text: string; onFocus: (r: number) => void }) {
  const parts = text.split(/(\[\d+\])/g);
  return (
    <p className="text-sm leading-relaxed text-slate-700">
      {parts.map((p, i) => {
        const m = p.match(/^\[(\d+)\]$/);
        return m ? <Cite key={i} refs={[Number(m[1])]} onFocus={onFocus} /> : <span key={i}>{p}</span>;
      })}
    </p>
  );
}

function InsightList({ items, onFocus }: { items: Insight[]; onFocus: (r: number) => void }) {
  if (!items.length) return <p className="text-sm text-slate-400">Nothing supported by the sources.</p>;
  return (
    <ul className="space-y-2.5">
      {items.map((ins, i) => (
        <li key={i} className="flex gap-2 text-sm leading-relaxed text-slate-700">
          <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-slate-300" />
          <span>
            {ins.text}
            <Cite refs={ins.sources} onFocus={onFocus} />
          </span>
        </li>
      ))}
    </ul>
  );
}

export function SourceList({ sources, highlighted }: { sources: AnalysisSource[]; highlighted?: number | null }) {
  return (
    <ol className="divide-y divide-slate-100">
      {sources.map((s) => (
        <li
          key={s.ref}
          id={`source-${s.ref}`}
          className={cx("flex gap-3 py-2.5 transition-colors", highlighted === s.ref && "rounded-md bg-indigo-50")}
        >
          <span className="w-6 shrink-0 pt-0.5 text-right text-xs font-semibold text-slate-400">{s.ref}</span>
          <div className="min-w-0">
            <a href={s.url} target="_blank" rel="noopener noreferrer" className="group text-sm font-medium text-slate-800 hover:text-indigo-600">
              {s.title}
              <ExternalLink className="ml-1 inline h-3 w-3 opacity-0 group-hover:opacity-100" />
            </a>
            <p className="text-xs text-slate-500">
              {s.company_name} · {s.source} · {formatDate(s.published_at)}
            </p>
          </div>
        </li>
      ))}
    </ol>
  );
}

export default function AnalysisView({ analysis, compact = false }: { analysis: Analysis; compact?: boolean }) {
  const [focus, setFocus] = useState<number | null>(null);
  const result = analysis.result;
  const onFocus = (r: number) => {
    setFocus(r);
    document.getElementById(`source-${r}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  if (analysis.status === "failed" || !result) {
    return <p className="text-sm text-rose-600">Analysis failed: {analysis.error ?? "unknown error"}</p>;
  }

  const sections = compact ? SECTIONS.filter((s) => ["important_developments", "risks", "key_takeaways"].includes(s.key)) : SECTIONS;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
        <Badge color={analysis.provider === "extractive" ? "slate" : "indigo"}>
          {analysis.provider === "extractive" ? "Extractive (no LLM)" : analysis.model}
        </Badge>
        {analysis.cached && <Badge color="blue">Cached result</Badge>}
        <span>{formatDate(analysis.created_at, true)}</span>
        <span>·</span>
        <span>{analysis.context_item_count} sources</span>
        {analysis.provider !== "extractive" && (
          <>
            <span>·</span>
            <span>
              {num(analysis.input_tokens)} in / {num(analysis.output_tokens)} out tokens{analysis.tokens_estimated && " (est.)"}
            </span>
            <span>·</span>
            <span>{usd(analysis.cost_usd)}</span>
            <span>·</span>
            <span>{(analysis.latency_ms / 1000).toFixed(1)}s</span>
          </>
        )}
      </div>

      <div className="rounded-lg border border-slate-200 bg-slate-50/60 p-4">
        <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">Market summary</p>
        <SummaryText text={result.market_summary} onFocus={onFocus} />
      </div>

      <div className={cx("grid gap-5", !compact && "md:grid-cols-2")}>
        {sections.map(({ key, label, icon: Icon, tone }) => (
          <div key={key}>
            <div className="mb-2.5 flex items-center gap-2">
              <span className={cx("rounded-md p-1.5", tone)}>
                <Icon className="h-3.5 w-3.5" />
              </span>
              <h3 className="text-sm font-semibold text-slate-800">{label}</h3>
            </div>
            <InsightList items={result[key]} onFocus={onFocus} />
          </div>
        ))}
      </div>

      <div>
        <h3 className="mb-1 text-sm font-semibold text-slate-800">Sources used ({analysis.sources.length})</h3>
        <p className="mb-2 text-xs text-slate-500">Every insight above cites these collected items. Click a number to jump to its source.</p>
        <SourceList sources={analysis.sources} highlighted={focus} />
      </div>
    </div>
  );
}
