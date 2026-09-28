import type { Envelope, HistoryItem, ReportType } from "./types";

const BASE = process.env.API_BASE_URL ?? "http://localhost:8000";

export const REPORT_META: Record<ReportType, { title: string; slot: string }> = {
  "us-close": { title: "전일 미국 증시 마감", slot: "07:00 KST" },
  "kr-watchlist": { title: "한국장 관전 포인트", slot: "07:00 KST" },
  "kr-close-and-calendar": { title: "국내 장 마감 + 익일 미국 캘린더", slot: "15:30 KST 장 마감 후" },
};

export const isReportType = (v: string): v is ReportType => v in REPORT_META;

export type FetchResult<T> =
  | { ok: true; report: Envelope<T> }
  | { ok: false; status: number; message: string };

export async function fetchReport<T>(type: ReportType, date?: string): Promise<FetchResult<T>> {
  const qs = date ? `?date=${encodeURIComponent(date)}` : "";
  try {
    const res = await fetch(`${BASE}/report/${type}${qs}`, { cache: "no-store" });
    if (res.status === 404) return { ok: false, status: 404, message: "해당 일자의 리포트가 아직 없습니다." };
    if (!res.ok) return { ok: false, status: res.status, message: `서버 오류 (${res.status})` };
    return { ok: true, report: (await res.json()) as Envelope<T> };
  } catch {
    return { ok: false, status: 0, message: "백엔드 서버에 연결할 수 없습니다." };
  }
}

export async function fetchHistory(type: ReportType, limit = 30): Promise<HistoryItem[]> {
  try {
    const res = await fetch(`${BASE}/reports?type=${type}&limit=${limit}`, { cache: "no-store" });
    if (!res.ok) return [];
    return ((await res.json()) as { items: HistoryItem[] }).items;
  } catch {
    return [];
  }
}
