import { useEffect, useState } from "react";
import { Tags } from "lucide-react";
import { api } from "../api";
import CardIntro from "./CardIntro";
import IconTitle from "./IconTitle";
import InlineRetry from "./InlineRetry";

type Kind = "group" | "tag";
const LABELS: Record<Kind, string> = { group: "그룹", tag: "과제 태그" };

/**
 * 그룹 · 과제 태그 정리 (TODO 341 — 전수 검토 D4). 자유 입력이라 표기가 흔들리면("MES" / "MES 고도화") 홈 표 · 거르기가
 * 두 줄로 갈라졌다. 분류 넷의 값 정리(275)처럼 쓰는 과제 수를 보이고 [이름 바꾸기] 는 쓰는 과제 파일을 함께 고친다 —
 * 새 이름을 이미 쓰는 과제가 있으면 합치기.
 */
export default function LabelValuesCard({ onChanged }: { onChanged: () => void }) {
  const [usage, setUsage] = useState<Record<Kind, { value: string; projects: number }[]> | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [kind, setKind] = useState<Kind>("group");
  const [editing, setEditing] = useState<string | null>(null);
  const [to, setTo] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const load = () => api.labelUsage().then(({ usage: next }) => { setUsage(next); setLoadError(null); })
    .catch((err: Error) => setLoadError(err.message));
  useEffect(() => { void load(); }, []);

  const rows = usage?.[kind] ?? [];
  const existing = new Set(rows.map((row) => row.value));

  async function rename(old: string) {
    const next = to.trim();
    if (!next || next === old) return;
    const row = rows.find((r) => r.value === old);
    const merging = existing.has(next);
    if (!window.confirm(`${LABELS[kind]} ‘${old}’ 을(를) ‘${next}’ ${merging ? "(으)로 합칩니다(이미 쓰는 이름)" : "(으)로 바꿉니다"}.\n`
      + `쓰는 과제 ${row?.projects ?? 0}건의 값도 함께 바뀝니다. 진행할까요?`)) return;
    setBusy(true);
    try {
      const done = await api.renameLabel(kind, old, next);
      setMessage({ ok: true, text: `${done.merged ? "합쳤습니다" : "바꿨습니다"} — 과제 ${done.projects}건을 고쳤습니다.` });
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
    <div className="card" data-testid="label-values">
      <IconTitle icon={Tags}>그룹 · 과제 태그 정리</IconTitle>
      <CardIntro id="label-values">
        그룹과 태그는 직접 적는 값이라 표기가 조금만 달라도 홈 표 · 거르기에서 <b>두 줄로 갈라집니다</b>. 이름을 바꾸면
        그 값을 쓰는 과제도 함께 바뀌고, 이미 쓰는 이름으로 바꾸면 <b>합쳐집니다</b>. (태그의 대소문자 · 띄어쓰기 차이는 이미 한 태그로 봅니다)
      </CardIntro>
      <div className="dict-axes" role="group" aria-label="정리할 칸">
        {(Object.keys(LABELS) as Kind[]).map((key) => (
          <button key={key} type="button" className={kind === key ? "chip on" : "chip"} aria-pressed={kind === key}
            onClick={() => { setKind(key); setEditing(null); setMessage(null); }}>
            {LABELS[key]} {usage ? <span className="muted">{usage[key].length}</span> : null}
          </button>
        ))}
      </div>
      {loadError && <InlineRetry what="그룹 · 태그 목록" message={loadError} onRetry={() => void load()} />}
      <ul className="dict-list class-values-list" aria-label={`${LABELS[kind]} 값`}>
        {usage && rows.length === 0 && <li className="muted dict-empty">쓰는 {LABELS[kind]}이(가) 없습니다.</li>}
        {rows.map((row) => (
          <li key={row.value} className="dict-item" data-label-value={row.value}>
            <div className="dict-line static">
              <span className="dict-name">{row.value}</span>
              <span className="dict-aliases muted">과제 {row.projects}</span>
              {editing === row.value ? (
                <span className="class-rename">
                  <input aria-label={`${row.value} 새 이름`} list={`label-items-${kind}`} value={to} autoFocus maxLength={40}
                    placeholder="새 이름 · 합칠 값" onChange={(e) => setTo(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") void rename(row.value); if (e.key === "Escape") setEditing(null); }} />
                  <button type="button" className="small" disabled={busy || !to.trim() || to.trim() === row.value} onClick={() => void rename(row.value)}>
                    {existing.has(to.trim()) && to.trim() !== row.value ? "합치기" : "바꾸기"}
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
      <datalist id={`label-items-${kind}`}>
        {rows.map((row) => <option key={row.value} value={row.value} />)}
      </datalist>
      {message && <p className={message.ok ? "hint notice" : "form-error"}>{message.text}</p>}
    </div>
  );
}
