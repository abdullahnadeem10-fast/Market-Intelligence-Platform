export type Relation = "own" | "competitor" | "watch";

export interface User {
  id: number;
  email: string;
  full_name: string;
  created_at: string;
}

export interface Company {
  id: number;
  name: string;
  description: string;
  website: string | null;
  industry: string | null;
  ticker: string | null;
  search_terms: string | null;
  rss_url: string | null;
  relation: Relation;
  created_at: string;
  last_collected_at: string | null;
  item_count: number;
  items_last_7d: number;
}

export interface Item {
  id: number;
  company_id: number;
  company_name: string;
  source: string;
  url: string;
  title: string;
  summary: string;
  author: string | null;
  domain: string | null;
  score: number | null;
  published_at: string;
  collected_at: string;
  categories: string[];
}

export interface ItemPage {
  items: Item[];
  total: number;
  page: number;
  page_size: number;
}

export interface Insight {
  text: string;
  sources: number[];
}

export interface AnalysisResult {
  market_summary: string;
  emerging_trends: Insight[];
  important_developments: Insight[];
  competitor_activity: Insight[];
  opportunities: Insight[];
  risks: Insight[];
  key_takeaways: Insight[];
}

export interface AnalysisSource {
  ref: number;
  item_id: number;
  title: string;
  url: string;
  source: string;
  company_name: string;
  published_at: string;
}

export interface Analysis {
  id: number;
  scope: "company" | "market";
  company_id: number | null;
  status: "success" | "failed";
  provider: string;
  model: string;
  result: AnalysisResult | null;
  error: string | null;
  sources: AnalysisSource[];
  context_item_count: number;
  input_tokens: number;
  output_tokens: number;
  tokens_estimated: boolean;
  cost_usd: number;
  latency_ms: number;
  created_at: string;
  cached: boolean;
}

export interface CompanyDetail {
  company: Company;
  stats: {
    total_items: number;
    items_last_7d: number;
    items_last_30d: number;
    sources: Record<string, number>;
    first_item_at: string | null;
    last_item_at: string | null;
  };
  timeline: { date: string; count: number }[];
  categories: { category: string; count: number }[];
  recent_items: Item[];
  latest_analysis: Analysis | null;
}

export interface CollectionRun {
  id: number;
  trigger: "manual" | "scheduled";
  status: "running" | "success" | "partial" | "failed";
  started_at: string;
  finished_at: string | null;
  companies_processed: number;
  items_fetched: number;
  items_new: number;
  items_duplicate: number;
  items_invalid: number;
  error_count: number;
  details: {
    sources?: Record<string, { fetched: number; new: number; duplicate: number; invalid: number; errors: number; skipped?: number }>;
    errors?: { company?: string; source?: string; error: string }[];
    skipped?: { company: string; source: string; reason: string }[];
    collectors?: string[];
    note?: string | null;
  };
}

export interface CollectionStatus {
  scheduler_enabled: boolean;
  interval_minutes: number;
  demo_mode: boolean;
  collectors: string[];
  next_run_at: string | null;
}

export interface Dashboard {
  overview: {
    tracked_companies: number;
    total_items: number;
    items_last_7d: number;
    items_prev_7d: number;
    analyses: number;
    last_run: { id: number; status: string; started_at: string; finished_at: string | null; items_new: number } | null;
  };
  activity: { date: string; count: number }[];
  by_company: { company: string; relation: Relation; count: number }[];
  by_category: { category: string; count: number }[];
  by_source: { source: string; count: number }[];
  mentions: { company: string; mentions: number }[];
  trends: { term: string; count: number; previous: number }[];
  competitors: { id: number; company: string; title: string; url: string; published_at: string; categories: string[] }[];
  recent_items: Item[];
  latest_market_analysis: Analysis | null;
}

export interface Usage {
  provider: string;
  model: string;
  total_analyses: number;
  successful_analyses: number;
  failed_analyses: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: number;
  avg_latency_ms: number;
  by_day: { date: string; analyses: number; input_tokens: number; output_tokens: number; cost_usd: number }[];
  recent: {
    id: number;
    scope: string;
    company: string | null;
    status: string;
    provider: string;
    model: string;
    input_tokens: number;
    output_tokens: number;
    tokens_estimated: boolean;
    cost_usd: number;
    latency_ms: number;
    created_at: string;
    error: string | null;
  }[];
}
