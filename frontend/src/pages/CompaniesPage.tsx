import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { Building2, Globe, Plus, Rss, Trash2, X } from "lucide-react";
import { Alert, Button, Card, EmptyState, ErrorState, Field, PageHeader, RelationBadge, Skeleton, inputClass } from "../components/ui";
import { api } from "../lib/api";
import { timeAgo } from "../lib/format";
import { useAsync } from "../lib/hooks";
import type { Company, Relation } from "../lib/types";

const emptyForm = { name: "", relation: "competitor" as Relation, website: "", industry: "", ticker: "", search_terms: "", rss_url: "", description: "" };

function AddCompanyForm({ onCreated, onCancel }: { onCreated: () => void; onCancel: () => void }) {
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const body: Record<string, string> = { name: form.name, relation: form.relation, description: form.description };
    for (const k of ["website", "industry", "ticker", "search_terms", "rss_url"] as const) if (form[k].trim()) body[k] = form[k].trim();
    try {
      await api("/companies", { method: "POST", body });
      setForm(emptyForm);
      onCreated();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Track a new company" action={<button onClick={onCancel} className="text-slate-400 hover:text-slate-600" aria-label="Close"><X className="h-4 w-4" /></button>} className="mb-6">
      <form onSubmit={submit} className="space-y-4">
        {error && <Alert>{error}</Alert>}
        <div className="grid gap-4 md:grid-cols-3">
          <Field label="Company name *">
            <input className={inputClass} required maxLength={120} value={form.name} onChange={set("name")} placeholder="e.g. Nvidia" />
          </Field>
          <Field label="Relationship">
            <select className={inputClass} value={form.relation} onChange={set("relation")}>
              <option value="own">Our company</option>
              <option value="competitor">Competitor</option>
              <option value="watch">Watching</option>
            </select>
          </Field>
          <Field label="Industry">
            <input className={inputClass} maxLength={80} value={form.industry} onChange={set("industry")} placeholder="e.g. Semiconductors" />
          </Field>
          <Field label="Website">
            <input className={inputClass} type="url" value={form.website} onChange={set("website")} placeholder="https://…" />
          </Field>
          <Field label="Ticker">
            <input className={inputClass} maxLength={12} value={form.ticker} onChange={set("ticker")} placeholder="e.g. NVDA" />
          </Field>
          <Field label="Search terms" hint="Comma-separated. Defaults to the company name.">
            <input className={inputClass} maxLength={255} value={form.search_terms} onChange={set("search_terms")} placeholder="Nvidia, GeForce" />
          </Field>
        </div>
        <Field label="RSS / Atom feed (optional)" hint="A public press-room or blog feed. robots.txt is respected.">
          <input className={inputClass} type="url" value={form.rss_url} onChange={set("rss_url")} placeholder="https://company.com/blog/rss.xml" />
        </Field>
        <Field label="Description" hint="Leave empty to fetch a short description from Wikipedia automatically.">
          <textarea className={inputClass} rows={2} maxLength={2000} value={form.description} onChange={set("description")} />
        </Field>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onCancel}>Cancel</Button>
          <Button type="submit" loading={busy}>Add company</Button>
        </div>
      </form>
    </Card>
  );
}

export default function CompaniesPage() {
  const { data, error, loading, reload } = useAsync(() => api<Company[]>("/companies"), []);
  const [showForm, setShowForm] = useState(false);
  const [deleting, setDeleting] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  async function remove(c: Company) {
    if (!window.confirm(`Stop tracking ${c.name}? Its ${c.item_count} collected items and analyses will be deleted.`)) return;
    setDeleting(c.id);
    setActionError(null);
    try {
      await api(`/companies/${c.id}`, { method: "DELETE" });
      reload();
    } catch (e) {
      setActionError((e as Error).message);
    } finally {
      setDeleting(null);
    }
  }

  return (
    <>
      <PageHeader
        title="Companies"
        description="The companies and competitors you monitor."
        actions={!showForm && <Button onClick={() => setShowForm(true)}><Plus className="h-4 w-4" /> Add company</Button>}
      />
      {showForm && <AddCompanyForm onCreated={() => { setShowForm(false); reload(); }} onCancel={() => setShowForm(false)} />}
      {actionError && <div className="mb-4"><Alert>{actionError}</Alert></div>}

      {loading && !data ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-44" />)}</div>
      ) : error ? (
        <ErrorState message={error} onRetry={reload} />
      ) : !data?.length ? (
        <Card>
          <EmptyState
            icon={<Building2 className="h-6 w-6" />}
            title="No companies tracked yet"
            description="Add your own company and a few competitors to start collecting market intelligence."
            action={!showForm && <Button onClick={() => setShowForm(true)}><Plus className="h-4 w-4" /> Add your first company</Button>}
          />
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {data.map((c) => (
            <div key={c.id} className="flex flex-col rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition hover:border-indigo-200 hover:shadow">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <Link to={`/companies/${c.id}`} className="text-base font-semibold text-slate-900 hover:text-indigo-600">
                    {c.name}
                  </Link>
                  <div className="mt-1 flex flex-wrap items-center gap-2">
                    <RelationBadge relation={c.relation} />
                    {c.ticker && <span className="text-xs font-medium text-slate-500">{c.ticker}</span>}
                    {c.industry && <span className="text-xs text-slate-500">{c.industry}</span>}
                  </div>
                </div>
                <Button variant="ghost" className="px-2" onClick={() => remove(c)} loading={deleting === c.id} aria-label={`Remove ${c.name}`}>
                  {deleting !== c.id && <Trash2 className="h-4 w-4" />}
                </Button>
              </div>
              <p className="mt-3 line-clamp-3 flex-1 text-sm text-slate-500">{c.description || "No description."}</p>
              <div className="mt-4 grid grid-cols-3 gap-2 border-t border-slate-100 pt-3 text-center">
                <div><p className="text-lg font-semibold">{c.item_count}</p><p className="text-[11px] text-slate-500">Items</p></div>
                <div><p className="text-lg font-semibold">{c.items_last_7d}</p><p className="text-[11px] text-slate-500">Last 7d</p></div>
                <div><p className="text-sm font-medium pt-1">{timeAgo(c.last_collected_at)}</p><p className="text-[11px] text-slate-500">Collected</p></div>
              </div>
              <div className="mt-3 flex gap-3 text-xs text-slate-400">
                {c.website && <a href={c.website} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 hover:text-indigo-600"><Globe className="h-3 w-3" /> Website</a>}
                {c.rss_url && <span className="inline-flex items-center gap-1"><Rss className="h-3 w-3" /> RSS feed</span>}
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
