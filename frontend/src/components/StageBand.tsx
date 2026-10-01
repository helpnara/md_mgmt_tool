/**
 * 과제명 뒤의 단계 띠 (TODO 175) — 다년도 과제가 몇 단계인지.
 *
 * 선행으로 이어진 과제가 없는 과제(단년도)에는 아무것도 그리지 않는다 — "1단계" 를 모든 과제에 붙이면
 * 띠가 정작 다년도 과제를 가려내지 못한다. 단계는 서버가 센다(projects.assign_stages — 과제 상세 · 로드맵과 같은 규칙).
 */
export default function StageBand({ stage }: { stage?: number | null }) {
  if (stage == null) return null;
  return (
    <span className={`stage-band stage-band-${Math.min(stage, 5)}`} title={`다년도 과제 ${stage}단계 — 선행 과제로 이어진 줄기는 로드맵에서 봅니다`}>
      {stage}단계
    </span>
  );
}
