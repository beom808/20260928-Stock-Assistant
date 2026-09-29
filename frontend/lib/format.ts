export function pct(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const s = v > 0 ? "+" : "";
  return `${s}${v.toFixed(2)}%`;
}

export function num(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return v.toLocaleString("ko-KR", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

// 한국 관례: 상승 빨강, 하락 파랑
export function trendClass(v: number | null | undefined): string {
  if (!v) return "flat";
  return v > 0 ? "up" : "down";
}

export function utcToKst(iso: string): string {
  const d = new Date(iso);
  return new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(d) + " KST";
}

const WEEKDAY = ["일", "월", "화", "수", "목", "금", "토"];

// "2026-09-28" 또는 "2026-09-28 07:00 KST" → "2026-09-28(월)" / "2026-09-28(월) 07:00 KST"
export function withWeekday(s: string | null | undefined): string {
  if (!s) return "";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
  if (!m) return s;
  const wd = WEEKDAY[new Date(Date.UTC(+m[1], +m[2] - 1, +m[3])).getUTCDay()];
  return `${m[0]}(${wd})${s.slice(10)}`;
}

// 부호 있는 수 ("+1.93" / "−0.01")
export function signed(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const s = v > 0 ? "+" : v < 0 ? "−" : "";
  return `${s}${Math.abs(v).toLocaleString("ko-KR", { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
}

// 억원 → "−2조 9,629억" / "+1,248억"
export function eok(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const sign = v > 0 ? "+" : v < 0 ? "−" : "";
  const n = Math.round(Math.abs(v));
  const jo = Math.floor(n / 10000);
  const rest = n % 10000;
  return jo ? `${sign}${jo}조 ${rest.toLocaleString("ko-KR")}억` : `${sign}${rest.toLocaleString("ko-KR")}억`;
}
