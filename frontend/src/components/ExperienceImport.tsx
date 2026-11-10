import { useEffect, useRef, useState } from "react";
import { ClipboardPaste, ListChecks, Sparkles } from "lucide-react";
import { api } from "../api";
import { copyText, COPY_FAILED } from "../clipboard";
import { isManager } from "../me";
import { notifyError } from "../notify";
import { personLink, setPageTitle } from "../nav";
import { useEditedUnsaved } from "../util";
import type { ExperiencePrompt, ImportAction, ImportBlock, ImportDecision, ImportPreview, ImportTarget } from "../types";
import IconTitle from "./IconTitle";
import { experienceLink } from "./ExperienceCard";

/** 칸 비교 — 백엔드 `experience_import.COMPARE_FIELDS` 와 같은 칸 · 같은 순서 */
const COMPARE_FIELDS: [string, string][] = [
  ["title", "제목"], ["period", "기간"], ["role", "역할"], ["kind", "구분"], ["situation", "상황"], ["goal", "목표"],
  ["actions", "행동"], ["result_qual", "결과(정성)"], ["impact", "영향"], ["lesson", "교훈"], ["affiliation", "소속"],
];
const ACTIONS: ImportAction[] = ["이어서", "새로", "버림"];
/** 원본 UX 4절 S-03 ① 고정 문구를 사내에 맞춰 */
const PROMPT_NOTE = "이 글은 사내 AI 로 갑니다. 고객사 이름 · 대외비는 붙이기 전에 지우거나 바꾸세요.";
const NO_BLOCK = "형식 블록이 없습니다. 프롬프트를 처음부터 끝까지 붙여 넣었는지 확인하세요. 응답 원문은 남았습니다.";

type Decisions = Record<number, ImportDecision>;

/** 기본값의 근거 — 백엔드 `PROJECT_REASONS` · `ACTION_REASONS` 와 같은 말 (TODO 259) */
const PROJECT_REASON: Record<string, string> = { key: "블록의 과제 칸으로", continues: "AI 의 이어짐으로", single: "고른 과제가 하나라", title: "제목이 과제명과 닮아" };
const ACTION_REASON: Record<string, string> = {
  continues: "AI 의 이어짐으로", draft: "이 과제의 담당 초안으로", shared: "같은 경험을 앞 블록이 가리켜 새 경험으로",
};

function blockValue(block: ImportBlock, field: string): string {
  const f = block.fields;
  if (field === "period") return f.start || f.end ? `${f.start} ~ ${f.end}` : "";
  const value = (f as unknown as Record<string, unknown>)[field];
  return Array.isArray(value) ? value.join("\n") : String(value ?? "");
}

/** 둘 다 값이 있고 다른 칸 — 백엔드 `compare` 와 같은 규칙. 기본은 사람이 고친 적 없으면 AI 값(3단계.md ④) */
export function conflicts(target: ImportTarget, block: ImportBlock) {
  return COMPARE_FIELDS.map(([field, label]) => ({ field, label, old: String(target[field] ?? "").trim(), next: blockValue(block, field).trim() }))
    .filter((row) => row.old && row.next && row.old !== row.next);
}

/**
 * AI 로 정리 — 응답 되받기 (TODO 258 · 253 의 3단계, 원본 UX S-03 을 사람별 이력에 맞춰).
 *
 * ① 과제 고르기 · 프롬프트(먼저 보이고 복사) → ② 사내 AI 응답 붙여넣기 → ③ 미리보기 · 저장(구조화).
 * [읽기] 하는 순간 응답 원문은 사람 폴더에 남는다(블록 0개여도). 저장은 서버가 원문을 다시 읽어서 한다.
 * 관리자 · 팀장만(3단계.md ⑥) — 팀원 PC 는 이 화면에 들어와도 안내만 본다.
 */
