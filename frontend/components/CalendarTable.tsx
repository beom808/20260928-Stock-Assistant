import type { CalendarRow } from "@/lib/types";

const ARROW = { up: "↑", down: "↓", flat: "→" } as const;

function Recent({ r }: { r: CalendarRow }) {
  const h = r.history;
  if (h && h.points.length > 0) {
    return (
      <>
        <div className="recent">
          {h.points.map((p) => (
            <span key={p.period} className="recent-item">
              {p.period} {p.text}
              {p.dir ? <span className={p.dir}>{ARROW[p.dir]}</span> : null}
            </span>
          ))}
        </div>
        {h.extra ? <div className="tiny">{h.extra}</div> : null}
        <div className="tiny muted">{h.label}</div>
      </>
    );
  }
  // 실적발표: EPS 예상치 / 이전 형식 리포트: 문자열 그대로
  if (r.kind === "실적발표" && r.consensus) return <span className="small">{r.consensus}</span>;
  if (r.previous) return <span className="small">{r.previous}</span>;
  return <span className="muted">—</span>;
}

export function CalendarTable({ rows, windowKst }: { rows: CalendarRow[]; windowKst: string }) {
  return (
    <section className="card">
      <h3>익일 미국 시장 이벤트</h3>
      <div className="small muted">조회 구간 {windowKst} · 서머타임 자동 반영</div>
      {rows.length === 0 ? (
        <p className="muted">확인된 이벤트가 없습니다(또는 캘린더 수집 실패 — 상단 참고 사항 확인).</p>
      ) : (
        <table className="table calendar">
          <thead>
            <tr>
              <th>이벤트</th>
              <th>종류</th>
              <th>미국(ET)</th>
              <th>한국(KST)</th>
              <th>최근 4회</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={`${r.event}-${r.et}`}>
                <td>{r.event}</td>
                <td>
                  <span className={`badge kind-${r.kind === "FOMC" ? "fomc" : r.kind === "실적발표" ? "earn" : "macro"}`}>
                    {r.kind}
                  </span>
                </td>
                <td>{r.et}</td>
                <td>
                  <b>{r.kst}</b>
                </td>
                <td>
                  <Recent r={r} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
