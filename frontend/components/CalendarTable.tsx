import type { CalendarRow } from "@/lib/types";

export function CalendarTable({ rows, windowKst }: { rows: CalendarRow[]; windowKst: string }) {
  return (
    <section className="card">
      <h3>익일 미국 시장 이벤트</h3>
      <div className="small muted">조회 구간 {windowKst} · 서머타임 자동 반영</div>
      {rows.length === 0 ? (
        <p className="muted">확인된 이벤트가 없습니다(또는 캘린더 수집 실패 — 상단 참고 사항 확인).</p>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>이벤트명</th>
                <th>종류</th>
                <th>미국시각(ET)</th>
                <th>한국시각(KST)</th>
                <th>컨센서스</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={`${r.event}-${r.et}`}>
                  <td>
                    {r.event}
                    {r.note ? <div className="small muted">{r.note}</div> : null}
                  </td>
                  <td>
                    <span className={`badge kind-${r.kind === "FOMC" ? "fomc" : r.kind === "실적발표" ? "earn" : "macro"}`}>
                      {r.kind}
                    </span>
                  </td>
                  <td className="nowrap-md">{r.et}</td>
                  <td className="nowrap-md">
                    <b>{r.kst}</b>
                  </td>
                  <td>
                    {r.consensus ?? <span className="muted">—</span>}
                    {r.previous ? <div className="small muted">이전 {r.previous}</div> : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
