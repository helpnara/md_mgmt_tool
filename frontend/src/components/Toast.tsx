import { useEffect, useState } from "react";
import { onNotify } from "../notify";

/**
 * 실패 알림 (TODO 161). 화면 아래 가운데에 쌓이고 10초 뒤 사라진다. [×] 로 먼저 닫을 수 있다.
 * 같은 글이 겹쳐 오면(두 번 누름) 하나로 둔다.
 */
export default function Toast() {
  const [items, setItems] = useState<{ id: number; message: string }[]>([]);
  useEffect(
    () =>
      onNotify((message) => {
        const id = Date.now() + Math.random();
        setItems((prev) => (prev.some((item) => item.message === message) ? prev : [...prev, { id, message }].slice(-3)));
        window.setTimeout(() => setItems((prev) => prev.filter((item) => item.id !== id)), 10000);
      }),
    [],
  );
  if (items.length === 0) return null;
  return (
    <div className="toast-stack" role="alert" aria-live="assertive">
      {items.map((item) => (
        <div key={item.id} className="toast">
          <span className="toast-mark" aria-hidden="true">!</span>
          <span className="toast-text">{item.message}</span>
          <button
            className="ghost small"
            aria-label="알림 닫기"
            onClick={() => setItems((prev) => prev.filter((other) => other.id !== item.id))}
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}
