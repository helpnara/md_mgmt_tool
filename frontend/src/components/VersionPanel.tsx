import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { DocumentVersion } from "../types";
import { formatBytes } from "../upload";

/**
 * 이 문서의 이전 버전.
 *
 * `.trash` 는 **지웠을 때**를 막아 준다. 더 자주 나는 사고는 **잘못 고쳐 저장한 것**이라,
 * 문서를 보고 있는 자리에서 바로 되돌릴 수 있어야 한다 — 설정 화면까지 찾아가게 하면
 * 정작 필요한 순간에 못 쓴다.
 */
export default function VersionPanel({ path, onRestored }: { path: string; onRestored: () => void }) {
  const [items, setItems] = useState<DocumentVersion[] | null>(null);
  const [preview, setPreview] = useState<{ stamp: string; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api.versions(path).then((data) => setItems(data.items)).catch((err: Error) => setError(err.message));
  }, [path]);

  useEffect(load, [load]);

  if (error) return <p className="form-error">{error}</p>;
  if (items === null) return <p className="hint">불러오는 중…</p>;

  return (
    <div className="version-panel">
      {items.length === 0 ? (
        <p className="hint">
          아직 남아 있는 이전 버전이 없습니다. <b>이 문서를 고쳐 저장하면</b> 그 직전 내용이
          여기에 남습니다.
        </p>
      ) : (
        <>
          <p className="hint">
            고쳐 저장할 때마다 <b>직전 내용</b>이 남습니다. 되돌리기도 하나의 저장이라,
            되돌린 뒤에 다시 되돌릴 수 있습니다.
          </p>
          <ol className="version-list">
            {items.map((item) => (
              <li key={item.stamp} className={preview?.stamp === item.stamp ? "open" : undefined}>
                <div className="version-head">
                  <span className="version-when">{item.saved_at}</span>
                  <span className="muted">{formatBytes(item.size_bytes)}</span>
                  <button
                    className="ghost small"
                    onClick={async () => {
                      if (preview?.stamp === item.stamp) {
                        setPreview(null);
                        return;
                      }
                      try {
                        const data = await api.versionContent(path, item.stamp);
                        setPreview({ stamp: item.stamp, text: data.text });
                      } catch (err) {
                        setError((err as Error).message);
                      }
                    }}
                  >
                    {preview?.stamp === item.stamp ? "닫기" : "내용 보기"}
                  </button>
                  <button
                    className="ghost small"
                    disabled={busy}
                    onClick={async () => {
                      if (!window.confirm(`${item.saved_at} 내용으로 되돌릴까요? 지금 내용도 버전으로 남습니다.`))
                        return;
                      setBusy(true);
                      setError(null);
                      try {
                        await api.restoreVersion(path, item.stamp);
                        setPreview(null);
                        load();
                        onRestored();
                      } catch (err) {
                        setError((err as Error).message);
                      } finally {
                        setBusy(false);
                      }
                    }}
                  >
                    되돌리기
                  </button>
                </div>
                {preview?.stamp === item.stamp && <pre className="version-preview">{preview.text}</pre>}
              </li>
            ))}
          </ol>
        </>
      )}
    </div>
  );
}
