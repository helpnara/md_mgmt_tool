/**
 * 화면 어디서나 실패를 알리는 한 자리 (TODO 161).
 *
 * 저장 · 삭제가 실패해도 **단추를 눌러도 아무 일이 없는 것처럼** 보이던 자리가 다섯 곳 있었다
 * (서버가 "파일이 다른 프로그램에서 열려 있습니다" 를 돌려줘도 콘솔에만 남았다). 자리마다 오류 칸을
 * 새로 만들지 않고, 화면 아래 **알림 한 곳**(Toast)으로 모은다. 처리하지 않은 실패도 여기로 온다(main.tsx).
 */
type Listener = (message: string) => void;
const listeners = new Set<Listener>();

export function notifyError(message: string): void {
  for (const listener of listeners) listener(message);
}

export function onNotify(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/**
 * 동작 하나를 시도하고, 실패하면 알린다. **성공했는가**를 돌려준다.
 * (결과 값으로 성공을 가리면 안 된다 — 지우기처럼 성공해도 아무것도 돌려주지 않는 요청이 있다.)
 */
export async function attempt(action: () => Promise<unknown>): Promise<boolean> {
  try {
    await action();
    return true;
  } catch (err) {
    notifyError((err as Error)?.message || "요청에 실패했습니다.");
    return false;
  }
}

/**
 * 화면 쪽 오류를 **최근 오류 기록**에 남긴다 (TODO 166). 과제 내용은 보내지 않는다 — 화면 이름 ·
 * 오류 종류 · 메시지(300자)만. 보내다 실패해도 조용히 넘어간다(기록 때문에 사용자가 막히면 안 된다).
 */
export function reportClientError(kind: string, message: string): void {
  const screen = window.location.hash.replace(/^#\/?/, "").split(/[/?]/)[0] || "home";
  void fetch("/api/errors/client", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ screen: screen.slice(0, 80), kind: kind.slice(0, 40), message: message.slice(0, 300) }),
  }).catch(() => undefined);
}
