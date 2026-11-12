import type { ExperienceQuant } from "../types";

type Example = { label: string; metric: string; value: string; baseline: string; kind: ExperienceQuant["baseline_kind"]; when: string; note?: string };

/** 대표 예시 — 전극봉 원단위 절감 0.8억원/년: 물량과 금액을 두 줄로 (사용자 2026-11-12) */
export const LEAD_EXAMPLES: Example[] = [
  { label: "물량", metric: "전극봉 원단위", value: "2.10 → 1.85 kg/t-s (−0.25, −12%)", baseline: "개선 전 2024년 연평균", kind: "비교", when: "2025-07 ~ 2025-12 평균" },
  { label: "금액", metric: "전극봉 비용 절감(연환산)", value: "0.8억원/년", baseline: "원단위 감소분 0.25 kg/t × 연 생산량 × 2025 단가", kind: "조건", when: "2025 하반기 실적 연환산" },
];

/** 여러 경우 — 종류(비교 · 집계 · 조건 · 미확인)가 고루 나오게 */
export const MORE_EXAMPLES: Example[] = [
  { label: "품질", metric: "표면 결함 불량률", value: "1.8% → 0.9%", baseline: "적용 전 3개월 평균", kind: "비교", when: "2025-04 ~ 06" },
  { label: "원가(물량)", metric: "산소 원단위", value: "52 → 48 Nm³/t", baseline: "기존 조업 표준", kind: "비교", when: "2025 하반기" },
  { label: "원가(금액)", metric: "부원료 비용 절감", value: "1.2억원/년", baseline: "절감량 × 2025 단가 × 연 생산량", kind: "조건", when: "2025 실적 연환산" },
  { label: "에너지", metric: "가열로 연료 원단위", value: "1.32 → 1.25 Gcal/t", baseline: "전년 동기", kind: "비교", when: "2025-01 ~ 06" },
  { label: "생산성", metric: "시간당 처리량", value: "85 → 93 t/h", baseline: "개선 전 1개월 평균", kind: "비교", when: "2025-09" },
  { label: "설비", metric: "비계획 정지 시간", value: "월 14 → 5시간", baseline: "2024년 월평균", kind: "비교", when: "2025 월평균" },
  { label: "리드타임", metric: "시험 결과 회신 시간", value: "3일 → 4시간", baseline: "기존 수기 집계 절차", kind: "비교", when: "2025-05 이후" },
  { label: "업무 자동화", metric: "수기 작업 시간", value: "주 6시간 → 0.5시간", baseline: "기존 엑셀 수작업", kind: "비교", when: "2025-03 이후" },
  { label: "AI 모델", metric: "결함 판정 정확도", value: "92.4% (재현율 95%)", baseline: "검증 데이터 3,000장, 사람 판정 대비", kind: "조건", when: "2025-08 검증" },
  { label: "예측", metric: "수요 예측 오차(MAPE)", value: "18% → 9%", baseline: "기존 이동평균 방식", kind: "비교", when: "2025 1 ~ 3분기" },
  { label: "확산", metric: "적용 라인 수", value: "4개 라인", baseline: "누적(2024 ~ 2025)", kind: "집계", when: "2025-12 기준" },
  { label: "사용", metric: "월 사용자 수", value: "120명", baseline: "사내 시스템 접속 기록, 월평균", kind: "집계", when: "2025 하반기" },
  { label: "안전", metric: "위험 작업 횟수", value: "연 40 → 6회", baseline: "자동화 전 2024년", kind: "비교", when: "2025" },
  { label: "교육 · 육성", metric: "교육 수료 인원", value: "35명", baseline: "과정 누적 수료", kind: "집계", when: "2024 ~ 2025" },
  { label: "성과물", metric: "특허 출원", value: "2건", baseline: "누적", kind: "집계", when: "2025" },
  { label: "기준이 없을 때", metric: "판정 기준서 정비", value: "12개 항목", baseline: "기준 없음", kind: "미확인", when: "2025", note: "확인 뒤 집계로" },
];

/**
 * 결과 · 정량 작성 예시 (TODO 283). 경험 상세의 결과 · 정량 표 아래 "작성 예시 ▾" · 도움말이 함께 쓴다.
 * `onPick` 을 주면(고칠 수 있는 경험) 예시 줄마다 [표에 넣기] — 넣은 뒤 숫자 · 기간을 제 것으로 고쳐 쓴다.
 */
