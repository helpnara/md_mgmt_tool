import { useEffect, useState } from "react";
import { api } from "../api";
import type { Meta } from "../types";

type Usage = Record<string, { value: string; projects: number; intakes: number; listed: boolean }[]>;

/**
 * 분류 넷의 값 정리 (TODO 275 — 설정 반영 전수 조사 빈틈 1).
 *
 * 값은 과제 · 접수에 글자 그대로 적혀서, 목록 칸에서 이름만 고치면 기존 과제 · 접수는 옛 이름으로 남았다(홈 표에 따로 한 줄 · 거르기에서 못 찾음).
 * 여기서 값마다 **쓰는 과제 · 접수 수**(목록에 없는 옛 값까지)를 보이고, [이름 바꾸기]는 쓰는 과제 · 접수의 값과 목록을 **함께** 고친다.
 * 새 이름이 이미 목록에 있으면 **합치기**.
 */
export default function ClassValuesPanel({ meta, onChanged }: { meta: Meta; onChanged: () => void }) {
  const [usage, setUsage] = useState<Usage | null>(null);
  const [field, setField] = useState(meta.classifications[0]?.key ?? "nature");
  const [editing, setEditing] = useState<string | null>(null);
  const [to, setTo] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const load = () => api.classificationUsage().then(({ usage: next }) => setUsage(next)).catch(() => setUsage(null));
  useEffect(() => { void load(); }, [meta.classifications]); // eslint-disable-line react-hooks/exhaustive-deps

  const info = meta.classifications.find((c) => c.key === field);
  const rows = usage?.[field] ?? [];

  async function rename(old: string) {
    const next = to.trim();
    if (!next || next === old) return;
    const row = rows.find((r) => r.value === old);
    const merging = info?.items.includes(next);
    const what = `${info?.label ?? ""} ‘${old}’ 을(를) ‘${next}’ ${merging ? "으로 합칩니다(이미 있는 값)" : "으로 바꿉니다"}.\n`
      + `쓰는 과제 ${row?.projects ?? 0}건 · 접수 ${row?.intakes ?? 0}건의 값도 함께 바뀝니다. 진행할까요?`;
    if (!window.confirm(what)) return;
    setBusy(true);
    try {
      const done = await api.renameClassification(field, old, next);
      setMessage({ ok: true, text: `${done.merged ? "합쳤습니다" : "바꿨습니다"} — 과제 ${done.projects}건 · 접수 ${done.intakes}건의 값을 고쳤습니다.` });
      setEditing(null);
      setTo("");
      await load();
      onChanged();
    } catch (err) {
      setMessage({ ok: false, text: (err as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="class-values" data-testid="class-values">
      <div className="class-values-head">
        <b>값 정리</b>
        <span className="hint">— 이름을 바꾸면 그 값을 쓰는 과제 · 접수도 함께 바뀝니다. 위 목록 칸에서 직접 고치면 기존 과제는 옛 이름으로 남습니다.</span>
      </div>
      <div className="dict-axes" role="group" aria-label="정리할 칸">
        {meta.classifications.map((c) => (
          <button key={c.key} type="button" className={field === c.key ? "chip on" : "chip"} aria-pressed={field === c.key}
            onClick={() => { setField(c.key); setEditing(null); setMessage(null); }}>
            {c.label}
            {(usage?.[c.key] ?? []).some((r) => !r.listed) && <span className="warn-text" title="목록에 없는 옛 값이 있습니다"> ●</span>}
          </button>
        ))}
      </div>
      <ul className="dict-list class-values-list" aria-label={`${info?.label ?? ""} 값`}>
        {rows.length === 0 && <li className="muted dict-empty">값이 없습니다.</li>}
        {rows.map((row) => (
          <li key={row.value} className="dict-item" data-class-value={row.value}>
            <div className="dict-line static">
              <span className="dict-name">{row.value}</span>
              {!row.listed && <span className="tag warn-tag" title="설정 목록에 없는 값 — 예전 이름이거나 손으로 적은 값">목록에 없음</span>}
              <span className="dict-aliases muted">과제 {row.projects} · 접수 {row.intakes}</span>
              {editing === row.value ? (
                <span className="class-rename">
                  <input aria-label={`${row.value} 새 이름`} list={`class-items-${field}`} value={to} autoFocus maxLength={30}
                    placeholder="새 이름 · 합칠 값" onChange={(e) => setTo(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") void rename(row.value); if (e.key === "Escape") setEditing(null); }} />
                  <button type="button" className="small" disabled={busy || !to.trim() || to.trim() === row.value} onClick={() => void rename(row.value)}>
                    {info?.items.includes(to.trim()) && to.trim() !== row.value ? "합치기" : "바꾸기"}
                  </button>
                  <button type="button" className="ghost small" onClick={() => setEditing(null)}>취소</button>
                </span>
              ) : (
                <button type="button" className="ghost small" disabled={busy} onClick={() => { setEditing(row.value); setTo(row.value); setMessage(null); }}>
                  이름 바꾸기
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
      <datalist id={`class-items-${field}`}>
        {(info?.items ?? []).map((item) => <option key={item} value={item} />)}
      </datalist>
      {message && <p className={message.ok ? "hint notice" : "form-error"}>{message.text}</p>}
    </div>
  );
}
