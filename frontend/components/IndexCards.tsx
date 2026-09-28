import type { IndexQuote } from "@/lib/types";
import { num, pct, trendClass } from "@/lib/format";

export function IndexCards({ items }: { items: IndexQuote[] }) {
  return (
    <div className="index-grid">
      {items.map((q) => (
        <div className="card index" key={q.name}>
          <div className="index-name">
            {q.name}
            {q.is_proxy ? <span className="badge warn">ETF 대체</span> : null}
          </div>
          {q.error ? (
            <div className="muted">데이터 없음</div>
          ) : (
            <>
              <div className={`index-pct ${trendClass(q.change_pct)}`}>{pct(q.change_pct)}</div>
              <div className="muted">
                {num(q.close)} ({q.change && q.change > 0 ? "+" : ""}
                {num(q.change)})
              </div>
            </>
          )}
          {q.note ? <div className="small muted">{q.note}</div> : null}
          {q.as_of_kst ? <div className="small muted">데이터 시각 {q.as_of_kst}</div> : null}
        </div>
      ))}
    </div>
  );
}