export default function QuantGuide({ onPick }: { onPick?: (quant: ExperienceQuant) => void }) {
  const row = (example: Example) => (
    <tr key={example.label + example.metric}>
      <th scope="row" className="muted">{example.label}</th>
      <td>{example.metric}</td>
      <td>{example.value}</td>
      <td>{example.baseline}</td>
      <td>{example.kind}{example.note ? <span className="muted"> → {example.note}</span> : null}</td>
      <td>{example.when}</td>
      {onPick && (
        <td>
          <button type="button" className="ghost small" title="이 줄을 표에 넣습니다 — 숫자 · 기간을 제 것으로 고쳐 쓰세요"
            onClick={() => onPick({ metric: example.metric, value: example.value, baseline: example.baseline, baseline_kind: example.kind, when: example.when })}>
            표에 넣기
          </button>
        </td>
      )}
    </tr>
  );
  const head = (
    <thead><tr><th /><th>지표</th><th>값</th><th>기준</th><th>종류</th><th>시점</th>{onPick && <th />}</tr></thead>
  );
  return (
    <div className="quant-guide" data-testid="quant-guide">
      <table className="grid quant-guide-meaning">
        <tbody>
          <tr><th scope="row">지표</th><td>무엇을 쟀나 — 명사로 짧게, 단위는 빼고(예: 전극봉 원단위 · 불량률)</td></tr>
          <tr><th scope="row">값</th><td>얼마였나 — <b>단위를 꼭</b>, 가능하면 <b>"전 → 후"</b>(예: 2.10 → 1.85 kg/t, −12%)</td></tr>
          <tr><th scope="row">기준</th><td>무엇과 견줬나 — 비교 대상 · 집계 범위 · 환산 가정. 없으면 "기준 없음"</td></tr>
          <tr><th scope="row">종류</th><td>
            <b>비교</b> 이전 · 기존 방식 · 다른 조건과 견줌 — 이때만 업무 이력 파일에 "개선 · 단축 · 증가" ·{" "}
            <b>집계</b> 누적 · 연간 · 건수 · <b>조건</b> 단가 · 생산량 같은 가정으로 환산 · <b>미확인</b> 아직 모름 — 남아 있으면 확정이 안 됩니다
          </td></tr>
          <tr><th scope="row">시점</th><td>언제 값인가 — 측정 기간 · 해, <b>실적</b>인지 <b>계획(기대)</b>인지도</td></tr>
        </tbody>
      </table>
      <p className="quant-guide-title"><b>대표 예시 — 전극봉 원단위 절감 0.8억원/년</b> · 물량과 금액은 <b>두 줄로</b> 나눕니다(금액은 단가 · 생산량을 가정한 환산이라 "조건")</p>
      <div className="table-scroll"><table className="grid quant-guide-table">{head}<tbody>{LEAD_EXAMPLES.map(row)}</tbody></table></div>
      <p className="hint">팀 전체 효과라면 <b>역할</b> 칸에 본인 몫을 적어 두세요(예: "조업 조건 분석 · 시험 설계는 본인, 설비 개조는 설비팀") — 초안의 "본인이 기여한 몫은?" 질문이 그 자리입니다.</p>
      <details className="quant-guide-more">
        <summary>여러 경우 예시 {MORE_EXAMPLES.length}가지</summary>
        <div className="table-scroll"><table className="grid quant-guide-table">{head}<tbody>{MORE_EXAMPLES.map(row)}</tbody></table></div>
      </details>
      <p className="quant-guide-title"><b>자주 하는 실수</b></p>
      <ul className="quant-guide-mistakes">
        <li><b>단위가 빠진 값</b> — "12% 절감" 만으로는 무엇의 12%인지 모릅니다.</li>
        <li><b>기준 없이 "개선 · 단축"</b> — 기준이 없으면 "기준 없음 · 미확인" 으로 두고 확인 필요 질문으로.</li>
        <li><b>한 줄에 두 지표</b> — "원단위 12% 절감, 0.8억원/년" 은 두 줄로.</li>
        <li><b>실적과 기대효과 섞기</b> — 시점에 "실적" · "계획(기대)" 을 남깁니다.</li>
      </ul>
    </div>
  );
}
