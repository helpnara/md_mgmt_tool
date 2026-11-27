/**
 * 333 — 카드 · 목록 한 부분을 불러오지 못했을 때 그 자리에 한 줄. 예전에는 조용히 비거나(첨부 0건처럼 보임) 카드가
 * 통째로 사라져 "없는 것"과 "못 불러온 것"이 구분되지 않았다. 권한으로 막힌 것(403)은 부르는 쪽이 숨긴다.
 */
/** 받침이 있으면 "을", 없으면 "를" */
function objectParticle(word: string): string {
  const last = word.trim().charCodeAt(word.trim().length - 1);
  if (last < 0xac00 || last > 0xd7a3) return "을(를)";
  return (last - 0xac00) % 28 ? "을" : "를";
}

export default function InlineRetry({ what, message, onRetry }: { what: string; message?: string | null; onRetry: () => void }) {
  return (
    <p className="inline-load-error" role="alert" data-testid="inline-retry">
      {what}{objectParticle(what)} 불러오지 못했습니다{message ? ` — ${message}` : ""}{" "}
      <button type="button" className="ghost small" onClick={onRetry}>다시 시도</button>
    </p>
  );
}
