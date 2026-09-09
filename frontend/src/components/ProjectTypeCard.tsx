import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { ProjectTypeRow } from "../types";
import { typeClass } from "./StatusBadge";

/**
 * 과제 속성 더하고 빼고 고치기 (TODO 100).
 *
 * 속성은 오래 **코드에 박힌 목록**이었다. 팀마다 쓰는 말이 다르고, 하나 더하려면
 * 개발자를 불러야 했다.
 *
 * 화면이 지켜야 할 것 둘.
 *
 * 1. **이름을 고쳐도 과제는 속성을 잃지 않는다.** 과제 파일에 남는 것은 *열쇠*이고
 *    여기서 고치는 것은 *이름*이다. 그래서 줄마다 열쇠를 그대로 들고 다닌다.
 * 2. **쓰고 있는 속성은 뺄 수 없다.** 몇 건이 쓰는지 줄마다 적어 두고, 0건일 때만
 *    [빼기]가 켜진다. 서버도 같은 것을 한 번 더 막는다.
 */
export default function ProjectTypeCard({ onSaved }: { onSaved: () => void }) {
  const [rows, setRows] = useState<ProjectTypeRow[] | null>(null);
  const [saved, setSaved] = useState<ProjectTypeRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .projectTypes()
      .then((data) => {
        setRows(data.types);
        setSaved(data.types);
        setError(null);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  useEffect(load, [load]);

  if (!rows) return null;

  const changed = JSON.stringify(rows) !== JSON.stringify(saved);

  const update = (index: number, label: string) =>
    setRows(rows.map((row, at) => (at === index ? { ...row, label } : row)));

  const move = (index: number, step: number) => {
    const next = [...rows];
    const target = index + step;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    setRows(next);
  };

  async function save() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const data = await api.saveProjectTypes(
        (rows ?? []).map((row) => ({ key: row.key, label: row.label })),
      );
      setRows(data.types);
      setSaved(data.types);
      setNotice("저장했습니다.");
      window.setTimeout(() => setNotice(null), 3000);
      // 거르기 상자·대시보드·서식 갈래가 모두 이 목록을 본다. 함께 다시 읽는다.
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h2>과제 속성</h2>
      <p className="hint">
        과제를 만들 때 고르는 <b>성격</b>입니다. 팀에서 쓰는 말로 더하고 빼고 고칠 수 있습니다.
        <br />
        <b>이름을 고쳐도 이미 만든 과제는 속성을 잃지 않습니다</b> — 과제 파일에 남는 것은
        이름이 아니라 속성 자체이기 때문입니다. <b>쓰고 있는 속성은 뺄 수 없습니다.</b>
      </p>

      <ul className="type-rows">
        {rows.map((row, index) => (
          <li key={row.key || `new-${index}`}>
            <span className={`type-badge ${typeClass(row.key)}`}>{row.label || "이름 없음"}</span>
            <input
              value={row.label}
              onChange={(event) => update(index, event.target.value)}
              placeholder="예: 설비투자"
              maxLength={20}
            />
            <span className={row.count > 0 ? "type-used" : "muted type-used"}>
              {row.count > 0 ? `${row.count}건` : "쓰는 과제 없음"}
            </span>
            <span className="type-move">
              <button
                className="ghost small"
                disabled={index === 0}
                title="위로"
                onClick={() => move(index, -1)}
              >
                ↑
              </button>
              <button
                className="ghost small"
                disabled={index === rows.length - 1}
                title="아래로"
                onClick={() => move(index, 1)}
              >
                ↓
              </button>
            </span>
            <button
              className="ghost small danger"
              disabled={row.count > 0}
              title={
                row.count > 0
                  ? `${row.count}건이 쓰고 있어 뺄 수 없습니다. 그 과제들의 속성을 먼저 바꿔 주세요.`
                  : "이 속성을 뺍니다"
              }
              onClick={() => setRows(rows.filter((_, at) => at !== index))}
            >
              빼기
            </button>
          </li>
        ))}
        {rows.length === 0 && (
          <li className="type-empty">
            속성이 하나도 없습니다. 과제를 만들 때 속성 칸이 서지 않습니다.
          </li>
        )}
      </ul>

      <div className="form-actions left">
        <button
          className="ghost small"
          // 새 줄은 열쇠가 비어 있다 — 저장할 때 서버가 이름에서 지어 붙인다.
          onClick={() => setRows([...rows, { key: "", label: "", count: 0 }])}
        >
          + 속성 추가
        </button>
      </div>

      {notice && <p className="hint notice">{notice}</p>}
      {error && <p className="form-error">{error}</p>}

      <div className="form-actions">
        {changed && (
          <button className="ghost" disabled={busy} onClick={() => setRows(saved)}>
            되돌리기
          </button>
        )}
        <button disabled={busy || !changed} onClick={() => void save()}>
          {busy ? "저장 중…" : "저장"}
        </button>
      </div>
    </div>
  );
}
