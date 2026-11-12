import { useEffect, useState } from "react";
import { CircleHelp, FileText, Tags, TriangleAlert } from "lucide-react";
import { api } from "../api";
import { getMe, isManager, isMember } from "../me";
import { notifyError } from "../notify";
import { personLink, projectLink, setPageTitle } from "../nav";
import type { ConsistencyWarning, Experience, ExperienceQuant, ExperienceResponseFile, ExperienceSkill, SkillDictionary } from "../types";
import { ConfirmBar, ConsistencyCard, QuestionAnswers, guessKind, type AnswerTarget } from "./ExperienceConfirm";
import IconTitle from "./IconTitle";
import QuantGuide from "./QuantGuide";
import { useEditedUnsaved, axisLabel } from "../util";

const AXES: ExperienceSkill["axis"][] = ["기술", "업무", "리더십", "문제해결"];
const KINDS: ExperienceQuant["baseline_kind"][] = ["비교", "집계", "조건", "미확인"];

/** 고칠 수 있는 칸만 — 저장할 때 이것을 보낸다 */
type Form = Pick<Experience, "title" | "start" | "end" | "role" | "kind" | "situation" | "goal" | "result_qual" | "impact" |
  "lesson" | "lesson_source" | "skills" | "quants"> & { actions: string; open_questions: string; tools: string };

function toForm(item: Experience): Form {
  return {
    title: item.title, start: item.start, end: item.end, role: item.role, kind: item.kind, situation: item.situation,
    goal: item.goal, result_qual: item.result_qual, impact: item.impact, lesson: item.lesson, lesson_source: item.lesson_source,
    skills: item.skills.map((skill) => ({ ...skill })), quants: item.quants.map((quant) => ({ ...quant })),
    actions: item.actions.join("\n"), open_questions: item.open_questions.join("\n"), tools: (item.tools ?? []).join(", "),
  };
}

const lines = (text: string) => text.split("\n").map((line) => line.trim()).filter(Boolean);

/**
 * 경험 상세 (TODO 257 · 253 의 2단계 — 원본 UX S-05 의 2단계 몫).
 *
 * 초안 · 구조화를 고친다(구조화는 고쳐도 구조화 — 3단계.md ⑨). [확정하기] · 정합성 경고(4단계)는 자리만 둔다.
 * 응답 되받기(TODO 258)로 만든 경험은 재료에 **AI 응답 원문**이 걸린다 — 눌러서 읽기 전용으로 본다.
 * 확인 필요는 본문 위(원본 원칙 4) — 남아 있으면 확정할 수 없다는 것을 늘 보이게.
 */
