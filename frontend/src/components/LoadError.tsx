/**
 * 불러오지 못했을 때.
 *
 * 예전에는 빨간 글씨 한 줄만 남고 표는 **빈 채로** 있었다. 그러면 화면만 봐서는
 * "과제가 없는 것"과 "못 불러온 것"이 구분되지 않는다 — 실제로 목록이 나왔다
 * 안 나왔다 하는 것처럼 보였다.
 *
 * 무엇이 잘못됐는지 말하고, 다시 해 볼 길을 함께 준다.
 */
export default function LoadError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="card load-error">
      <h2>내용을 불러오지 못했습니다</h2>
      <p className="hint">{message}</p>
      <p className="hint">
        잠시 뒤 다시 시도해 보세요. 계속 같은 일이 생기면 <b>설정 › 최근 오류</b>의 내용을
        복사해 알려 주시면 원인을 짚을 수 있습니다.
      </p>
      <div className="form-actions">
        <button onClick={onRetry}>다시 시도</button>
      </div>
    </div>
  );
}
