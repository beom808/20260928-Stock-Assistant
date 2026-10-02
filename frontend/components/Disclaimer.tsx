// 모든 화면 맨 아래에 작게 표시되는 면책 문구 (layout.tsx 에서 렌더)
export const DISCLAIMER =
  "본 서비스는 공개 데이터와 AI 요약을 활용한 정보 제공·리서치 보조 도구이며, 투자자문이나 특정 종목의 매수·매도 추천이 아닙니다. 데이터에는 지연·오류가 있을 수 있으며, 모든 투자 판단과 그 결과에 대한 책임은 투자자 본인에게 있습니다.";

export function Disclaimer() {
  return (
    <footer className="disclaimer" role="note" aria-label="면책 고지">
      <strong>투자 조언 아님</strong> · {DISCLAIMER}
    </footer>
  );
}