export default function ExperienceDetail({ id }: { id: string }) {
  const [item, setItem] = useState<Experience | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [raw, setRaw] = useState<ExperienceResponseFile | null>(null);
  const [dictionary, setDictionary] = useState<SkillDictionary | null>(null);
  const manager = isManager();
  // 팀원 보완 (TODO 262 · 5단계.md ⑦) — 팀원 PC 는 자기 경험의 초안 · 구조화만 고친다(확정 · 확인함 · 지우기는 팀장)
  const editable = manager || Boolean(item && isMember() && getMe().name === item.person && item.status !== "확정");

  // 역량 사전 (TODO 260) — "사전에 없음" 의 [기존 역량으로 ▾] · 태그 입력 자동 완성이 쓴다
  useEffect(() => {
    if (!editable) return;
    api.experienceSkills().then(setDictionary).catch(() => setDictionary(null));
  }, [editable]);

  useEffect(() => {
    api
      .experience(id)
      .then((next) => {
        setItem(next);
        setForm(toForm(next));
        setPageTitle(`${next.id} ${next.title}`);
      })
      .catch((err: Error) => setError(err.message));
  }, [id]);

  const dirty = Boolean(item && form && JSON.stringify(form) !== JSON.stringify(toForm(item)));
  useEditedUnsaved(`experience:${id}`, dirty ? "1" : "0", "0", busy);

  if (error) return <section className="experience-detail"><div className="card"><p className="error">{error}</p></div></section>;
  if (!item || !form) return <section className="experience-detail"><p className="muted">불러오는 중…</p></section>;

  async function openRaw(name: string) {
    try {
      setRaw(await api.experienceResponse(item!.person, name));
    } catch (err) {
      notifyError((err as Error).message);
    }
  }

  const set = <K extends keyof Form>(key: K, value: Form[K]) => setForm({ ...form, [key]: value });
  const setQuant = (index: number, patch: Partial<ExperienceQuant>) =>
    set("quants", form.quants.map((quant, i) => (i === index ? { ...quant, ...patch } : quant)));
  const setSkill = (index: number, patch: Partial<ExperienceSkill>) =>
    set("skills", form.skills.map((skill, i) => (i === index ? { ...skill, ...patch } : skill)));

  async function save() {
    if (!form || !item) return;
    setBusy(true);
    try {
      const next = await api.updateExperience(item.id, {
        ...form, actions: lines(form.actions), open_questions: lines(form.open_questions),
        tools: form.tools.split(",").map((tool) => tool.trim()).filter(Boolean),
        skills: form.skills.filter((skill) => skill.name.trim()), quants: form.quants.filter((quant) => quant.metric.trim()),
        base_updated_at: item.updated_at,
      } as Partial<Experience> & { base_updated_at: string });
      setItem(next);
      setForm(toForm(next));
      setNotice("저장했습니다.");
      window.setTimeout(() => setNotice(""), 3000);
    } catch (err) {
      notifyError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  /** 서버가 돌려준 경험으로 바꾼다 — 고치던 칸이 없을 때만 부른다 */
  function adopt(next: Experience, message: string) {
    setItem(next);
    setForm(toForm(next));
    setNotice(message);
    window.setTimeout(() => setNotice(""), 3000);
  }

  async function act(run: () => Promise<Experience>, message: string) {
    setBusy(true);
    try {
      adopt(await run(), message);
    } catch (err) {
      notifyError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function ack(warning: ConsistencyWarning) {
    if (dirty) {
      notifyError("고친 것을 먼저 저장하세요 — [확인함]은 저장한 내용에 붙습니다.");
      return;
    }
    void act(() => api.acknowledgeWarning(item!.id, warning.code, warning.key), `${warning.code} 을(를) 확인함으로 넘겼습니다.`);
  }

  /** 확인 필요 [반영] — 답을 고른 칸 끝에 덧붙이고 질문을 지운다(저장은 [저장]으로) */
  function applyAnswer(question: string, answer: string, target: AnswerTarget) {
    if (!form) return;
    const rest = lines(form.open_questions).filter((q) => q !== question).join("\n");
    const next: Form = { ...form, open_questions: rest };
    if (target.startsWith("quant:")) {
      const index = Number(target.slice(6));
      next.quants = form.quants.map((q, i) => (i === index ? { ...q, baseline: answer, baseline_kind: q.baseline_kind === "미확인" ? guessKind(answer) : q.baseline_kind } : q));
    } else if (target === "actions") {
      next.actions = [form.actions.trim(), answer].filter(Boolean).join("\n");
    } else {
      const key = target as "role" | "situation" | "goal" | "result_qual" | "impact" | "lesson";
      const old = String(form[key] ?? "").trim();
      next[key] = old ? (key === "role" || key === "impact" ? `${old} / ${answer}` : `${old}\n${answer}`) : answer;
    }
    setForm(next);
    setNotice("반영했습니다 — [저장]을 눌러야 남습니다.");
  }

  function dropQuestion(question: string) {
    if (!form) return;
    set("open_questions", lines(form.open_questions).filter((q) => q !== question).join("\n"));
  }

  async function addToDictionary(skill: ExperienceSkill) {
    if (!dictionary) return;
    try {
      await api.saveSettings({ skill_dictionary: [...dictionary.dictionary, { axis: skill.axis, name: skill.name, aliases: [] }] });
      setDictionary(await api.experienceSkills());
      setItem({ ...item!, skills_unknown: item!.skills_unknown.filter((name) => name !== skill.name) });
      setNotice(`역량 사전에 ‘${skill.name}’ 을(를) 더했습니다.`);
    } catch (err) {
      notifyError((err as Error).message);
    }
  }

  async function remove() {
    if (!item || !window.confirm(`${item.id} ${item.title} — 삭제 보관함으로 옮길까요? 번호는 다시 쓰지 않습니다.`)) return;
    try {
      await api.deleteExperience(item.id);
      window.location.hash = personLink(item.person);
    } catch (err) {
      notifyError((err as Error).message);
    }
  }

  const warnings = item.problems.filter((problem) => problem.level === "경고");
  const questions = lines(form.open_questions);
  return (
    <section className="experience-detail">
      <a className="back" href={personLink(item.person)}>← {item.person}의 이력</a>
      <div className="card experience-head">
        <div className="card-head">
          <h1>
            <span className="project-id">{item.id}</span> {item.title}
            <span className={`exp-status exp-${item.status}`}>{item.status}</span>
          </h1>
          {manager && (
            <span className="exp-head-actions">
              <ConfirmBar item={item} dirty={dirty} busy={busy}
                onConfirm={() => void act(() => api.confirmExperience(item.id), "확정했습니다.")}
                onUnconfirm={() => void act(() => api.unconfirmExperience(item.id), "구조화로 되돌렸습니다.")} />
              <button className="ghost danger" onClick={() => void remove()}>지우기</button>
            </span>
          )}
        </div>
        <p className="muted">
          {item.person}
          {item.project && (
            <> · 과제 {item.project_gone ? <span>{item.project} (지운 과제)</span> : <a href={projectLink(item.project)}>{item.project} {item.project_title}</a>}</>
          )}
          {item.edited_by_member_at && (
            <> · <span className="exp-member-edit" title="팀원이 자기 PC 에서 보완했습니다 — 확정하면 표시가 지워집니다">팀원이 고침 {item.edited_by_member_at.slice(5, 10)}</span></>
          )}
          {" "}· 만든 때 {item.created_at.slice(0, 10)}{item.created_by ? ` (${item.created_by})` : ""} · 출처 {item.source}
        </p>
        <p className="hint experience-stage">
          {item.status === "확정"
            ? <>팀장이 검토해 사실로 인정한 <b>확정</b> 경험입니다 — 고쳐도 상태는 그대로, 업무 이력 파일(다음 단계)에 들어갑니다.</>
            : item.status === "초안"
              ? <>지금은 <b>초안</b>입니다 — [AI 로 정리]로 다듬거나 손으로 채운 뒤, 조건 다섯이 맞으면 확정합니다.</>
              : <>AI 응답을 읽어 채운 <b>구조화</b> 경험입니다 — 검토하고 조건 다섯이 맞으면 확정합니다.</>}
        </p>
      </div>

      {/* 확인 필요 — 본문 위(원본 S-05) */}
      <div className={questions.length ? "card experience-questions has" : "card experience-questions"}>
        <IconTitle icon={CircleHelp}>확인 필요 {questions.length}건</IconTitle>
        <p className="hint">답을 적고 <b>[반영]</b>하면 고른 칸에 들어가고 질문이 지워집니다. [해당 없음]은 질문만 지웁니다. 남아 있으면 확정할 수 없습니다.</p>
        <QuestionAnswers questions={questions} quants={form.quants} editable={editable} onApply={applyAnswer} onDrop={dropQuestion} />
        <textarea className="exp-lines" value={form.open_questions} readOnly={!editable} rows={Math.max(3, questions.length + 1)}
          onChange={(event) => set("open_questions", event.target.value)} aria-label="확인 필요" />
      </div>

      <ConsistencyCard warnings={item.consistency} editable={manager} busy={busy} onAck={ack} />

      {warnings.length > 0 && (
        <div className="card experience-warnings">
          <IconTitle icon={TriangleAlert}>검사 {warnings.length}건</IconTitle>
          <ul className="exp-warn-list">
            {warnings.map((problem, index) => <li key={index}>{problem.message}</li>)}
          </ul>
        </div>
      )}

      <div className="experience-columns">
        <div className="card experience-body">
          <IconTitle icon={FileText}>본문</IconTitle>
          <fieldset disabled={!editable} className="exp-fields">
            <label>제목<input value={form.title} onChange={(event) => set("title", event.target.value)} /></label>
            <div className="form-row">
              <label>시작<input value={form.start} placeholder="2026-03" onChange={(event) => set("start", event.target.value)} /></label>
              <label>끝<input value={form.end} placeholder="비우면 진행 중" onChange={(event) => set("end", event.target.value)} /></label>
              <label>구분
                <select value={form.kind} onChange={(event) => set("kind", event.target.value)}>
                  <option value="">—</option><option>업무</option><option>업무 외</option>
                </select>
              </label>
            </div>
            <label>역할<input value={form.role} placeholder="본인이 한 일 / 다른 주체(팀원 · 외부 · 도구)가 한 일" onChange={(event) => set("role", event.target.value)} /></label>
            <label>상황<textarea rows={3} value={form.situation} onChange={(event) => set("situation", event.target.value)} /></label>
            <label>목표<textarea rows={2} value={form.goal} onChange={(event) => set("goal", event.target.value)} /></label>
            <label>행동 <span className="muted">— 한 줄에 하나</span>
              <textarea className="exp-lines" rows={4} value={form.actions} onChange={(event) => set("actions", event.target.value)} />
            </label>
            <div className="exp-quants">
              <span className="exp-label">결과 · 정량</span>
              <div className="table-scroll">
                <table className="grid exp-quant-table">
                  <thead><tr><th>지표</th><th>값</th><th>기준</th><th>종류</th><th>시점</th>{editable && <th />}</tr></thead>
                  <tbody>
                    {form.quants.map((quant, index) => (
                      <tr key={index}>
                        <td><input aria-label="지표" value={quant.metric} onChange={(event) => setQuant(index, { metric: event.target.value })} /></td>
                        <td><input aria-label="값" value={quant.value} onChange={(event) => setQuant(index, { value: event.target.value })} /></td>
                        <td><input aria-label="기준" value={quant.baseline} placeholder="기준 없음" onChange={(event) => setQuant(index, { baseline: event.target.value })} /></td>
                        <td>
                          <select aria-label="종류" value={quant.baseline_kind} onChange={(event) => setQuant(index, { baseline_kind: event.target.value as ExperienceQuant["baseline_kind"] })}>
                            {KINDS.map((kind) => <option key={kind}>{kind}</option>)}
                          </select>
                        </td>
                        <td><input aria-label="시점" value={quant.when} onChange={(event) => setQuant(index, { when: event.target.value })} /></td>
                        {editable && <td><button type="button" className="ghost small danger" onClick={() => set("quants", form.quants.filter((_, i) => i !== index))}>빼기</button></td>}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {editable && (
                <button type="button" className="ghost small" onClick={() => set("quants", [...form.quants, { metric: "", value: "", baseline: "", baseline_kind: "미확인", when: "" }])}>
                  + 정량 성과
                </button>
              )}
              {/* 283 — 칸 뜻 · 대표 예시(전극봉 원단위 절감) · 여러 경우 · 자주 하는 실수. 고칠 수 있으면 [표에 넣기] */}
              <details className="quant-guide-box" data-testid="quant-guide-box">
                <summary>작성 예시 ▾ — 지표 · 값 · 기준 · 종류 · 시점을 어떻게 쓰나</summary>
                <QuantGuide onPick={editable ? (quant) => set("quants", [...form.quants, quant]) : undefined} />
              </details>
            </div>
            <label>결과 · 정성<textarea rows={3} value={form.result_qual} onChange={(event) => set("result_qual", event.target.value)} /></label>
            <label>업무 영향<input value={form.impact} onChange={(event) => set("impact", event.target.value)} /></label>
            <div className="form-row">
              <label className="grow">교훈<textarea rows={2} value={form.lesson} onChange={(event) => set("lesson", event.target.value)} /></label>
              <label>출처<input value={form.lesson_source} onChange={(event) => set("lesson_source", event.target.value)} /></label>
            </div>
          </fieldset>
          {notice && <p className="hint notice">{notice}</p>}
          {editable && (
            <div className="form-actions">
              <button disabled={busy || !dirty} onClick={() => void save()}>{busy ? "저장 중…" : "저장"}</button>
            </div>
          )}
        </div>

        <div className="card experience-side">
          <IconTitle icon={Tags}>역량 태그 · 재료</IconTitle>
          <p className="hint">저장하면 역량 사전의 이름 · 축으로 맞춥니다. 사전에 없는 태그는 그대로 두고 표시만 합니다(확정은 막지 않음).</p>
          <ul className="exp-skill-list">
            {form.skills.map((skill, index) => (
              <li key={index}>
                <select aria-label="축" disabled={!editable} value={skill.axis} onChange={(event) => setSkill(index, { axis: event.target.value as ExperienceSkill["axis"] })}>
                  {AXES.map((axis) => <option key={axis} value={axis}>{axisLabel(axis)}</option>)}
                </select>
                <input aria-label="역량 태그" list="exp-skill-names" disabled={!editable} value={skill.name}
                  onChange={(event) => {
                    // 사전의 이름 · 다른 이름을 고르면 축도 사전의 것으로(역량태그입력.md — 입력할 때 맞추기)
                    const hit = dictionary?.dictionary.find((d) => d.name === event.target.value || d.aliases.includes(event.target.value));
                    setSkill(index, hit ? { name: hit.name, axis: hit.axis } : { name: event.target.value });
                  }} />
                {editable && <button type="button" className="ghost small danger" onClick={() => set("skills", form.skills.filter((_, i) => i !== index))}>빼기</button>}
                {item.skills_unknown.includes(skill.name) && item.skills.some((s) => s.name === skill.name && s.axis === skill.axis) && (
                  <span className="exp-unknown" data-unknown={skill.name}>
                    <span className="exp-unknown-tag">사전에 없음</span>
                    {editable && dictionary && (
                      <>
                        {manager && <button type="button" className="link-button" onClick={() => void addToDictionary(skill)}>사전에 추가</button>}
                        <select aria-label="기존 역량으로" value="" onChange={(event) => {
                          const [axis, name] = event.target.value.split("|");
                          if (name) setSkill(index, { axis: axis as ExperienceSkill["axis"], name });
                        }}>
                          <option value="">기존 역량으로 ▾</option>
                          {dictionary.dictionary.filter((d) => d.axis === skill.axis).map((d) => <option key={d.name} value={`${d.axis}|${d.name}`}>{d.name}</option>)}
                        </select>
                      </>
                    )}
                  </span>
                )}
              </li>
            ))}
          </ul>
          {editable && <button type="button" className="ghost small" onClick={() => set("skills", [...form.skills, { axis: "기술", name: "" }])}>+ 역량 태그</button>}
          {dictionary && (
            <datalist id="exp-skill-names">
              {dictionary.dictionary.flatMap((d) => [d.name, ...d.aliases]).map((name) => <option key={name} value={name} />)}
            </datalist>
          )}
          <label className="exp-tools">보유 기술(도구) <span className="muted">— 무엇으로 했는가: 프로그래밍 언어 · 소프트웨어 · 장비(쉼표로, 사전의 대표 이름으로 맞춰집니다). 분석 기법 · 방법은 위의 역량 태그에. 역량 태그와 따로 업무 이력 파일에 들어갑니다</span>
            <input aria-label="보유 기술(도구)" disabled={!editable} value={form.tools} placeholder="Python, SQL" onChange={(event) => set("tools", event.target.value)} />
          </label>
          {/* 확정 전에 알린다 — 막지 않는다 (TODO 273) */}
          {(item.tool_notes ?? []).map((note) => <p key={note} className="hint exp-tool-note" data-testid="tool-note">ⓘ {note}</p>)}
          {item.materials.length > 0 && (
            <>
              <h3>재료 — ★성과 일지 · AI 응답 원문</h3>
              <ul className="exp-materials">
                {item.materials.map((text) =>
                  text.startsWith("response:") ? (
                    <li key={text}>
                      <button type="button" className="link-button" data-response={text.slice(9)} onClick={() => void openRaw(text.slice(9))}>
                        AI 응답 원문 {text.slice(9)}
                      </button>
                    </li>
                  ) : (
                    <li key={text}>{text.replace(/^entry:\d+\s*/, "")}</li>
                  ),
                )}
              </ul>
              {raw && (
                <div className="exp-raw" data-testid="experience-raw">
                  <div className="exp-raw-head">
                    <b>AI 응답 원문 {raw.name}</b>
                    <span className="muted">고치지 않습니다</span>
                    <button type="button" className="ghost small" onClick={() => setRaw(null)}>닫기</button>
                  </div>
                  <pre>{raw.text}</pre>
                </div>
              )}
            </>
          )}
          {item.evidences.length > 0 && (
            <>
              <h3>증빙</h3>
              <ul className="exp-materials">{item.evidences.map((evidence, index) => <li key={index}>{evidence.type} · {evidence.text}</li>)}</ul>
            </>
          )}
          <p className="muted exp-stamps">고친 때 {item.updated_at.slice(0, 16).replace("T", " ")}</p>
        </div>
      </div>
    </section>
  );
}
