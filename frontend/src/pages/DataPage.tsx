import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ChevronLeft, ChevronRight, Search } from "lucide-react";
import ItemRow from "../components/ItemRow";
import { Button, Card, EmptyState, ErrorState, PageHeader, Skeleton, inputClass } from "../components/ui";
import { api } from "../lib/api";
import { num } from "../lib/format";
import { useAsync, useDebounced } from "../lib/hooks";
import type { Company, ItemPage } from "../lib/types";

const PAGE_SIZE = 20;

export default function DataPage() {
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get("q") ?? "");
  const debouncedQ = useDebounced(q);

  const filters = {
    company_id: params.get("company_id") ?? "",
    category: params.get("category") ?? "",
    source: params.get("source") ?? "",
    date_from: params.get("date_from") ?? "",
    date_to: params.get("date_to") ?? "",
    sort: params.get("sort") ?? "newest",
    page: Number(params.get("page") ?? 1),
  };

  function update(patch: Record<string, string | number>) {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(patch)) {
      if (v === "" || v === null) next.delete(k);
      else next.set(k, String(v));
    }
    if (!("page" in patch)) next.delete("page");
    setParams(next, { replace: true });
  }

  useEffect(() => {
    if ((params.get("q") ?? "") !== debouncedQ) update({ q: debouncedQ });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedQ]);

  const companies = useAsync(() => api<Company[]>("/companies"), []);
  const categories = useAsync(() => api<{ slug: string; name: string }[]>("/categories"), []);
  const sources = useAsync(() => api<{ key: string; name: string }[]>("/sources"), []);
  const items = useAsync(
    () => api<ItemPage>("/items", { query: { ...filters, q: params.get("q") ?? "", page_size: PAGE_SIZE } }),
    [params.toString()],
  );

  const totalPages = items.data ? Math.max(1, Math.ceil(items.data.total / PAGE_SIZE)) : 1;
  const selectClass = "rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm";
  const hasFilters = ["q", "company_id", "category", "source", "date_from", "date_to"].some((k) => params.get(k));

  return (
    <>
      <PageHeader title="Collected Data" description="Search everything the collectors have gathered. Filtering happens on the server." />
      <Card className="mb-6">
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-6">
          <div className="relative lg:col-span-2">
            <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
            <input className={inputClass + " pl-9"} placeholder="Search keywords…" value={q} onChange={(e) => setQ(e.target.value)} maxLength={200} aria-label="Keyword" />
          </div>
          <select className={selectClass} value={filters.company_id} onChange={(e) => update({ company_id: e.target.value })} aria-label="Company">
            <option value="">All companies</option>
            {companies.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <select className={selectClass} value={filters.category} onChange={(e) => update({ category: e.target.value })} aria-label="Category">
            <option value="">All categories</option>
            {categories.data?.map((c) => <option key={c.slug} value={c.slug}>{c.name}</option>)}
          </select>
          <select className={selectClass} value={filters.source} onChange={(e) => update({ source: e.target.value })} aria-label="Source">
            <option value="">All sources</option>
            {sources.data?.map((s) => <option key={s.key} value={s.key}>{s.name}</option>)}
          </select>
          <select className={selectClass} value={filters.sort} onChange={(e) => update({ sort: e.target.value })} aria-label="Sort">
            <option value="newest">Newest first</option>
            <option value="oldest">Oldest first</option>
            <option value="score">Highest score</option>
          </select>
          <label className="flex items-center gap-2 text-sm text-slate-600 lg:col-span-2">
            From <input type="date" className={selectClass + " flex-1"} value={filters.date_from} onChange={(e) => update({ date_from: e.target.value })} />
          </label>
          <label className="flex items-center gap-2 text-sm text-slate-600 lg:col-span-2">
            To <input type="date" className={selectClass + " flex-1"} value={filters.date_to} onChange={(e) => update({ date_to: e.target.value })} />
          </label>
          {hasFilters && (
            <Button variant="ghost" onClick={() => { setQ(""); setParams({}, { replace: true }); }}>Clear filters</Button>
          )}
        </div>
      </Card>

      <Card title={items.data ? `${num(items.data.total)} results` : "Results"}>
        {items.loading && !items.data ? (
          <div className="space-y-4">{[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-14" />)}</div>
        ) : items.error ? (
          <ErrorState message={items.error} onRetry={items.reload} />
        ) : !items.data?.items.length ? (
          <EmptyState
            icon={<Search className="h-6 w-6" />}
            title={hasFilters ? "No items match your filters" : "No data collected yet"}
            description={hasFilters ? "Try a broader search or clear the filters." : "Add companies and run a collection to populate this list."}
          />
        ) : (
          <>
            <ul className={"-my-3 divide-y divide-slate-100 transition-opacity " + (items.loading ? "opacity-50" : "")}>
              {items.data.items.map((i) => <ItemRow key={i.id} item={i} />)}
            </ul>
            <div className="mt-5 flex items-center justify-between border-t border-slate-100 pt-4 text-sm text-slate-500">
              <span>Page {filters.page} of {totalPages}</span>
              <div className="flex gap-2">
                <Button variant="secondary" disabled={filters.page <= 1} onClick={() => update({ page: filters.page - 1 })}><ChevronLeft className="h-4 w-4" /> Prev</Button>
                <Button variant="secondary" disabled={filters.page >= totalPages} onClick={() => update({ page: filters.page + 1 })}>Next <ChevronRight className="h-4 w-4" /></Button>
              </div>
            </div>
          </>
        )}
      </Card>
    </>
  );
}
