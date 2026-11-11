import { useEffect, useMemo, useState } from "react";
import { Wand2 } from "lucide-react";
import { api } from "../api";
import { copyText, COPY_FAILED } from "../clipboard";
import { notifyError } from "../notify";
import type { SkillEntry, TagAction, TagDecision, TagProposal, UnknownTag } from "../types";
import CardIntro from "./CardIntro";
import { axisLabel } from "../util";
import { SKILL_DICTIONARY_CHANGED } from "./SkillDictionaryCard";
import { experienceLink } from "./ExperienceCard";
import IconTitle from "./IconTitle";

const AXES = ["기술", "업무", "리더십", "문제해결"];
/** 한 태그의 결정 — action 이 비면 "그대로". alias 면 target(축|이름), new 면 axis · name(다듬은 이름) */
type Choice = { action: TagAction | ""; target: string; axis: string; name: string };
const EMPTY: Choice = { action: "", target: "", axis: "", name: "" };

export const CLEANUP_ANCHOR = "skill-cleanup";

/**
 * 역량 태그 정리함 (TODO 262 · 261 → 280 · 282).
 *
 * 사전에 없는 태그를 **팀 전체에서 모아** 한 번에 정리한다. 282 — 사용자 편의(사용자 2026-11-11 "사용자 편의성이 매우 중요하니깐"):
 * A 추천을 **단추로**(한 번 누르면 결정) · B 결정이 그 줄에 보임 · C 줄을 펼쳐 그 태그가 붙은 경험(제목 · 사람 · 행동 첫 줄)
 * D 여럿을 골라 한 번에 · E [적용] 전 요약 · F 진행 "결정 n / N" · 찾기 · 결정 안 한 것만 · G AI 제안이 줄 안에 칩으로
 * J 새 역량 이름을 그 자리에서 다듬기. 적용은 사람이 [적용]으로 — AI 의 답을 그대로 넣지 않는다.
 */
