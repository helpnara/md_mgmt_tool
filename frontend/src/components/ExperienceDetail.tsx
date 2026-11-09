import { useEffect, useState } from "react";
import { CircleHelp, FileText, Tags, TriangleAlert } from "lucide-react";
import { api } from "../api";
import { isManager } from "../me";
import { notifyError } from "../notify";
import { personLink, projectLink, setPageTitle } from "../nav";
import type { Experience, ExperienceQuant, ExperienceSkill } from "../types";
import IconTitle from "./IconTitle";
import { useEditedUnsaved } from "../util";

const AXES: ExperienceSkill["axis"][] = ["기술", "업무", "리더십", "문제해결"];
const KINDS: ExperienceQuant["baseline_kind"][] = ["비교", "집계", "조건", "미확인"];

/** 고칠 수 있는 칸만 — 저장할 때 이것을 보낸다 */
type Form = Pick<Experience, "title" | "start" | "end" | "role" | "kind" | "situation" | "goal" | "result_qual" | "impact" |
  "lesson" | "lesson_source" | "skills" | "quants"> & { actions: string; open_questions: string };

function toForm(item: Experience): Form {
  return {
    title: item.title, start: item.start, end: item.end, role: item.role, kind: item.kind, situation: item.situation,
    goal: item.goal, result_qual: item.result_qual, impact: item.impact, lesson: item.lesson, lesson_source: item.lesson_source,
    skills: item.skills.map((skill) => ({ ...skill })), quants: item.quants.map((quant) => ({ ...quant })),
    actions: item.actions.join("\n"), open_questions: item.open_questions.join("\n"),
  };
}

const lines = (text: string) => text.split("\n").map((line) => line.trim()).filter(Boolean);

/**
 * 경험 상세 (TODO 257 · 253 의 2단계 — 원본 UX S-05 의 2단계 몫).
 *
 * 2단계는 **초안**을 고친다. [확정하기] · 정합성 경고(4단계)와 AI 응답 붙여넣기(3단계)는 자리만 둔다.
 * 확인 필요는 본문 위(원본 원칙 4) — 남아 있으면 확정할 수 없다는 것을 늘 보이게.
 */
export default function ExperienceDetail({ id }: { id: string }) {
  const [item, setItem] = useState<Experience | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const editable = isManager();

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
          {editable && <button className="ghost danger" onClick={() => void remove()}>지우기</button>}
        </div>
        <p className="muted">
          {item.person}
          {item.project && (
            <> · 과제 {item.project_gone ? <span>{item.project} (지운 과제)</span> : <a href={projectLink(item.project)}>{item.project} {item.project_title}</a>}</>
          )}
          {" "}· 만든 때 {item.created_at.slice(0, 10)}{item.created_by ? ` (${item.created_by})` : ""} · 출처 {item.source}
        </p>
        <p className="hint experience-stage">
          지금은 <b>초안</b> 단계입니다 — AI 로 다듬어 붙여 넣는 [응답 되받기]와 [확정하기]는 다음 단계에서 붙습니다.
          {item.confirm_missing.length > 0 && <> 확정하려면: {item.confirm_missing.join(" / ")}</>}
        </p>
      </div>

      {/* 확인 필요 — 본문 위(원본 S-05) */}
      <div className={questions.length ? "card experience-questions has" : "card experience-questions"}>
        <IconTitle icon={CircleHelp}>확인 필요 {questions.length}건</IconTitle>
        <p className="hint">답한 질문은 지웁니다 — 남아 있으면 확정할 수 없습니다. 한 줄에 하나.</p>
        <textarea className="exp-lines" value={form.open_questions} readOnly={!editable} rows={Math.max(3, questions.length + 1)}
          onChange={(event) => set("open_questions", event.target.value)} aria-label="확인 필요" />
      </div>

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
          <p className="hint">역량 사전에 맞추기는 다음 단계 — 지금은 적힌 그대로입니다.</p>
          <ul className="exp-skill-list">
            {form.skills.map((skill, index) => (
              <li key={index}>
                <select aria-label="축" disabled={!editable} value={skill.axis} onChange={(event) => setSkill(index, { axis: event.target.value as ExperienceSkill["axis"] })}>
                  {AXES.map((axis) => <option key={axis}>{axis}</option>)}
                </select>
                <input aria-label="역량 태그" disabled={!editable} value={skill.name} onChange={(event) => setSkill(index, { name: event.target.value })} />
                {editable && <button type="button" className="ghost small danger" onClick={() => set("skills", form.skills.filter((_, i) => i !== index))}>빼기</button>}
              </li>
            ))}
          </ul>
          {editable && <button type="button" className="ghost small" onClick={() => set("skills", [...form.skills, { axis: "기술", name: "" }])}>+ 역량 태그</button>}
          {item.materials.length > 0 && (
            <>
              <h3>재료 — ★성과 일지</h3>
              <ul className="exp-materials">
                {item.materials.map((text) => <li key={text}>{text.replace(/^entry:\d+\s*/, "")}</li>)}
              </ul>
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
