import type { Envelope, HistoryItem, ReportType } from "./types";

const BASE = (process.env.API_BASE_URL ?? "http://localhost:8000").replace(/\/+$/, "");

// 무료 백엔드 서버(Render Free)는 잠들어 있다가 첫 요청에 깨어나는 데 30~60초가 걸릴 수 있다.
// 페이지 전체가 멈추지 않도록 요청마다 제한 시간을 두고, 초과 시 안내 문구를 보여 준다.
const TIMEOUT_MS = 8000;

export const REPORT_META: Record<ReportType, { title: string; slot: string }> = {
  "us-close": { title: "전일 미국 증시 마감", slot: "07:00 발행" },
  "kr-watchlist": { title: "국장 관전 포인트", slot: "07:00 발행" },
  "kr-close-and-calendar": { title: "국장 마감 + 익일 미국 캘린더", slot: "15:40 발행 · 수 분 지연 가능" },
};

export const isReportType = (v: string): v is ReportType => v in REPORT_META;

export type FetchResult<T> =
  | { ok: true; report: Envelope<T> }
  | { ok: false; status: number; message: string; waking?: boolean };

const WAKING_MESSAGE =
  "백엔드 서버가 깨어나는 중일 수 있습니다(무료 서버는 첫 접속 시 30~60초 소요).";

function get(path: string): Promise<Response> {
  return fetch(`${BASE}${path}`, { cache: "no-store", signal: AbortSignal.timeout(TIMEOUT_MS) });
}

const isTimeout = (e: unknown) => e instanceof Error && (e.name === "TimeoutError" || e.name === "AbortError");

export async function fetchReport<T>(type: ReportType, date?: string): Promise<FetchResult<T>> {
  const qs = date ? `?date=${encodeURIComponent(date)}` : "";
  try {
    const res = await get(`/report/${type}${qs}`);
    if (res.status === 404) return { ok: false, status: 404, message: "해당 일자의 리포트가 아직 없습니다." };
    if (res.status === 502 || res.status === 503)
      return { ok: false, status: res.status, message: WAKING_MESSAGE, waking: true };
    if (!res.ok) return { ok: false, status: res.status, message: `서버 오류 (${res.status})` };
    return { ok: true, report: (await res.json()) as Envelope<T> };
  } catch (e) {
    if (isTimeout(e)) return { ok: false, status: 0, message: WAKING_MESSAGE, waking: true };
    return { ok: false, status: 0, message: "백엔드 서버에 연결할 수 없습니다.", waking: true };
  }
}

export async function fetchHistory(type: ReportType, limit = 30): Promise<HistoryItem[]> {
  try {
    const res = await get(`/reports?type=${type}&limit=${limit}`);
    if (!res.ok) return [];
    return ((await res.json()) as { items: HistoryItem[] }).items;
  } catch {
    return [];
  }
}