export default function SkillCleanupCard() {
  const [tags, setTags] = useState<UnknownTag[] | null>(null);
  const [dictionary, setDictionary] = useState<SkillEntry[]>([]);
  const [choices, setChoices] = useState<Record<string, Choice>>({});
  const [ai, setAi] = useState<Record<string, TagProposal>>({});
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [open, setOpen] = useState<string | null>(null);
  const [find, setFind] = useState("");
  const [onlyOpen, setOnlyOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [prompt, setPrompt] = useState<string | null>(null);
  const [answer, setAnswer] = useState("");
  const [copied, setCopied] = useState(false);
  // 280 — 파일이 잠겨(다른 프로그램 · 네트워크 드라이브) 못 바꾼 경험. 사전은 이미 바뀌었으니 [다시 맞추기]로 끝낸다
  const [failed, setFailed] = useState<{ id: string; person: string; reason: string }[]>([]);

  const keyOf = (t: { axis: string; name: string }) => `${t.axis}|${t.name}`;
  const load = async () => {
    try {
      const [unknown, dict] = await Promise.all([api.unknownTags(), api.experienceSkills()]);
      setTags(unknown.items);
      setDictionary(dict.dictionary);
      // 처음 결정 — 보유 기술 사전에 있는 이름이면 "보유 기술로", 아니면 비워 둔다(사람이 고른다)
      setChoices(Object.fromEntries(unknown.items.map((t) => [keyOf(t), t.tool_like ? { ...EMPTY, action: "tool" as TagAction } : EMPTY])));
      setPicked(new Set());
      setAi({});
    } catch (error) {
      notifyError((error as Error).message);
    }
  };
  useEffect(() => { void load(); }, []);

  const choose = (key: string, next: Partial<Choice>) => setChoices((now) => ({ ...now, [key]: { ...EMPTY, ...next } }));
  const isDecided = (c: Choice | undefined) => Boolean(c && c.action && (c.action !== "alias" || c.target) && (c.action !== "new" || c.name.trim()));
  const decided = Object.entries(choices).filter(([, c]) => isDecided(c));

  const q = find.replace(/\s+/g, "").toLowerCase();
  const shown = useMemo(() => (tags ?? []).filter((t) => (!q || t.name.replace(/\s+/g, "").toLowerCase().includes(q))
    && (!onlyOpen || !isDecided(choices[keyOf(t)]))), [tags, q, onlyOpen, choices]); // eslint-disable-line react-hooks/exhaustive-deps

  async function retryFailed() {
    setBusy(true);
    try {
      let changed = 0;
      for (const person of [...new Set(failed.map((f) => f.person))]) changed += (await api.rematchSkills(person)).changed.length;
      setFailed([]);
      setNotice(`다시 맞췄습니다 — 경험 ${changed}건.`);
      await load();
    } catch (error) {
      notifyError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  /** E — [적용] 전 요약: 사전에 무엇이 더해지고 경험 몇 건이 바뀌나 */
  function summary(): string {
    const by = (a: TagAction) => decided.filter(([, c]) => c.action === a).length;
    const ids = new Set<string>();
    for (const [key] of decided) for (const id of tags?.find((t) => keyOf(t) === key)?.experiences ?? []) ids.add(id);
    return `태그 ${decided.length}개를 정리합니다.\n\n`
      + `· 사전의 역량에 다른 이름으로 더함 ${by("alias")}개\n· 새 역량으로 사전에 더함 ${by("new")}개\n`
      + `· 보유 기술(도구)로 옮김 ${by("tool")}개\n· 빼기 ${by("drop")}개\n\n`
      + `팀원 경험 ${ids.size}건의 태그가 함께 바뀝니다(바꾸기 전 내용은 이전 버전에 남습니다). 진행할까요?`;
  }

  async function apply() {
    if (!tags || decided.length === 0) return;
    const actions: TagDecision[] = decided.map(([key, c]) => {
      const [axis, name] = key.split("|");
      const [targetAxis, targetName] = c.target.split("|");
      return c.action === "alias" ? { axis, name, action: "alias", target_axis: targetAxis, target_name: targetName }
        : c.action === "new" ? { axis, name, action: "new", target_axis: c.axis || axis, target_name: c.name.trim() }
        : { axis, name, action: c.action as TagAction };
    });
    if (!window.confirm(summary())) return;
    setBusy(true);
    try {
      const result = await api.cleanupTags(actions);
      setFailed(result.failed ?? []);
      setNotice(`정리했습니다 — 경험 ${result.changed.length}건의 태그를 바꿨습니다.`
        + ((result.failed ?? []).length ? ` 못 바꾼 경험 ${result.failed!.length}건이 있습니다 — 아래를 보세요.` : ""));
      // 280 — 같은 화면의 역량 사전 카드가 옛 사전을 들고 있다가 [저장]으로 덮지 않게 알린다
      window.dispatchEvent(new Event(SKILL_DICTIONARY_CHANGED));
      setPrompt(null);
      setAnswer("");
      await load();
    } catch (error) {
      notifyError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function openPrompt() {
    try {
      setPrompt((await api.tagPrompt()).text);
    } catch (error) {
      notifyError((error as Error).message);
    }
  }

  /** G — AI 의 답은 줄마다 "AI 제안" 칩으로. 누르거나 [AI 제안 모두 받기]로 결정 */
  async function readAnswer() {
    try {
      const { items } = await api.tagAnswer(answer);
      setAi(Object.fromEntries(items.map((row) => [keyOf(row), row])));
      const usable = items.filter((row) => row.action).length;
      setNotice(`AI 의 답 ${items.length}줄 — 쓸 수 있는 제안 ${usable}개를 줄마다 "AI" 칩으로 붙였습니다. 누르거나 [AI 제안 모두 받기]로 고르세요.`);
    } catch (error) {
      notifyError((error as Error).message);
    }
  }

  const fromAi = (row: TagProposal): Partial<Choice> | null =>
    row.action === "alias" ? { action: "alias", target: `${row.target_axis}|${row.target_name}` }
      : row.action === "new" ? { action: "new", axis: row.target_axis ?? row.axis, name: row.name }
      : row.action === "tool" || row.action === "drop" ? { action: row.action } : null;

  function takeAllAi() {
    setChoices((now) => {
      const next = { ...now };
      for (const [key, row] of Object.entries(ai)) {
        const c = fromAi(row);
        if (c && !isDecided(next[key])) next[key] = { ...EMPTY, ...c };
      }
      return next;
    });
  }

  /** D — 고른 여럿에 같은 결정 */
  function bulk(next: Partial<Choice> | null) {
    setChoices((now) => {
      const out = { ...now };
      for (const key of picked) {
        const [axis, name] = key.split("|");
        out[key] = next ? { ...EMPTY, ...next, ...(next.action === "new" ? { axis: next.axis || axis, name } : {}) } : EMPTY;
      }
      return out;
    });
    setPicked(new Set());
  }

  async function copyPrompt() {
    if (!prompt) return;
    if (!(await copyText(prompt))) {
      notifyError(COPY_FAILED);
      return;
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  }

  const describe = (t: UnknownTag, c: Choice): string => {
    if (c.action === "alias") {
      const [axis, name] = c.target.split("|");
      return `→ ${axisLabel(axis)} · ${name} (다른 이름으로 더함)`;
    }
    if (c.action === "new") return `→ 새 역량 ${axisLabel(c.axis || t.axis)} · ${c.name || t.name}`;
    if (c.action === "tool") return "→ 보유 기술(도구)로 옮김";
    if (c.action === "drop") return "→ 태그 빼기";
    return "";
  };

  const total = tags?.length ?? 0;
  const allShownPicked = shown.length > 0 && shown.every((t) => picked.has(keyOf(t)));
  return (
    <div className="card skill-cleanup settings-wide" data-testid="skill-cleanup" id={CLEANUP_ANCHOR}>
      <div className="card-head">
        <IconTitle icon={Wand2}>역량 태그 정리함 — 사전에 없는 태그 {total}개</IconTitle>
        <div className="person-tools">
          {total > 0 && <span className="cleanup-progress" data-testid="cleanup-progress">결정 <b>{decided.length}</b> / {total}</span>}
          <button className="ghost" disabled={!tags?.length} onClick={() => (prompt === null ? void openPrompt() : setPrompt(null))}>
            {prompt === null ? "AI 로 맞추기" : "AI 로 맞추기 닫기"}
          </button>
        </div>
      </div>
      <CardIntro id="skill-cleanup">
        팀원 경험에서 <b>사전에 없는 태그</b>를 모았습니다. 줄마다 <b>추천 단추</b>(비슷한 역량 — 다른 이름으로 더함) · <b>[새 역량]</b> ·
        <b> [보유 기술(도구)]</b> · <b>[빼기]</b> 중 하나를 누르면 결정되고, 다 고르면 아래 [적용]으로 한 번에 바꿉니다. 태그 이름을 누르면 그 태그가 붙은 경험이 보입니다.
      </CardIntro>
      {prompt !== null && (
        <div className="refine-panel" data-testid="tag-prompt">
          <p className="hint">사내 AI 에 붙여넣을 글입니다 — <b>읽어 보고</b> 복사하세요. 답의 <code>태그 | 맞출 곳</code> 줄을 아래에 붙이면 줄마다 <b>AI 제안 칩</b>이 붙습니다(바로 적용하지 않음).</p>
          <textarea className="refine-text" readOnly value={prompt} aria-label="태그 맞추기 프롬프트" />
          <div className="form-actions"><button onClick={() => void copyPrompt()}>{copied ? "복사됨 ✓" : "전문 복사"}</button></div>
          <textarea className="import-paste" value={answer} onChange={(e) => setAnswer(e.target.value)} aria-label="AI 의 답" placeholder="- 알고리즘 개발 | 버림" />
          <div className="form-actions">
            <button className="ghost" disabled={!answer.trim()} onClick={() => void readAnswer()}>답 읽기</button>
            {Object.keys(ai).length > 0 && <button onClick={takeAllAi}>AI 제안 모두 받기</button>}
          </div>
        </div>
      )}
      {notice && <p className="hint notice">{notice}</p>}
      {failed.length > 0 && (
        <div className="cleanup-failed" data-testid="cleanup-failed">
          <p className="warn-text">
            <b>못 바꾼 경험 {failed.length}건</b> — 파일을 다른 프로그램(탐색기 미리보기 · 편집기 · 백신)이 잡고 있었습니다. 그 프로그램을 닫고 [다시 맞추기]를 누르세요.
            사전은 이미 바뀌어 있습니다.
          </p>
          <ul className="muted">{failed.slice(0, 8).map((f) => <li key={f.id}>{f.id} · {f.person} — {f.reason}</li>)}</ul>
          <button type="button" className="small" disabled={busy} onClick={() => void retryFailed()}>다시 맞추기</button>
        </div>
      )}
      {!tags ? <p className="muted">불러오는 중…</p> : total === 0 ? (
        <p className="muted">사전에 없는 태그가 없습니다 — 정리할 것이 없습니다.</p>
      ) : (
        <>
          {/* F — 찾기 · 결정 안 한 것만 · 모두 고르기 */}
          <div className="cleanup-tools">
            <label className="check-label">
              <input type="checkbox" aria-label="보이는 태그 모두 고르기" checked={allShownPicked}
                onChange={(e) => setPicked(e.target.checked ? new Set([...picked, ...shown.map((t) => keyOf(t))]) : new Set())} />
              모두
            </label>
            <input type="search" className="dict-search" placeholder="태그 찾기" aria-label="태그 찾기" value={find} onChange={(e) => setFind(e.target.value)} />
            <button type="button" className={onlyOpen ? "chip on" : "chip"} aria-pressed={onlyOpen} onClick={() => setOnlyOpen(!onlyOpen)}>
              결정 안 한 것만 <b>{total - decided.length}</b>
            </button>
          </div>
          {/* D — 고른 여럿에 한 번에 */}
          {picked.size > 0 && (
            <div className="cleanup-bulk" data-testid="cleanup-bulk">
              <b>{picked.size}개 고름</b>
              <button type="button" className="small ghost" onClick={() => bulk({ action: "drop" })}>모두 빼기</button>
              <button type="button" className="small ghost" onClick={() => bulk({ action: "tool" })}>모두 보유 기술(도구)로</button>
              <button type="button" className="small ghost" onClick={() => bulk({ action: "new" })}>모두 새 역량으로</button>
              <button type="button" className="small ghost" onClick={() => bulk(null)}>결정 지우기</button>
              <button type="button" className="link-button" onClick={() => setPicked(new Set())}>고르기 풀기</button>
            </div>
          )}
          <ul className="cleanup-list" aria-label="정리할 태그">
            {shown.map((t) => {
              const key = keyOf(t);
              const c = choices[key] ?? EMPTY;
              const done = isDecided(c);
              const hint = ai[key];
              const aiChoice = hint ? fromAi(hint) : null;
              return (
                <li key={key} className={done ? "cleanup-row decided" : "cleanup-row"} data-tag={t.name}>
                  <div className="cleanup-line">
                    <input type="checkbox" aria-label={`${t.name} 고르기`} checked={picked.has(key)}
                      onChange={(e) => { const next = new Set(picked); if (e.target.checked) next.add(key); else next.delete(key); setPicked(next); }} />
                    <button type="button" className="cleanup-name link-button" aria-expanded={open === key} onClick={() => setOpen(open === key ? null : key)}
                      title="이 태그가 붙은 경험 보기">
                      <b>{t.name}</b>
                    </button>
                    <span className="muted cleanup-meta">{axisLabel(t.axis)} · 경험 {t.count} · {t.people.join(", ")}</span>
                    {done && (
                      <span className="cleanup-decision" data-testid="cleanup-decision">
                        {describe(t, c)}
                        <button type="button" className="link-button" onClick={() => choose(key, {})}>취소</button>
                      </span>
                    )}
                  </div>
                  {/* A — 한 번 누르면 결정. G — AI 제안도 칩으로 */}
                  <div className="cleanup-actions">
                    {hint && aiChoice && !done && (
                      <button type="button" className="chip ai-chip" onClick={() => choose(key, aiChoice)} title={hint.unsure ? "AI 가 확실하지 않다고 한 것" : "AI 의 제안"}>
                        AI: {hint.action === "alias" ? `→ ${hint.target_name}` : hint.action === "new" ? "새 역량" : hint.action === "tool" ? "보유 기술(도구)" : "빼기"}{hint.unsure ? " ?" : ""}
                      </button>
                    )}
                    {hint?.problem && <span className="form-warn">AI: {hint.problem}</span>}
                    {t.suggest.slice(0, 3).map((sg) => (
                      <button key={keyOf(sg)} type="button" className={c.action === "alias" && c.target === keyOf(sg) ? "chip on" : "chip"}
                        onClick={() => choose(key, { action: "alias", target: keyOf(sg) })} title="이 역량의 다른 이름으로 더합니다">
                        → {sg.name}
                      </button>
                    ))}
                    <select aria-label="다른 역량으로" className="cleanup-other" value={c.action === "alias" && !t.suggest.some((sg) => keyOf(sg) === c.target) ? c.target : ""}
                      onChange={(e) => e.target.value && choose(key, { action: "alias", target: e.target.value })}>
                      <option value="">다른 역량 ▾</option>
                      {AXES.map((axis) => (
                        <optgroup key={axis} label={axisLabel(axis)}>
                          {dictionary.filter((d) => d.axis === axis).map((d) => <option key={keyOf(d)} value={keyOf(d)}>{d.name}</option>)}
                        </optgroup>
                      ))}
                    </select>
                    <button type="button" className={c.action === "new" ? "chip on" : "chip"} onClick={() => choose(key, { action: "new", axis: t.axis, name: t.name })}>새 역량</button>
                    <button type="button" className={c.action === "tool" ? "chip on" : "chip"} onClick={() => choose(key, { action: "tool" })}>보유 기술(도구)</button>
                    <button type="button" className={c.action === "drop" ? "chip on danger" : "chip"} onClick={() => choose(key, { action: "drop" })}>빼기</button>
                  </div>
                  {/* J — 새 역량의 이름 · 축을 그 자리에서 */}
                  {c.action === "new" && (
                    <div className="cleanup-new">
                      <select aria-label="새 역량의 축" value={c.axis || t.axis} onChange={(e) => setChoices((now) => ({ ...now, [key]: { ...c, axis: e.target.value } }))}>
                        {AXES.map((a) => <option key={a} value={a}>{axisLabel(a)}</option>)}
                      </select>
                      <input aria-label="새 역량 이름" value={c.name} maxLength={60} onChange={(e) => setChoices((now) => ({ ...now, [key]: { ...c, name: e.target.value } }))} />
                      <span className="hint">이름을 다듬으면 옛 태그는 그 역량의 다른 이름으로 남습니다. 이미 있는 이름이면 그 역량으로 합칩니다.</span>
                    </div>
                  )}
                  {/* C — 맥락 */}
                  {open === key && (
                    <ul className="cleanup-uses" data-testid="cleanup-uses">
                      {(t.uses ?? []).map((use) => (
                        <li key={use.id}>
                          <a href={experienceLink(use.id)}>{use.title}</a>
                          <span className="muted"> · {use.person}{use.status ? ` · ${use.status}` : ""}</span>
                          {use.line && <span className="muted cleanup-use-line"> — {use.line}</span>}
                        </li>
                      ))}
                      {t.count > (t.uses?.length ?? 0) && <li className="muted">… 외 {t.count - (t.uses?.length ?? 0)}건</li>}
                    </ul>
                  )}
                </li>
              );
            })}
            {shown.length === 0 && <li className="muted dict-empty">찾는 태그가 없습니다.</li>}
          </ul>
        </>
      )}
      <div className="form-actions">
        <button disabled={busy || decided.length === 0} onClick={() => void apply()}>{busy ? "정리하는 중…" : `적용 (${decided.length})`}</button>
      </div>
    </div>
  );
}
