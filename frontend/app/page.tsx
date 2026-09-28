import Link from "next/link";
import { fetchReport, REPORT_META } from "@/lib/api";
import type { KrCloseData, KrWatchlistData, ReportType, UsCloseData } from "@/lib/types";
import { KrCloseView, KrWatchlistView, UsCloseView } from "@/components/ReportViews";

export const dynamic = "force-dynamic";

async function Slot({ type }: { type: ReportType }) {
  const meta = REPORT_META[type];
  const head = (
    <div className="slot-head">
      <h2>{meta.title}</h2>
      <span className="badge">{meta.slot}</span>
      <Link href={`/report/${type}`} className="more">
        전체 보기 →
      </Link>
    </div>
  );
  if (type === "us-close") {
    const res = await fetchReport<UsCloseData>(type);
    return (
      <section className="slot">
        {head}
        {res.ok ? <UsCloseView r={res.report} compact /> : <p className="muted">{res.message}</p>}
      </section>
    );
  }
  if (type === "kr-watchlist") {
    const res = await fetchReport<KrWatchlistData>(type);
    return (
      <section className="slot">
        {head}
        {res.ok ? <KrWatchlistView r={res.report} compact /> : <p className="muted">{res.message}</p>}
      </section>
    );
  }
  const res = await fetchReport<KrCloseData>(type);
  return (
    <section className="slot">
      {head}
      {res.ok ? <KrCloseView r={res.report} compact /> : <p className="muted">{res.message}</p>}
    </section>
  );
}

export default function Home() {
  return (
    <div className="dashboard">
      <Slot type="us-close" />
      <Slot type="kr-watchlist" />
      <Slot type="kr-close-and-calendar" />
    </div>
  );
}
