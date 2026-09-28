import type { WatchSector as WS } from "@/lib/types";

const CRIT = [
  ["same_industry", "동일산업"],
  ["supply_chain", "공급망"],
  ["sensitivity", "실적민감"],
  ["theme", "테마"],
] as const;

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
      <table className="table">
        <thead>
          <tr>
            <th>관련기업 (관련도 순)</th>
            <th>관련도</th>
            <th className="hide-sm">세부 점수</th>
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
              </td>
              <td className="num">{(c.relevance * 100).toFixed(0)}</td>
              <td className="hide-sm small">
                {CRIT.map(([k, label]) => `${label} ${(c.scores[k] * 100).toFixed(0)}`).join(" · ")}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
