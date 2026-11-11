import { useMemo, useState, type ReactNode } from "react";
import { axisLabel } from "../util";

/** 사전 한 줄 — 축(역량 사전만) · 대표 이름 · 다른 이름. origin = 저장된 자리(새 줄은 "") */
export type DictRow = { axis?: string; name: string; aliases: string[]; origin: string };

const norm = (text: string) => text.replace(/[\s·・‧•_\-,]+/g, "").toLowerCase();

/**
 * 사전 편집 (TODO 274) — 역량 사전 · 보유 기술 사전이 함께 쓴다.
 *
 * 예전엔 가로로 긴 표(대표 이름 · 다른 이름 입력 칸이 줄마다)라, 항목이 수십 개를 넘으면 찾기도 고치기도 어려웠다(사용자 2026-11-11).
 * 이제 ① **찾기**(대표 이름 · 다른 이름 모두, 띄어쓰기 · 가운뎃점 무시) ② 축 칩(역량 사전) ③ 짧은 목록 — 이름 · 쓰는 수 · 다른 이름은 흐리게 한 줄
 * ④ 줄을 누르면 그 아래에 **고치는 칸**(이름 · 축 · 다른 이름을 칩으로 — 엔터로 더하고 ×로 뺀다) ⑤ 고친 줄은 ● 표시 — [저장]은 카드 아래 한 번.
 */
export default function DictionaryEditor({
  rows, saved: savedRows, setRows, axes, usage, itemLabel, extraActions, removable,
}: {
  rows: DictRow[];
  /** 저장된 줄 — 고친 줄(●)을 가리는 기준 */
  saved: DictRow[];
  setRows: (rows: DictRow[]) => void;
  /** 역량 사전이면 축 넷 — 칩으로 거르고 고치는 칸에 축 상자 */
  axes?: string[];
  usage: (row: DictRow) => number;
  /** "역량" · "보유 기술" — 안내 글 · aria 이름에 */
  itemLabel: string;
  /** 고치는 칸 아래의 더 할 일(역량 사전의 [다른 역량으로 합치기]) */
  extraActions?: (row: DictRow, index: number) => ReactNode;
  /** 쓰는 항목도 뺄 수 있나(보유 기술 사전 — 빼도 적힌 이름은 남는다) */
  removable: (row: DictRow) => boolean;
}) {
  const [query, setQuery] = useState("");
  const [axis, setAxis] = useState("");
  const [open, setOpen] = useState<number | null>(null);
  const [alias, setAlias] = useState("");
  const saved = useMemo(() => new Map(savedRows.map((r) => [r.origin, r])), [savedRows]);

  const q = norm(query);
  const shown = rows
    .map((row, index) => ({ row, index }))
    .filter(({ row }) => !axis || row.axis === axis)
    .filter(({ row }) => !q || norm(row.name).includes(q) || row.aliases.some((a) => norm(a).includes(q)) || !row.name.trim());
  const counts = (axes ?? []).map((a) => ({ axis: a, n: rows.filter((r) => r.axis === a).length }));

  const set = (index: number, patch: Partial<DictRow>) => setRows(rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  const changed = (row: DictRow) => {
    if (!row.origin) return true;
    const before = saved.get(row.origin);
    return !before || before.name !== row.name || before.axis !== row.axis || before.aliases.join("|") !== row.aliases.join("|");
  };
  const addAlias = (index: number) => {
    const parts = alias.split(",").map((a) => a.trim()).filter(Boolean);
    if (!parts.length) return;
    const row = rows[index];
    set(index, { aliases: [...row.aliases, ...parts.filter((p) => !row.aliases.some((a) => norm(a) === norm(p)) && norm(p) !== norm(row.name))] });
    setAlias("");
  };
  const addNew = () => {
    setRows([{ axis: axes ? axis || axes[0] : undefined, name: "", aliases: [], origin: "" }, ...rows]);
    setOpen(0);
    setQuery("");
    setAlias("");
  };

  return (
    <div className="dict-editor" data-testid="dict-editor">
      <div className="dict-tools">
        <input type="search" className="dict-search" placeholder={`${itemLabel} 찾기 — 이름 · 다른 이름`} aria-label={`${itemLabel} 찾기`}
          value={query} onChange={(event) => setQuery(event.target.value)} />
        <button type="button" className="ghost small" onClick={addNew}>+ {itemLabel}</button>
      </div>
      {axes && (
        <div className="dict-axes" role="group" aria-label="축으로 거르기">
          <button type="button" className={axis ? "chip" : "chip on"} aria-pressed={!axis} onClick={() => setAxis("")}>전체 <b>{rows.length}</b></button>
          {counts.map(({ axis: a, n }) => (
            <button key={a} type="button" className={axis === a ? "chip on" : "chip"} aria-pressed={axis === a} onClick={() => setAxis(a)}>
              {axisLabel(a)} <b>{n}</b>
            </button>
          ))}
        </div>
      )}
      <ul className="dict-list" aria-label={`${itemLabel} 목록`}>
        {shown.length === 0 && <li className="muted dict-empty">찾는 {itemLabel}이(가) 없습니다.</li>}
        {shown.map(({ row, index }) => {
          const used = usage(row);
          const isOpen = open === index;
          return (
            <li key={index} className={isOpen ? "dict-item open" : "dict-item"} data-entry={row.name}>
              <button type="button" className="dict-line" aria-expanded={isOpen} onClick={() => { setOpen(isOpen ? null : index); setAlias(""); }}>
                {changed(row) && <span className="dict-dirty" title="고쳤습니다 — [저장]을 누르세요">●</span>}
                <span className="dict-name">{row.name || <i className="muted">(이름 없음)</i>}</span>
                {axes && !axis && <span className="dict-axis muted">{axisLabel(row.axis ?? "")}</span>}
                <span className="dict-aliases muted">{row.aliases.join(", ")}</span>
                <span className={used ? "dict-used" : "dict-used zero"} title="쓰는 곳 수">{used || "-"}</span>
              </button>
              {isOpen && (
                <div className="dict-edit">
                  <div className="dict-edit-row">
                    {axes && (
                      <select aria-label="축" value={row.axis} onChange={(event) => set(index, { axis: event.target.value })}>
                        {axes.map((a) => <option key={a} value={a}>{axisLabel(a)}</option>)}
                      </select>
                    )}
                    <input aria-label={`${itemLabel} 대표 이름`} value={row.name} maxLength={60} placeholder="대표 이름"
                      onChange={(event) => set(index, { name: event.target.value })} autoFocus={!row.name} />
                  </div>
                  <div className="dict-alias-chips">
                    {row.aliases.map((a) => (
                      <span key={a} className="exp-chip">
                        {a}
                        <button type="button" className="chip-x" aria-label={`${a} 빼기`} onClick={() => set(index, { aliases: row.aliases.filter((x) => x !== a) })}>×</button>
                      </span>
                    ))}
                    <input className="dict-alias-input" aria-label={`${itemLabel} 다른 이름`} value={alias} placeholder="다른 이름 — 엔터(쉼표로 여럿)"
                      onChange={(event) => setAlias(event.target.value)}
                      onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); addAlias(index); } }}
                      onBlur={() => addAlias(index)} />
                  </div>
                  <div className="dict-edit-actions">
                    {extraActions?.(row, index)}
                    {removable(row) ? (
                      <button type="button" className="ghost small danger" onClick={() => { setRows(rows.filter((_, i) => i !== index)); setOpen(null); }}>빼기</button>
                    ) : (
                      <span className="hint">쓰는 곳이 있어 빼지 않고 합칩니다</span>
                    )}
                  </div>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
