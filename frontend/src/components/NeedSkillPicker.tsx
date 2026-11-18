import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { SkillEntry } from "../types";

/**
 * 필요 역량 고르기 (TODO 309) — 과제 · 접수 양식.
 *
 * 예전에는 역량 사전의 **앞 12개**만 칩으로 보여 나머지는 이름을 알아야 적을 수 있었다.
 * * 이 과제에 맞을 만한 — 서버 추천(글에 나옴 · 이 과제의 경험 · 같은 태그 과제), 까닭을 칩 옆에.
 * * 적는 중 — 마지막 조각(쉼표 뒤)이 이름 · 같은 말에 들어간 역량을 사전 전체에서.
 * * 역량 사전 전체 — 축(기술 · 업무 · 리더십 · 문제해결)마다 중분류 순으로 모두. 고른 것은 파랗게, 다시 누르면 뺀다.
 * * 적은 것 중 같은 말 → 대표 이름으로 저장 · 사전에 없는 이름은 [후보 보기]가 찾지 못한다고 알린다.
 */
const MAX = 10;
const AXES = ["기술", "업무", "리더십", "문제해결"];

export const skillKey = (text: string) => text.replace(/[\s·・‧•_\-,]+/g, "").toLowerCase();
const split = (value: string) => value.split(",").map((s) => s.trim()).filter(Boolean);

interface Props {
  value: string;
  onChange: (next: string) => void;
  dictionary: SkillEntry[];
  title?: string;
  tags?: string;
  project?: string;
  intake?: string;
}

export default function NeedSkillPicker({ value, onChange, dictionary, title = "", tags = "", project, intake }: Props) {
  const chosen = split(value);
  const lastRaw = value.endsWith(",") ? "" : (value.split(",").pop() ?? "").trim();
  // 열쇠 → 대표 이름(이름 · 같은 말)
  const index = useMemo(() => {
    const map = new Map<string, string>();
    for (const e of dictionary) map.set(skillKey(e.name), e.name);
    for (const e of dictionary) for (const a of e.aliases ?? []) if (!map.has(skillKey(a))) map.set(skillKey(a), e.name);
    return map;
  }, [dictionary]);
  const chosenNames = new Set(chosen.map((c) => index.get(skillKey(c)) ?? c));
  const full = chosen.length >= MAX;

  const [suggest, setSuggest] = useState<{ name: string; why: string[] }[]>([]);
  useEffect(() => {
    const timer = window.setTimeout(() => {
      api.needSuggest({ title, tags, project, intake }).then((d) => setSuggest(d.suggest)).catch(() => setSuggest([]));
    }, 500);
    return () => window.clearTimeout(timer);
  }, [title, tags, project, intake]);

  const toggle = (name: string) => {
    if (chosenNames.has(name)) {
      onChange(chosen.filter((c) => (index.get(skillKey(c)) ?? c) !== name).join(", "));
    } else if (!full) {
      // 적다 만 조각(사전 이름이 아님)은 고른 이름으로 바꾼다
      const base = lastRaw && !index.has(skillKey(lastRaw)) ? chosen.slice(0, -1) : chosen;
      onChange([...base, name].join(", "));
    }
  };
  const chip = (name: string, extra?: string) => (
    <button key={name} type="button" className={`tag-pick${chosenNames.has(name) ? " on" : ""}`} disabled={full && !chosenNames.has(name)}
      onClick={() => toggle(name)} title={extra}>
      {chosenNames.has(name) ? "✓ " : ""}{name}{extra && <span className="need-why"> · {extra}</span>}
    </button>
  );

  const typing = lastRaw && !index.has(skillKey(lastRaw))
    ? dictionary.filter((e) => [e.name, ...(e.aliases ?? [])].some((w) => skillKey(w).includes(skillKey(lastRaw)))).slice(0, 15)
    : [];
  const merges = chosen.filter((c) => index.has(skillKey(c)) && index.get(skillKey(c)) !== c).map((c) => `‘${c}’ → ‘${index.get(skillKey(c))}’`);
  const unknown = chosen.filter((c) => !index.has(skillKey(c)) && c !== lastRaw);
  const shownSuggest = suggest.filter((s) => !chosenNames.has(s.name));
  const byAxis = AXES.map((axis) => ({
    axis,
    items: dictionary.filter((e) => e.axis === axis).sort((a, b) => (a.group ?? "").localeCompare(b.group ?? "", "ko") || 0),
  })).filter((row) => row.items.length);

  return (
    <div className="need-picker" data-testid="need-picker">
      {(merges.length > 0 || unknown.length > 0 || full) && (
        <p className="hint tag-merge-hint">
          {merges.length > 0 && <>{merges.join(" · ")} 로 저장됩니다. </>}
          {unknown.length > 0 && <>‘{unknown.join("’ · ‘")}’ 은 역량 사전에 없어 [후보 보기]가 찾지 못합니다. </>}
          {full && <>필요 역량은 {MAX}개까지입니다.</>}
        </p>
      )}
      {typing.length > 0 && (
        <div className="tag-suggest" data-testid="need-typing">
          <span className="muted">‘{lastRaw}’ 이 든 역량</span>
          {typing.map((e) => chip(e.name))}
        </div>
      )}
      {shownSuggest.length > 0 && (
        <div className="tag-suggest" data-testid="need-suggest">
          <span className="muted">이 과제에 맞을 만한</span>
          {shownSuggest.map((s) => chip(s.name, s.why.join(" · ")))}
        </div>
      )}
      <details className="need-all" data-testid="need-all">
        <summary>역량 사전 전체에서 고르기 <span className="muted">({dictionary.length}개 · 고른 것 {chosenNames.size}개)</span></summary>
        {byAxis.map((row) => (
          <div key={row.axis} className="need-axis">
            <span className="need-axis-name">{row.axis}</span>
            <div className="tag-suggest">{row.items.map((e) => chip(e.name))}</div>
          </div>
        ))}
      </details>
    </div>
  );
}
