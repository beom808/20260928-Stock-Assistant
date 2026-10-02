import Link from "next/link";
import { notFound } from "next/navigation";
import { fetchHistory, fetchReport, isReportType, REPORT_META } from "@/lib/api";
import { withWeekday } from "@/lib/format";
import type { KrCloseData, KrWatchlistData, UsCloseData } from "@/lib/types";
import { LoadError } from "@/components/LoadError";
import { KrCloseView, KrWatchlistView, UsCloseView } from "@/components/ReportViews";
import { ShareBar } from "@/components/ShareBar";

export const dynamic = "force-dynamic";

type Props = {
  params: Promise<{ type: string }>;
  searchParams: Promise<{ date?: string }>;
};

export default async function ReportPage({ params, searchParams }: Props) {
  const { type } = await params;
  const { date } = await searchParams;
  if (!isReportType(type)) notFound();
  const validDate = date && /^\d{4}-\d{2}-\d{2}$/.test(date) ? date : undefined;
  const history = await fetchHistory(type);

  let body: React.ReactNode;
  if (type === "us-close") {
    const res = await fetchReport<UsCloseData>(type, validDate);
    body = res.ok ? <UsCloseView r={res.report} /> : <LoadError message={res.message} waking={res.waking} />;
  } else if (type === "kr-watchlist") {
    const res = await fetchReport<KrWatchlistData>(type, validDate);
    body = res.ok ? <KrWatchlistView r={res.report} /> : <LoadError message={res.message} waking={res.waking} />;
  } else {
    const res = await fetchReport<KrCloseData>(type, validDate);
    body = res.ok ? <KrCloseView r={res.report} /> : <LoadError message={res.message} waking={res.waking} />;
  }

  return (
    <div className="report-page">
      <div className="slot-head">
        <h1>{REPORT_META[type].title}</h1>
        <span className="badge">{REPORT_META[type].slot}</span>
        <div style={{ marginLeft: "auto" }}>
          <ShareBar title={REPORT_META[type].title} />
        </div>
      </div>
      <form className="date-form" method="get">
        <label>
          일자 조회(KST){" "}
          <input type="date" name="date" defaultValue={validDate} />
        </label>
        <button type="submit">조회</button>
        {validDate && <Link href={`/report/${type}`}>최신으로</Link>}
      </form>
      {history.length > 0 && (
        <div className="history">
          {history.map((h) => (
            <Link
              key={h.report_date_kst}
              href={`/report/${type}?date=${h.report_date_kst}`}
              className={`chip ${h.report_date_kst === validDate ? "active" : ""}`}
            >
              {withWeekday(h.report_date_kst).slice(5)}
              {h.status !== "ok" ? " ⚠" : ""}
            </Link>
          ))}
        </div>
      )}
      {body}
    </div>
  );
}
