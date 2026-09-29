import { withWeekday } from "@/lib/format";
import type { Envelope } from "@/lib/types";

const STATUS_LABEL = { ok: "정상", partial: "일부 데이터 누락", failed: "생성 실패" } as const;

export function ReportMeta({ report }: { report: Envelope<unknown> }) {
  return (
    <div className="meta">
      <div className="meta-row">
        <span className={`badge status-${report.status}`}>{STATUS_LABEL[report.status]}</span>
        <span>생성 시각 <b>{withWeekday(report.generated_at_kst)}</b></span>
        <span>기준일 {withWeekday(report.report_date_kst)} (KST)</span>
        {report.revision && report.revision > 1 ? <span>재생성 {report.revision}회차</span> : null}
      </div>
      {report.errors.length > 0 && (
        <ul className="alert error">
          {report.errors.map((e) => (
            <li key={e}>{e}</li>
          ))}
        </ul>
      )}
      {report.warnings.length > 0 && (
        <details className="alert warn">
          <summary>참고 사항 {report.warnings.length}건</summary>
          <ul>
            {report.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

export function Sources({ report }: { report: Envelope<unknown> }) {
  return (
    <section className="card sources">
      <h3>출처</h3>
      <ul>
        {report.sources.map((s) => (
          <li key={`${s.name}-${s.used_for}`}>
            <b>{s.name}</b> — {s.used_for}
            {s.fetched_at_kst ? ` (수집 ${s.fetched_at_kst})` : ""}
            {s.stale_cache ? <span className="badge warn"> 캐시 데이터(갱신 실패)</span> : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
