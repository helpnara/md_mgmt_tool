import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { copyAsPlainText } from "../plaintext";
import type { ErrorEntry } from "../types";
import { formatDateTime } from "../util";

/**
 * 최근 오류.
 *
 * 기록은 `vault/.logs/error-YYYY-MM.log` 에 쌓인다. 그 파일을 탐색기로 찾아 열지 않고
 * 여기서 바로 보고, [복사] 한 번으로 통째로 전달할 수 있게 한다.
 *
 * 남는 것은 **동작과 오류 종류뿐**이고 과제 내용은 담기지 않는다 — 그래야 이 내용을
 * 그대로 붙여 넣어 원인을 물어볼 수 있다.
 */
export default function ErrorLogCard() {
  const [items, setItems] = useState<ErrorEntry[]>([]);
  const [keepMonths, setKeepMonths] = useState(3);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  const load = useCallback(() => {
    api
      .errors()
      .then((data) => {
        setItems(data.items);
        setKeepMonths(data.keep_months);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  useEffect(load, [load]);

  /** 붙여넣기 좋은 평문으로 만든다. 화면 모양이 아니라 읽을 수 있는 줄이어야 한다. */
  function asText(): string {
    return items
      .map((item) => {
        const head = `${item.at}  [${item.status ?? "-"}] ${item.action}`;
        const why = item.detail ? `\n    사유: ${item.detail}` : item.error ? `\n    오류: ${item.error}` : "";
        const trail = item.trail.length > 0 ? `\n    직전: ${item.trail.join(" → ")}` : "";
        return head + why + trail;
      })
      .join("\n");
  }

  async function copy() {
    try {
      await copyAsPlainText(asText());
      setNotice("복사했습니다. 그대로 붙여 넣어 물어보시면 됩니다.");
      window.setTimeout(() => setNotice(null), 4000);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div className="card wide">
      <div className="card-head">
        <h2>최근 오류 ({items.length})</h2>
        <div className="form-actions" style={{ margin: 0 }}>
          <button className="ghost small" onClick={load}>
            다시 읽기
          </button>
          {items.length > 0 && (
            <>
              <button className="ghost small" onClick={() => void copy()}>
                복사
              </button>
              <button
                className="ghost small danger"
                title="문제를 재현하기 전에 비워 두면 그 뒤의 것만 남습니다."
                onClick={async () => {
                  if (!window.confirm("오류 기록을 모두 지울까요?")) return;
                  await api.clearErrors();
                  load();
                }}
              >
                비우기
              </button>
            </>
          )}
        </div>
      </div>

      <p className="hint">
        저장·삭제 같은 동작이 실패하면 여기에 남습니다. 남는 것은 <b>동작과 오류 종류뿐</b>이고
        과제 내용은 담기지 않으므로, [복사]해서 그대로 전달하셔도 됩니다. {keepMonths}개월이
        지난 기록은 자동으로 지워집니다.
      </p>

      {error && <p className="form-error">{error}</p>}
      {notice && <p className="hint notice">{notice}</p>}

      {items.length === 0 ? (
        <p className="hint">기록된 오류가 없습니다.</p>
      ) : (
        <ol className="error-list">
          {(open ? items : items.slice(0, 5)).map((item, index) => (
            <li key={`${item.at}-${index}`}>
              <div className="error-head">
                <span className="error-status">{item.status ?? "실패"}</span>
                <code className="error-action">{item.action}</code>
                <span className="muted">{formatDateTime(item.at)}</span>
              </div>
              {(item.detail || item.error) && (
                <div className="error-detail">{item.detail || item.error}</div>
              )}
              {item.trail.length > 0 && (
                <div className="error-trail">직전: {item.trail.join(" → ")}</div>
              )}
            </li>
          ))}
        </ol>
      )}
      {items.length > 5 && (
        <button className="ghost small" onClick={() => setOpen((prev) => !prev)}>
          {open ? "접기" : `나머지 ${items.length - 5}건 더 보기`}
        </button>
      )}
    </div>
  );
}
