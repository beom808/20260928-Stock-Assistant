import type { UsNews } from "@/lib/types";
import { utcToKst } from "@/lib/format";

export function NewsCard({ n }: { n: UsNews }) {
  const body = (
    <>
      <div className="news-head">
        <span className="rank">{n.rank}</span>
        <span className={`badge tier-${n.tier}`}>{n.tier_label}</span>
        <span className="small muted">
          {n.source} · {utcToKst(n.published_at_utc)}
        </span>
      </div>
      <h4 className="news-title">{n.title_ko ?? n.title}</h4>
      {n.title_ko ? <div className="small muted">{n.title}</div> : null}
      <p className="news-summary">
        {n.summary}
        {n.summary_origin === "llm" ? <span className="badge ai">AI 요약</span> : null}
      </p>
      <div className="chips">
        {n.sectors.map((s) => (
          <span className="chip" key={s.key}>
            {s.label}
          </span>
        ))}
        {n.tickers.map((t) => (
          <span className="chip ticker" key={t}>
            {t}
          </span>
        ))}
      </div>
      <div className="news-link">{n.url ? "원문 보기 ↗" : <span className="muted">원문 링크 없음</span>}</div>
    </>
  );
  // 탭(클릭) 시 새 창(외부 브라우저 탭)으로 API 가 준 원문 URL 을 연다
  return n.url ? (
    <a className="card news clickable" href={n.url} target="_blank" rel="noopener noreferrer">
      {body}
    </a>
  ) : (
    <div className="card news">{body}</div>
  );
}