export default function ExperienceImport({ name }: { name: string }) {
  const [prompt, setPrompt] = useState<ExperiencePrompt | null>(null);
  const [picked, setPicked] = useState<string[] | null>(null);
  const [copied, setCopied] = useState("");
  const [paste, setPaste] = useState("");
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [decisions, setDecisions] = useState<Decisions>({});
  const [open, setOpen] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<{ made: string[]; merged: string[]; dropped: number } | null>(null);
  const [reload, setReload] = useState(0);
  const [drafted, setDrafted] = useState("");
  const pasteRef = useRef<HTMLTextAreaElement>(null);
  const manager = isManager();

  useEffect(() => setPageTitle(`${name} — AI 로 정리`), [name]);
  useEffect(() => {
    if (!manager) return;
    let stale = false;   // 과제를 빨리 여러 번 바꾸면 늦게 온 옛 답이 새 글을 덮지 않게
    api
      .experiencePrompt(name, picked ?? undefined)
      .then((next) => {
        if (stale) return;
        setPrompt(next);
        if (picked === null) setPicked(next.projects);
      })
      .catch((error: Error) => { if (!stale) notifyError(error.message); });
    return () => { stale = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [name, picked?.join(","), reload]);

  const pending = Boolean(preview && !done && preview.blocks.length > 0);
  useEditedUnsaved(`experience-import:${name}`, paste.trim() || pending ? "1" : "0", "0", busy);

  if (!manager) {
    return (
      <section className="experience-import">
        <a className="back" href={personLink(name)}>← {name}의 이력</a>
        <div className="card"><p className="hint">AI 로 정리는 관리자 · 팀장 PC 에서 합니다.</p></div>
      </section>
    );
  }

  function toggle(id: string) {
    setPicked((prev) => {
      const now = prev ?? [];
      return now.includes(id) ? now.filter((item) => item !== id) : [...now, id];
    });
  }

  async function copyPrompt() {
    if (!prompt?.text) return;
    if (!(await copyText(prompt.text))) {
      notifyError(COPY_FAILED);
      return;
    }
    setCopied("prompt");
    window.setTimeout(() => setCopied(""), 1500);
    pasteRef.current?.focus();
  }

  function adopt(next: ImportPreview) {
    setPreview(next);
    setDone(null);
    setDecisions(Object.fromEntries(next.blocks.map((block) => [block.index, {
      index: block.index, action: block.action, target: block.target, project: block.project, choose: {},
    }])));
  }

  async function read(append: boolean) {
    if (!paste.trim()) return;
    setBusy(true);
    try {
      adopt(await api.readExperienceResponse({
        person: name, text: paste, projects: picked ?? [], append_to: append && preview ? preview.response : undefined,
      }));
      setPaste("");
    } catch (error) {
      notifyError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function decide(index: number, change: Partial<ImportDecision>) {
    setDecisions((prev) => {
      const next = { ...prev[index], ...change };
      if (change.target !== undefined) next.choose = {};
      return { ...prev, [index]: next };
    });
  }

  async function save() {
    if (!preview) return;
    setBusy(true);
    try {
      const items = preview.blocks.map((block) => {
        const d = decisions[block.index];
        return d.action === "이어서" && !d.target ? { ...d, action: "새로" as ImportAction } : d;
      });
      const result = await api.importExperiences({ person: name, response: preview.response, items });
      setDone(result);
    } catch (error) {
      notifyError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  /** 259 — 고른 과제 중 경험이 없는 과제의 초안을 먼저 만든다(비교 · 효과 금액 · ★성과 일지가 남게) */
  async function makeDrafts(ids: string[]) {
    setBusy(true);
    try {
      const result = await api.draftExperiences(name, ids);
      setDrafted(
        `초안 ${result.made.length}건을 만들었습니다(${result.made.join(" · ")}).` +
          (preview && !done ? " 이미 읽은 응답의 기본값은 [읽기]를 다시 해야 바뀝니다." : ""),
      );
      setReload((value) => value + 1);
    } catch (error) {
      notifyError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function copySummary() {
    if (!preview) return;
    try {
      const { text } = await api.experienceResponseSummary(name, preview.response);
      if (!(await copyText(text))) {
        notifyError(COPY_FAILED);
        return;
      }
      setCopied("summary");
      window.setTimeout(() => setCopied(""), 1500);
    } catch (error) {
      notifyError((error as Error).message);
    }
  }

  const missing = (prompt?.choices ?? []).filter((c) => (picked ?? []).includes(c.id) && !c.has_experience).map((c) => c.id);
  // 같은 경험에 이어서 저장할 블록 수 — 둘 이상이면 나눈 경험이 하나로 합쳐진다(259)
  const sharedCount: Record<string, number> = {};
  for (const d of Object.values(decisions)) if (d.action === "이어서" && d.target) sharedCount[d.target] = (sharedCount[d.target] ?? 0) + 1;
  const sharedTargets = Object.entries(sharedCount).filter(([, n]) => n > 1);
  const keep = preview ? preview.blocks.filter((block) => decisions[block.index]?.action !== "버림").length : 0;
  const targets = preview?.targets ?? [];
  return (
    <section className="experience-import" data-testid="experience-import">
      <a className="back" href={personLink(name)}>← {name}의 이력</a>
      <h1 className="import-title">{name} — AI 로 정리</h1>
      <p className="muted import-steps">① 과제 고르기 · 프롬프트 복사 → ② 사내 AI 응답 붙여넣기 → ③ 확인 · 저장(구조화)</p>
      <div className="import-columns">
        <div className="import-left">
          <div className="card">
            <IconTitle icon={Sparkles}>① 경험 정리 프롬프트</IconTitle>
            <div className="import-projects" role="group" aria-label="과제 고르기">
              {(prompt?.choices ?? []).length === 0 && <p className="muted">맡은 과제가 없습니다.</p>}
              {(prompt?.choices ?? []).map((choice) => (
                <label key={choice.id} className={choice.retro ? "" : "muted"}>
                  <input type="checkbox" checked={(picked ?? []).includes(choice.id)} onChange={() => toggle(choice.id)} />
                  <span className="project-id">{choice.id}</span> {choice.title}
                  <span className="muted"> · {choice.period}{choice.retro ? "" : " · 회고 없음"}{choice.structured ? " · 구조화 있음" : choice.has_experience ? " · 초안 있음" : " · 초안 없음"}</span>
                </label>
              ))}
            </div>
            {missing.length > 0 && (
              <div className="import-draft-first" data-testid="draft-first">
                <p className="hint">
                  초안이 없는 과제 <b>{missing.length}개</b> — 초안을 먼저 만들면 AI 값과 <b>비교해서 고를 수</b> 있고, 효과 금액 · ★성과 일지가 함께 남습니다.
                </p>
                <button className="ghost small" disabled={busy} onClick={() => void makeDrafts(missing)}>초안 만들기</button>
              </div>
            )}
            {drafted && <p className="hint notice">{drafted}</p>}
            <textarea className="refine-text import-prompt" readOnly value={prompt?.text ?? ""} aria-label="경험 정리 프롬프트"
              placeholder="과제를 고르면 프롬프트가 여기에 나옵니다." />
            <p className="hint import-note">ⓘ {PROMPT_NOTE}</p>
            <div className="form-actions">
              <span className="muted">{(prompt?.chars ?? 0).toLocaleString()}자 · 과제 {prompt?.projects.length ?? 0}개 · 기존 경험 {prompt?.existing ?? 0}건</span>
              <button disabled={!prompt?.text} onClick={() => void copyPrompt()}>{copied === "prompt" ? "복사됨 ✓" : "전문 복사"}</button>
            </div>
          </div>
          <div className="card">
            <IconTitle icon={ClipboardPaste}>② 응답 붙여넣기</IconTitle>
            <textarea ref={pasteRef} className="import-paste" value={paste} onChange={(event) => setPaste(event.target.value)}
              placeholder="사내 AI 의 응답 전체를 붙여 넣으세요 — 블록 밖 설명이 섞여 있어도 됩니다." aria-label="AI 응답" />
            <div className="form-actions">
              {preview && <span className="muted">응답 원문 {preview.response}</span>}
              {preview && (
                <button className="ghost" disabled={busy || !paste.trim()} onClick={() => void read(true)}
                  title="AI 가 나눠 출력했을 때 — 앞 응답에 이어 붙여 함께 읽습니다">더 붙여넣기</button>
              )}
              <button disabled={busy || !paste.trim()} onClick={() => void read(false)}>{busy ? "읽는 중…" : "읽기"}</button>
            </div>
          </div>
        </div>

        <div className="card import-right" data-testid="import-preview">
          <IconTitle icon={ListChecks}>③ 미리보기 · 저장</IconTitle>
          {!preview ? (
            <p className="muted">응답을 붙여 넣고 [읽기]를 누르면 여기에 블록이 나옵니다. 아직 아무것도 저장하지 않습니다.</p>
          ) : (
            <>
              <div className="import-summary">
                <span>블록 <b>{preview.blocks.length}</b></span>
                <span>읽은 줄 {preview.lines}</span>
                <span className={preview.bad_count ? "warn" : ""}>못 읽은 줄 {preview.bad_count}</span>
                <span className={preview.duplicates.length ? "warn" : ""}>중복 후보 {preview.duplicates.length}</span>
                <span className={preview.unknown_count ? "warn" : ""}>미분류 칸 {preview.unknown_count}</span>
                <button className="ghost small" onClick={() => void copySummary()}
                  title="값 없이 모양만(블록 수 · 못 읽은 줄의 사유 · 미분류 칸 이름 · 글자 수) — 실험 기록용">
                  {copied === "summary" ? "복사됨 ✓" : "실험 요약 복사"}
                </button>
              </div>
              {!done && sharedTargets.length > 0 && (
                <p className="form-warn import-shared" data-testid="shared-warning">
                  ⚠ 같은 경험에 이어서 저장할 블록이 있습니다({sharedTargets.map(([id, n]) => `${id} 에 ${n}블록`).join(" · ")}) — 나눈 경험이면 하나를 새 경험으로 고르세요.
                </p>
              )}
              {preview.blocks.length === 0 && (
                <div className="import-empty">
                  <p className="error">{NO_BLOCK}</p>
                </div>
              )}
              {done ? (
                <div className="import-done" data-testid="import-done">
                  <p>
                    경험 {done.made.length + done.merged.length}건을 저장했습니다(구조화)
                    {done.made.length > 0 && <> · 새로 {done.made.map((id) => <a key={id} href={experienceLink(id)}> {id}</a>)}</>}
                    {done.merged.length > 0 && <> · 이어서 {done.merged.map((id) => <a key={id} href={experienceLink(id)}> {id}</a>)}</>}
                    {done.dropped > 0 && <> · 버림 {done.dropped}</>}
                  </p>
                  <a className="button-link" href={personLink(name)}>이력의 [경험] 카드로</a>
                </div>
              ) : (
                <>
                  {preview.blocks.map((block) => {
                    const d = decisions[block.index];
                    if (!d) return null;
                    const target = d.action === "이어서" ? targets.find((t) => t.id === d.target) : undefined;
                    const rows = target ? conflicts(target, block) : [];
                    const dup = preview.duplicates.some((pair) => pair.includes(block.index));
                    const expanded = open.has(block.index);
                    return (
                      <div key={block.index} className={`import-block${d.action === "버림" ? " dropped" : ""}`} data-block={block.index}>
                        <div className="import-block-head">
                          <b>{block.fields.title}</b>
                          {dup && <span className="exp-status exp-초안" title="같은 응답 안에 제목 · 기간이 비슷한 블록이 있습니다">중복 후보</span>}
                        </div>
                        <p className="muted import-block-line">
                          {block.fields.start || "?"} ~ {block.fields.end || "?"} · {block.fields.role || "역할 없음"}
                        </p>
                        {block.warnings.length > 0 && (
                          <ul className="exp-warn-list">{block.warnings.map((w, i) => <li key={i}>⚠ {w.message}</li>)}</ul>
                        )}
                        {block.bad_lines.length > 0 && (
                          <ul className="exp-warn-list">{block.bad_lines.map((b) => <li key={b.line}>{b.line}번 줄 — {b.reason}: {b.text}</li>)}</ul>
                        )}
                        {(block.project_reason || block.action_reason) && (
                          <p className="muted import-reason">
                            기본값 —{block.project && block.project_reason ? ` 과제는 ${PROJECT_REASON[block.project_reason]}` : " 과제는 못 잡음"}
                            {block.action_reason ? ` · 저장은 ${ACTION_REASON[block.action_reason]}` : ""}
                          </p>
                        )}
                        {d.action === "이어서" && d.target && (sharedCount[d.target] ?? 0) > 1 && (
                          <p className="form-warn">⚠ 다른 블록도 {d.target} 에 이어 붙입니다 — 한 경험으로 합쳐집니다.</p>
                        )}
                        <div className="import-block-controls">
                          <label>
                            과제{" "}
                            <select value={d.project ?? ""} onChange={(event) => decide(block.index, { project: event.target.value })} aria-label="과제">
                              <option value="">(과제 없음)</option>
                              {preview.project_choices.map((p) => <option key={p.id} value={p.id}>{p.id} {p.title}</option>)}
                            </select>
                          </label>
                          {block.continues && (
                            <span className="muted" title={block.continues_known ? "" : "이 사람의 경험에 없는 번호입니다"}>
                              AI 제안: 이어짐 {block.continues}{block.continues_known ? "" : " (없는 번호)"}
                            </span>
                          )}
                        </div>
                        <div className="import-actions" role="radiogroup" aria-label="저장 방법">
                          {ACTIONS.map((action) => (
                            <label key={action}>
                              <input type="radio" name={`action-${block.index}`} checked={d.action === action}
                                onChange={() => decide(block.index, { action, target: action === "이어서" ? (d.target || targets[0]?.id || "") : d.target })} />
                              {action === "이어서" ? "기존 경험에 이어서" : action === "새로" ? "새 경험" : "버림"}
                            </label>
                          ))}
                          {d.action === "이어서" && (
                            <select value={d.target ?? ""} onChange={(event) => decide(block.index, { target: event.target.value })} aria-label="이어 붙일 경험">
                              {targets.length === 0 && <option value="">(이어 붙일 경험이 없습니다)</option>}
                              {targets.map((t) => <option key={t.id} value={t.id}>{t.id} {t.title} · {t.status}</option>)}
                            </select>
                          )}
                        </div>
                        {target && rows.length > 0 && (
                          <table className="grid import-compare">
                            <thead><tr><th>칸</th><th>기존 값{target.touched ? " (사람이 고침)" : ""}</th><th>AI 값</th></tr></thead>
                            <tbody>
                              {rows.map((row) => {
                                const pick = d.choose?.[row.field] ?? (target.touched ? "old" : "new");
                                const choose = (value: "old" | "new") => decide(block.index, { choose: { ...d.choose, [row.field]: value } });
                                return (
                                  <tr key={row.field} data-field={row.field}>
                                    <td>{row.label}</td>
                                    <td className={pick === "old" ? "picked" : ""}>
                                      <label><input type="radio" name={`c-${block.index}-${row.field}`} checked={pick === "old"} onChange={() => choose("old")} /> {row.old}</label>
                                    </td>
                                    <td className={pick === "new" ? "picked" : ""}>
                                      <label><input type="radio" name={`c-${block.index}-${row.field}`} checked={pick === "new"} onChange={() => choose("new")} /> {row.next}</label>
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        )}
                        {target && <p className="hint">빈 칸은 AI 값으로 채우고, 확인 필요 · 역량 태그 · 정량 · 증빙은 합칩니다.</p>}
                        <div className="import-block-foot">
                          <span className="muted">확인 필요 {block.counts.open} · 행동 {block.counts.action} · 정량 {block.counts.quant} · 역량 {block.counts.skill}</span>
                          <button className="ghost small" aria-expanded={expanded}
                            onClick={() => setOpen((prev) => { const next = new Set(prev); if (next.has(block.index)) next.delete(block.index); else next.add(block.index); return next; })}>
                            {expanded ? "접기" : "펼치기"}
                          </button>
                        </div>
                        {expanded && <BlockFields block={block} />}
                      </div>
                    );
                  })}
                  {preview.blocks.length > 0 && (
                    <div className="form-actions">
                      <button disabled={busy || keep === 0} onClick={() => void save()}>
                        {busy ? "저장하는 중…" : `저장 — ${keep}건 (구조화로)`}
                      </button>
                    </div>
                  )}
                </>
              )}
            </>
          )}
        </div>
      </div>
    </section>
  );
}

/** [펼치기] — 모든 칸 읽기 전용 */
function BlockFields({ block }: { block: ImportBlock }) {
  const f = block.fields;
  const rows: [string, string][] = [
    ["구분", f.kind], ["소속", f.affiliation], ["상황", f.situation], ["목표", f.goal], ["행동", f.actions.map((a) => `- ${a}`).join("\n")],
    ["정량", f.quants.map((q) => `${q.metric} | ${q.value} | 기준: ${q.baseline} (${q.baseline_kind}) | 시점: ${q.when}`).join("\n")],
    ["결과(정성)", f.result_qual], ["영향", f.impact], ["교훈", f.lesson + (f.lesson_source ? ` (${f.lesson_source})` : "")],
    ["역량", f.skills.map((s) => `${s.axis}: ${s.name}`).join(", ")], ["증빙", f.evidences.map((e) => e.text).join(", ")],
    ["확인 필요", f.open_questions.map((q) => `- ${q}`).join("\n")],
  ];
  return (
    <dl className="import-fields">
      {rows.filter(([, value]) => value.trim()).map(([label, value]) => (
        <div key={label}><dt>{label}</dt><dd>{value}</dd></div>
      ))}
    </dl>
  );
}
