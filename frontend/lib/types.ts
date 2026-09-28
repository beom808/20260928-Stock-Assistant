// 백엔드 리포트 payload 타입 (backend/app/reports/builders.py 와 동기화)

export type ReportType = "us-close" | "kr-watchlist" | "kr-close-and-calendar";

export interface Source {
  name: string;
  used_for: string;
  fetched_at_kst: string | null;
  stale_cache: boolean;
}

export interface Envelope<T> {
  report_type: ReportType;
  title: string;
  report_date_kst: string;
  generated_at_kst: string;
  disclaimer: string;
  status: "ok" | "partial" | "failed";
  sources: Source[];
  warnings: string[];
  errors: string[];
  revision?: number;
  data: T;
}

export interface IndexQuote {
  name: string;
  symbol: string;
  close?: number | null;
  change?: number | null;
  change_pct?: number | null;
  as_of_kst?: string | null;
  provider?: string;
  is_proxy?: boolean;
  note?: string | null;
  error?: string;
}

export interface UsNews {
  rank: number;
  title: string;
  title_ko: string | null;
  summary: string;
  summary_origin: "llm" | "api";
  tier: "a" | "b" | "c" | "d";
  tier_label: string;
  sectors: { key: string; label: string }[];
  tickers: string[];
  url: string | null;
  source: string;
  provider: string;
  published_at_utc: string;
}

export interface UsCloseData {
  session_date_et: string;
  session_close_kst: string;
  session_close_tz: string;
  indices: IndexQuote[];
  news: UsNews[];
  news_window_kst: string;
  ranking_method: "llm" | "rules";
  selection_criteria: string[];
}

export interface KrCompany {
  code: string;
  name: string;
  market: string;
  relevance: number;
  scores: Record<"same_industry" | "supply_chain" | "sensitivity" | "theme", number>;
  rationale: string;
  rationale_origin: "rule" | "llm";
}

export interface WatchSector {
  key: string;
  us_label: string;
  kr_sector: string;
  heat: number;
  us_tickers: string[];
  news_refs: { rank: number; title: string }[];
  watch_point: string;
  companies: KrCompany[];
}

export interface KrWatchlistData {
  notice: string;
  us_session_date_et: string | null;
  method: "rules" | "hybrid";
  weights: Record<string, number>;
  macro_points: { rank: number; title: string }[];
  sectors: WatchSector[];
}

export interface KrIssue {
  rank: number;
  title: string;
  summary: string;
  summary_origin: "llm" | "api";
  url: string | null;
  source: string;
  published_at_kst: string;
}

export interface CalendarRow {
  event: string;
  kind: string;
  et: string;
  kst: string;
  consensus: string | null;
  previous: string | null;
  time_confirmed: boolean;
  note: string | null;
  provider: string;
}

export interface KrCloseData {
  indices: IndexQuote[];
  issues: KrIssue[];
  issue_method: string;
  us_calendar: { window_kst: string; rows: CalendarRow[] };
  calendar_columns: string[];
}

export interface HistoryItem {
  report_type: ReportType;
  report_date_kst: string;
  generated_at_kst: string;
  status: string;
  revision: number;
}
