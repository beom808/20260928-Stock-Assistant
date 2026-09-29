import type { Envelope, InvestorFlow, KrCloseData, KrWatchlistData, UsCloseData } from "@/lib/types";
import { eok, trendClass, withWeekday } from "@/lib/format";
import { CalendarTable } from "./CalendarTable";
import { IndexCards, MacroStrip } from "./IndexCards";
import { NewsCard } from "./NewsCard";
import { ReportMeta, Sources } from "./ReportMeta";
import { WatchSectorCard } from "./WatchSector";

export function UsCloseView({ r, compact = false }: { r: Envelope<UsCloseData>; compact?: boolean }) {
  const d = r.data;
  const news = compact ? d.news.slice(0, 3) : d.news;
  return (
    <>
      <ReportMeta report={r} />
      <p className="small muted">
        기준 세션 {withWeekday(d.session_date_et)} (미국 동부) · 정규장 마감 {withWeekday(d.session_close_kst)} (
        {d.session_close_tz} 기준)
      </p>
      <IndexCards items={d.indices} />
      <MacroStrip items={d.macro ?? []} fx={d.fx} />
      <h3>
        주요 이슈 {d.news.length}건{" "}
        <span className="small muted">({d.ranking_method === "llm" ? "AI 분류" : "규칙 기반 분류"})</span>
      </h3>
      {!compact && <p className="small muted">선정 기준: {d.selection_criteria.join(" > ")}</p>}
      <div className="news-list">
        {news.map((n) => (
          <NewsCard key={n.rank} n={n} />
        ))}
      </div>
      {!compact && <Sources report={r} />}
    </>
  );
}

export function KrWatchlistView({ r, compact = false }: { r: Envelope<KrWatchlistData>; compact?: boolean }) {
  const d = r.data;
  const sectors = compact ? d.sectors.slice(0, 2) : d.sectors;
  return (
    <>
      <ReportMeta report={r} />
      {d.macro_points.length > 0 && (
        <section className="card">
          <h3>시장 전반(매크로) 관전 포인트</h3>
          <ul>
            {d.macro_points.map((m) => (
              <li key={m.rank}>
                #{m.rank} {m.title}
              </li>
            ))}
          </ul>
        </section>
      )}
      {sectors.map((s) => (
        <WatchSectorCard key={s.key} s={s} />
      ))}
      {!compact && d.weights.same_industry === undefined && (
        <p className="small muted">
          점수(−100~+100) = 공급망 {Math.round((d.weights.supply_chain ?? 0) * 100)}% · 실적민감{" "}
          {Math.round((d.weights.sensitivity ?? 0) * 100)}% · 테마 {Math.round((d.weights.theme ?? 0) * 100)}% 가중합 · +
          수혜 / − 악재 ({d.method === "hybrid" ? "관련 강도: 정적 규칙 + AI, 방향: AI 판단" : "AI 미사용 — 방향 미판정"}).
          주가 등락률 예측이 아닙니다.
        </p>
      )}
      {!compact && <Sources report={r} />}
    </>
  );
}

export function KrCloseView({ r, compact = false }: { r: Envelope<KrCloseData>; compact?: boolean }) {
  const d = r.data;
  return (
    <>
      <ReportMeta report={r} />
      <IndexCards items={d.indices} fx={d.fx} caption="15:30 종가 기준" />
      {d.investor_flows && d.investor_flows.length > 0 ? <Flows flows={d.investor_flows} /> : null}
      <section className="card">
        <h3>
          오늘의 국내 주요 이슈 {d.issues.length}건 <span className="small muted">(지수 영향 큰 순)</span>
        </h3>
        {d.issues.length === 0 ? (
          <p className="muted">확인된 이슈가 없습니다(뉴스 수집 미설정 또는 실패).</p>
        ) : (
          <ol className="issues">
            {(compact ? d.issues.slice(0, 5) : d.issues).map((i) => (
              <li key={i.rank}>
                {i.url ? (
                  <a href={i.url} target="_blank" rel="noopener noreferrer">
                    {i.title} ↗
                  </a>
                ) : (
                  <span>
                    {i.title} <span className="small muted">(원문 링크 없음)</span>
                  </span>
                )}
                <div className="small">
                  {i.summary}
                  {i.summary_origin === "llm" ? <span className="badge ai">AI 요약</span> : null}
                </div>
                <div className="small muted">
                  {i.source} · {i.published_at_kst}
                </div>
              </li>
            ))}
          </ol>
        )}
      </section>
      <CalendarTable rows={compact ? d.us_calendar.rows.slice(0, 5) : d.us_calendar.rows} windowKst={d.us_calendar.window_kst} />
      {!compact && <Sources report={r} />}
    </>
  );
}

function Flows({ flows }: { flows: InvestorFlow[] }) {
  return (
    <section className="card">
      <h3>
        투자자별 순매수 <span className="small muted">(KRX · 억원 · 장 마감 직후 잠정치)</span>
      </h3>
      <table className="table flows">
        <thead>
          <tr>
            <th>시장</th>
            <th>외국인</th>
            <th>기관</th>
            <th>개인</th>
          </tr>
        </thead>
        <tbody>
          {flows.map((f) => (
            <tr key={f.market}>
              <td>{f.market === "KOSPI" ? "코스피" : f.market === "KOSDAQ" ? "코스닥" : f.market}</td>
              {([f.foreign, f.institution, f.retail] as const).map((v, i) => (
                <td key={i} className={`num ${trendClass(v)}`}>
                  {eok(v)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
