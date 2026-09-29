import type { FxRate, IndexQuote, MacroStat } from "@/lib/types";
import { num, pct, signed, trendClass } from "@/lib/format";

// 지수 카드를 한 줄에 나란히(fx 를 주면 같은 줄 끝에 환율 카드). caption: 카드 공통 기준 문구
export function IndexCards({ items, fx, caption }: { items: IndexQuote[]; fx?: FxRate | null; caption?: string }) {
  const n = items.length + (fx ? 1 : 0);
  return (
    <div className="index-grid" style={{ gridTemplateColumns: `repeat(${n}, minmax(0, 1fr))` }}>
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
              <div className="index-val">
                {num(q.close)} <span className={trendClass(q.change)}>({signed(q.change)})</span>
              </div>
            </>
          )}
          {caption ? <div className="small muted">{caption}</div> : null}
          {q.note ? <div className="small muted">{q.note}</div> : null}
        </div>
      ))}
      {fx ? <FxCard fx={fx} /> : null}
    </div>
  );
}

export function FxCard({ fx }: { fx: FxRate }) {
  return (
    <div className="card index">
      <div className="index-name">원/달러 환율</div>
      <div className={`index-pct ${trendClass(fx.change)}`}>{num(fx.rate)}</div>
      <div className="index-val">
        <span className={trendClass(fx.change)}>{signed(fx.change)}</span> ({pct(fx.change_pct)})
      </div>
      <div className="small muted">{fx.note}</div>
    </div>
  );
}

// 매크로 지표 한 줄(작은 카드) — 환율(fx)을 앞에 둘 수 있다
export function MacroStrip({ items, fx }: { items: MacroStat[]; fx?: FxRate | null }) {
  const ok = items.filter((m) => !m.error && m.value !== null && m.value !== undefined);
  if (!fx && ok.length === 0) return null;
  return (
    <div className="macro-grid">
      {fx ? (
        <div className="card mini">
          <div className="mini-name">원/달러 (ECB)</div>
          <div className="mini-val">
            {num(fx.rate)} <span className={`small ${trendClass(fx.change)}`}>{signed(fx.change)}</span>
          </div>
          <div className="tiny muted">{fx.note}</div>
        </div>
      ) : null}
      {ok.map((m) => (
        <div className="card mini" key={m.name}>
          <div className="mini-name">{m.name}</div>
          <div className="mini-val">
            {num(m.value)}
            {m.unit ?? ""}{" "}
            <span className={`small ${trendClass(m.change)}`}>{signed(m.change)}</span>
          </div>
          <div className="tiny muted">{m.note ?? (m.date ? `${m.date.slice(5).replace("-", "/")} 기준` : "")}</div>
        </div>
      ))}
    </div>
  );
}
