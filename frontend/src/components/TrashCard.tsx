import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { TrashItem } from "../types";
import { formatDateTime } from "../util";

/**
 * 삭제 보관함.
 *
 * 이 도구는 아무것도 진짜로 지우지 않고 `.trash/` 로 옮기기만 한다. 그런데 되돌리려면
 * 탐색기를 열고 폴더 구조를 눈으로 짚어야 했다. 실수 한 번이면 바로 필요해지는 화면이다.
 */
export default function TrashCard() {
  const [items, setItems] = useState<TrashItem[]>([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api.trash().then(setItems).catch((err: Error) => setError(err.message));
  }, []);

  useEffect(load, [load]);

  async function restore(item: TrashItem) {
    setBusy(item.trash_name);
    setError(null);
    try {
      const result = await api.restoreFromTrash(item.trash_name);
      const count = item.attachments?.length ?? 0;
      const left = result.attachments_left ?? [];
      // 함께 옮긴 첨부도 돌아온다 (TODO 218). 막혀 남은 것은 제 줄로 보관함에 남는다
      setNotice(
        `${result.label} 을(를) 되돌렸습니다.` +
          (count > left.length ? ` 첨부 ${count - left.length}개도 함께 돌아왔습니다.` : "") +
          (left.length > 0 ? ` 첨부 ${left.length}개(${left.join(", ")})는 다른 프로그램이 잡고 있어 보관함에 남았습니다 — 닫고 하나씩 되돌려 주세요.` : ""),
      );
      window.setTimeout(() => setNotice(null), 4000);
      load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="card">
      <div className="card-head">
        <h2>삭제 보관함 {items.length}건</h2>
        {items.length > 0 && (
          <button className="ghost" onClick={() => setOpen((value) => !value)}>
            {open ? "접기" : "펼치기"}
          </button>
        )}
      </div>
      <p className="hint">
        지운 과제·진행일지·보고·첨부는 삭제되지 않고 여기에 남습니다. 되돌리면 원래 자리로 돌아갑니다.
      </p>
      {notice && <p className="hint notice">{notice}</p>}
      {error && <p className="form-error">{error}</p>}
      {items.length === 0 && <p className="hint">보관함이 비어 있습니다.</p>}

      {open && items.length > 0 && (
        <ul className="trash-list">
          {items.map((item) => (
            <li key={item.trash_name}>
              <span className="trash-kind">{item.kind_label ?? "기록 없음"}</span>
              <span
                className="trash-label"
                title={[item.origin ?? item.trash_name, ...(item.attachments ?? []).map((name) => `· ${name}`)].join("\n")}
              >
                {item.label}
                {(item.attachments?.length ?? 0) > 0 && (
                  <span className="muted trash-with"> · 첨부 {item.attachments!.length}개 함께</span>
                )}
              </span>
              <span className="muted trash-when">
                {item.deleted_at ? formatDateTime(item.deleted_at) : "—"}
              </span>
              {item.restorable ? (
                <button data-write
                  className="ghost small"
                  disabled={busy !== null}
                  onClick={() => void restore(item)}
                >
                  {busy === item.trash_name ? "되돌리는 중…" : "되돌리기"}
                </button>
              ) : (
                <span
                  className="muted trash-note"
                  title="이 기능이 생기기 전에 지운 항목이라 어디로 되돌릴지 알 수 없습니다. 보관함 폴더에서 직접 옮겨 주세요."
                >
                  수동
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
