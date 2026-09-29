import type { KrCompany, WatchSector as WS } from "@/lib/types";

const CRIT = [
  ["supply_chain", "공급망"],
  ["sensitivity", "실적민감"],
  ["theme", "테마"],
] as const;

const cls = (v: number | null | undefined) => (!v ? "flat" : v > 0 ? "up" : "down");
const fmt = (v: number) => (v > 0 ? `+${v}` : v < 0 ? `−${Math.abs(v)}` : "0");

function Score({ c }: { c: KrCompany }) {
  if (c.score === undefined) {
    // 2026-09-29 이전 리포트(부호 없는 관련도 형식)
    return <span className="muted">관련도 {(c.relevance * 100).toFixed(0)}</span>;
  }
  if (c.score === null) {
    return (
      <span className="muted">
        방향 미판정
        <div className="tiny">관련도 {(c.relevance * 100).toFixed(0)}</div>
      </span>
    );
  }
  return (
    <span className={`score ${cls(c.score)}`}>
      <b>{fmt(c.score)}</b>
      <div className="tiny">{c.label}</div>
    </span>
  );
}

export function WatchSectorCard({ s }: { s: WS }) {
  return (
    <section className="card sector">
      <h3>{s.kr_sector} 섹터</h3>
      <p className="watch">{s.watch_point}</p>
      {s.us_tickers.length > 0 && <div className="small muted">관련 미국 종목: {s.us_tickers.join(", ")}</div>}
      <details className="small">
        <summary>근거 뉴스 {s.news_refs.length}건</summary>
        <ul>
          {s.news_refs.map((r) => (
            <li key={`${r.rank}-${r.title}`}>
              #{r.rank} {r.title}
            </li>
          ))}
        </ul>
      </details>
      <table className="table companies">
        <thead>
          <tr>
            <th>관련기업 (영향 큰 순)</th>
            <th className="c-score">점수</th>
            <th className="c-detail">세부 (공급망·실적민감·테마)</th>
          </tr>
        </thead>
        <tbody>
          {s.companies.map((c) => (
            <tr key={c.code}>
              <td>
                <b>{c.name}</b> <span className="small muted">{c.code} · {c.market}</span>
                <div className="small">
                  {c.rationale}
                  {c.rationale_origin === "llm" ? <span className="badge ai">AI 추론</span> : null}
                </div>
                {c.llm_rationale && c.rationale_origin === "rule" ? (
                  <div className="small muted">
                    {c.llm_rationale}
                    <span className="badge ai">AI 판단</span>
                  </div>
                ) : null}
              </td>
              <td className="c-score">
                <Score c={c} />
              </td>
              <td className="c-detail small">
                {c.scores && c.score !== undefined
                  ? CRIT.map(([k, label]) => (
                      <div key={k}>
                        {label} <span className={cls(c.scores?.[k])}>{fmt(c.scores?.[k] ?? 0)}</span>
                      </div>
                    ))
                  : c.magnitudes
                    ? CRIT.map(([k, label]) => (
                        <div key={k} className="muted">
                          {label} 관련도 {((c.magnitudes?.[k] ?? 0) * 100).toFixed(0)}
                        </div>
                      ))
                    : <span className="muted">—</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
