import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { getMe, isManager } from "../me";
import { personLink, projectLink } from "../nav";
import { isLeader, leftLabel } from "../people";
import type { Contribution, Meta, Milestone, Project } from "../types";
import Explain from "./Explain";
import { RetroField, RetroText } from "./RetroText";
import { DoneCard } from "./YearCard";

/**
 * 담당과 역할 (TODO 237 · 239) — 사람마다 역할 · 맡은 부분 · 보유 기술 · 담당 기간 · 회고(내가 한 일 · 결과).
 * 회고는 둘 — 배경 · 목적은 과제 개요에 있어 담당자마다 적지 않는다(239 ⑤).
 *
 * 팀원이 나중에 본인의 업무 이력 · 성과를 정리할 때의 재료다. 업무 이력 한 줄은 **과제 · 기간 · 내 역할 · 내가 한 일 · 성과**인데,
 * 담당자 명단만으로는 셋을 알 수 없다. 화면 · 내보내기는 나중에 붙여도 되지만 **기록은 지금부터 쌓지 않으면 되살릴 수 없다.**
 *
 * * 팀장은 누구 줄이든, 팀원은 **자기 줄만** 고친다(담당 기간은 팀장). 숨기는 것은 편의 — 막는 것은 서버다.
 * * 담당 기간은 담당자를 바꾸면 저절로 적힌다. 기록이 없는 담당자는 시작일부터로 읽는다(흐린 "시작일부터").
 * * 완료로 바꾸는 순간 상세 화면이 내 줄의 양식을 열어 준다(`openFor`).
 */

export const ROLES = ["주관", "참여", "지원"] as const;

const RETRO = [
  { key: "did", label: "내가 한 일", placeholder: "예: 집계 스크립트를 만들고 현장 담당자 교육" },
  { key: "result", label: "결과", placeholder: "예: 주 4시간 → 30분, 집계 오류 0건" },
] as const;

type RetroKey = (typeof RETRO)[number]["key"];

/** 지금의 나 — 팀원 PC 면 그 사람, 서버 PC 면 명부의 팀장 */
export function myName(meta: Meta): string {
  const me = getMe();
  if (me.role === "member") return me.name;
  if (isManager(me)) return meta.leader || "";
  return "";
}

function hasRetro(row: Contribution): boolean {
  return Boolean(row.did || row.result);
}

function endText(row: Contribution, project: Project): string {
  if (row.to) return row.to;
  if (!row.current) return "?";
  if (project.status === "done") return project.completed_at ?? "완료";
  if (project.status === "dropped") return "중단";
  return "지금";
}

export default function ContributionsCard({
  project,
  meta,
  onSaved,
  openFor,
  onOpened,
  celebrate = false,
}: {
  project: Project;
  meta: Meta;
  onSaved: (saved: Project) => void;
  /** 방금 완료로 바꿨다 — 마친 과제 띠를 강조 (TODO 244 A4) */
  celebrate?: boolean;
  /** 이 사람의 양식을 열어 둔다 — 완료로 바꾼 직후 */
  openFor?: string | null;
  onOpened?: () => void;
}) {
  const rows = project.contributions ?? [];
  const me = getMe();
  const [editing, setEditing] = useState<string | null>(null);
  const [justDone, setJustDone] = useState(false);
  const card = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!openFor) return;
    if (rows.some((row) => row.name === openFor)) {
      setEditing(openFor);
      setJustDone(true);
      window.setTimeout(() => card.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
    }
    onOpened?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openFor]);

  const canEdit = (name: string) =>
    isManager(me) || (me.role === "member" && name === me.name && me.projects.includes(project.id));

  return (
    <div className="card contributions-card" ref={card} data-contributions>
      <div className="card-head">
        <h2>담당과 역할</h2>
      </div>
      {project.done_summary && <DoneCard summary={project.done_summary} fresh={celebrate} />}
      <Explain
        id="contributions"
        lead={<>사람마다 <b>역할 · 맡은 부분 · 보유 기술 · 담당 기간 · 회고</b>를 남깁니다 — 나중에 본인의 업무 이력 · 성과를 정리할 때의 재료입니다.</>}
      >
        담당 기간은 담당자를 바꾸면 저절로 적힙니다(든 사람은 그날부터, 빠진 사람은 그날까지). 기록이 없던 담당자는 시작일부터로 읽습니다.
        팀원은 자기 줄의 역할 · 맡은 부분 · 회고를 고치고, 담당 기간은 팀장이 고칩니다. 과제 [내보내기]에도 이 내용이 함께 나갑니다.
      </Explain>
      {rows.length === 0 ? (
        <p className="muted">담당자가 없습니다 — [과제 정보 수정]에서 담당자를 정하면 여기에 줄이 생깁니다.</p>
      ) : (
        <ul className="contrib-list">
          {rows.map((row) => (
            <li key={row.name} className={row.current ? "contrib-row" : "contrib-row former"} data-person={row.name}>
              <div className="contrib-main">
                <span className="contrib-name">
                  <a href={personLink(row.name)} title={`${row.name} — 이력`}>{row.name}</a>
                  {isLeader(meta, row.name) && <span className="tag leader-tag">팀장</span>}
                  {!row.current && <span className="tag former-tag">예전 담당</span>}
                  {leftLabel(meta, row.name) && <span className="tag left-tag">{leftLabel(meta, row.name)}</span>}
                </span>
                <span className={row.role ? "contrib-role" : "contrib-role muted"}>{row.role || "역할 미정"}</span>
                <span className="contrib-part">{row.part || <span className="muted">맡은 부분 —</span>}</span>
                <span className="contrib-period" title={row.derived ? "기록이 없어 과제 시작일부터로 읽었습니다" : undefined}>
                  {row.from ?? "?"} ~ {endText(row, project)}
                  {row.derived && <span className="muted"> · 시작일부터</span>}
                </span>
                <span className={hasRetro(row) ? "retro-state retro-written" : "retro-state retro-missing"}>
                  {hasRetro(row) ? "회고 ✓" : "회고 비어 있음"}
                </span>
                {canEdit(row.name) && editing !== row.name && (
                  <button data-write className="ghost" onClick={() => setEditing(row.name)}>
                    {hasRetro(row) || row.role || row.part || row.skills.length > 0 || (row.milestones?.length ?? 0) > 0 ? "고치기" : "적기"}
                  </button>
                )}
              </div>
              {row.skills.length > 0 && editing !== row.name && (
                <div className="skill-chips">
                  {row.skills.map((item) => (
                    <span key={item} className="skill-chip">{item}</span>
                  ))}
                </div>
              )}
              {(row.milestones?.length ?? 0) > 0 && editing !== row.name && (
                <ul className="milestone-list">
                  {row.milestones!.map((item) => (
                    <li key={`${item.date}-${item.text}`}><span className="due">{item.date}</span>{item.text}</li>
                  ))}
                </ul>
              )}
              {/* 팀장의 인정 한 줄 (TODO 242 A2) — 서버가 그 사람과 팀장에게만 준다 */}
              {row.praise && editing !== row.name && (
                <p className="praise-line">
                  <span className="praise-label">팀장</span>“{row.praise}”
                  {row.praise_at && <span className="muted"> · {row.praise_at}</span>}
                  <span className="muted praise-private"> · 이 사람과 팀장만 봅니다</span>
                </p>
              )}
              {hasRetro(row) && editing !== row.name && (
                <dl className="contrib-retro">
                  {RETRO.map((item) =>
                    row[item.key] ? (
                      <div key={item.key}>
                        <dt>{item.label}</dt>
                        <dd><RetroText text={row[item.key]} clamp /></dd>
                      </div>
                    ) : null,
                  )}
                </dl>
              )}
              {editing === row.name && (
                <ContributionForm
                  project={project}
                  row={row}
                  ownerView={isManager(me)}
                  // 인정 한 줄은 팀장이 팀원에게 — 명부의 팀장 자신의 줄에는 두지 않는다
                  praiseEditable={isManager(me) && !isLeader(meta, row.name)}
                  justDone={justDone}
                  onCancel={() => {
                    setEditing(null);
                    setJustDone(false);
                  }}
                  onSaved={(saved) => {
                    setEditing(null);
                    setJustDone(false);
                    onSaved(saved);
                  }}
                />
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function ContributionForm({
  project,
  row,
  ownerView,
  praiseEditable,
  justDone,
  onCancel,
  onSaved,
}: {
  project: Project;
  row: Contribution;
  ownerView: boolean;
  praiseEditable: boolean;
  justDone: boolean;
  onCancel: () => void;
  onSaved: (saved: Project) => void;
}) {
  const [role, setRole] = useState(row.role);
  const [part, setPart] = useState(row.part);
  // 보유 기술 (TODO 239) — 쉼표로. 팀에서 쓴 것을 골라 넣을 수 있다
  const [skills, setSkills] = useState(row.skills.join(", "));
  const chosenSkills = skills.split(",").map((item) => item.trim()).filter(Boolean);
  const chosenKeys = new Set(chosenSkills.map((item) => item.toLowerCase()));
  const suggestions = (project.known_skills ?? []).filter((item) => !chosenKeys.has(item.toLowerCase())).slice(0, 12);
  // 담당 기간의 기본값 = 과제 수행 기간 (TODO 239 ④) — 비어 있는 칸만 채운다. 끝은 완료한 과제면 완료일, 아니면 마감일.
  // 팀장 양식에서만 — 팀원은 기간을 저장하지 않으므로(서버가 막는다) 채워 보이면 저장된 값으로 오해한다.
  // 시작보다 빠른 끝(마감이 지난 과제에 오늘 든 사람)은 채우지 않는다 — 그대로 저장하면 400 이다.
  const defaultFrom = row.from ?? project.start_date ?? "";
  const projectEnd = (project.status === "done" ? project.completed_at : project.due_date) ?? "";
  const defaultTo = row.to ?? (row.current && projectEnd && (!defaultFrom || projectEnd >= defaultFrom) ? projectEnd : "");
  const [from, setFrom] = useState(ownerView ? defaultFrom : row.from ?? "");
  const [to, setTo] = useState(ownerView ? defaultTo : row.to ?? "");
  const [praise, setPraise] = useState(row.praise ?? "");
  // 중간 성과 (TODO 243 B2) — 날짜 + 한 줄, 여럿. 빈 줄은 저장할 때 버린다
  const [milestones, setMilestones] = useState<Milestone[]>(() => [...(row.milestones ?? [])]);
  const setMilestone = (index: number, key: keyof Milestone, value: string) =>
    setMilestones((prev) => prev.map((item, i) => (i === index ? { ...item, [key]: value } : item)));
  const stars = project.star_entries ?? [];
  const filledFromProject = ownerView && ((!row.from && Boolean(defaultFrom)) || (!row.to && Boolean(defaultTo)));
  const [retro, setRetro] = useState<Record<RetroKey, string>>({ did: row.did, result: row.result });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // 연 때의 수정 시각 — 그 사이 누가 먼저 고쳤으면 409 (TODO 233 R7)
  const base = useRef(project.updated_at);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const saved = await api.updateContribution(project.id, row.name, {
        role,
        part,
        skills: chosenSkills,
        ...(praiseEditable ? { praise: praise.trim() } : {}),
        milestones: milestones.filter((item) => item.date || item.text.trim()),
        ...retro,
        // 팀원은 기간을 보내지 않는다(서버가 막는다 — 팀장이 고친다)
        ...(ownerView ? { from: from || null, to: to || null } : {}),
        ...(base.current ? { base_updated_at: base.current } : {}),
      });
      onSaved(saved);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      className="contrib-form"
      onSubmit={(event) => {
        event.preventDefault();
        void save();
      }}
    >
      {justDone && (
        <p className="contrib-done-note">
          과제가 끝났습니다 — 기억이 생생할 때 <b>회고</b>(내가 한 일 · 결과)를 남겨 두세요. 비워 두고 닫아도 됩니다(홈 [할 일]에 1년 동안 남습니다).
        </p>
      )}
      <div className="contrib-form-row">
        <label className="contrib-role-label">
          역할
          <select value={role} onChange={(event) => setRole(event.target.value)} aria-label="역할">
            <option value="">정하지 않음</option>
            {ROLES.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        <label className="contrib-part-label">
          <span>맡은 부분 <span className="muted">(한 줄)</span></span>
          <input value={part} maxLength={100} onChange={(event) => setPart(event.target.value)}
                 placeholder="예: 데이터 수집 · 분석 모델" aria-label="맡은 부분" />
        </label>
      </div>
      <div className="contrib-form-row">
        <label className="contrib-skills-label">
          <span>보유 기술 <span className="muted">(쉼표로 여러 개 · 10개까지)</span></span>
          <input value={skills} onChange={(event) => setSkills(event.target.value)}
                 placeholder="예: Python, SQL, MES — 언어 · 소프트웨어 · 장비 (분석 기법 · 방법은 경험의 역량 태그로)" aria-label="보유 기술" />
        </label>
      </div>
      {suggestions.length > 0 && (
        <div className="tag-suggest contrib-skill-suggest">
          <span className="muted">팀에서 쓴 것</span>
          {suggestions.map((item) => (
            <button key={item} type="button" className="tag-pick" onClick={() => setSkills([...chosenSkills, item].join(", "))}>
              {item}
            </button>
          ))}
        </div>
      )}
      <div className="contrib-form-row">
        <label>
          담당 시작
          <input type="date" value={from} onChange={(event) => setFrom(event.target.value)} disabled={!ownerView}
                 aria-label="담당 시작" />
        </label>
        <label>
          담당 끝
          <input type="date" value={to} onChange={(event) => setTo(event.target.value)} disabled={!ownerView}
                 aria-label="담당 끝" />
        </label>
        {!ownerView && <p className="hint contrib-period-hint">담당 기간은 팀장이 고칩니다.</p>}
        {filledFromProject && <p className="hint contrib-period-hint">빈 칸은 과제 기간으로 채워 두었습니다 — 저장하면 그대로 남습니다.</p>}
      </div>
      {/* 중간 성과 (TODO 243 B2) — 진행 중에 분기 · 반기마다 한 줄. 끝날 때 회고의 재료 */}
      <div className="milestone-fields">
        <span className="milestone-head">
          중간 성과 <span className="muted">(날짜 + 한 줄 · 진행 중에 분기 · 반기마다 적어 두면 끝날 때 회고가 쉽습니다)</span>
        </span>
        {milestones.map((item, index) => (
          <div key={index} className="milestone-row">
            <input type="date" value={item.date} onChange={(event) => setMilestone(index, "date", event.target.value)} aria-label={`중간 성과 ${index + 1} 날짜`} />
            <input value={item.text} maxLength={200} onChange={(event) => setMilestone(index, "text", event.target.value)}
                   placeholder="예: 상반기 시범 운영 — 재작업 월 38건 → 23건" aria-label={`중간 성과 ${index + 1}`} />
            <button type="button" className="ghost small" onClick={() => setMilestones((prev) => prev.filter((_, i) => i !== index))} aria-label={`중간 성과 ${index + 1} 빼기`}>
              빼기
            </button>
          </div>
        ))}
        <button type="button" className="ghost small milestone-add" onClick={() => setMilestones((prev) => [...prev, { date: "", text: "" }])}>
          + 중간 성과
        </button>
      </div>
      {/* 성과 후보 일지 (TODO 243 B3) — ★성과 태그가 붙은 일지. 회고 쓸 때 다시 찾지 않게 */}
      {stars.length > 0 && (
        <div className="star-entries">
          <span className="milestone-head">★ 성과 후보 일지 <span className="muted">— 회고를 쓸 때 보세요</span></span>
          <ul>
            {stars.map((entry) => (
              <li key={entry.id}>
                <a href={projectLink(project.id, { entry: entry.id })}>{entry.date} {entry.title}</a>
                {entry.first_line && <span className="muted"> — {entry.first_line}</span>}
                {entry.author && <span className="muted"> · {entry.author}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
      {/* 회고 두 칸은 위아래로 · 글에 맞춰 자라는 칸 · 글자 수 · 붙여넣기 정리 (TODO 240) */}
      <div className="contrib-retro-fields">
        {RETRO.map((item) => (
          <RetroField
            key={item.key}
            label={item.label}
            value={retro[item.key]}
            placeholder={item.placeholder}
            onChange={(next) => setRetro((prev) => ({ ...prev, [item.key]: next }))}
          />
        ))}
      </div>
      {praiseEditable && (
        <label className="praise-field">
          <span>
            팀장의 인정 한 줄 <span className="muted">(팀장만 적고, {row.name} 님과 팀장에게만 보입니다 · 200자)</span>
          </span>
          <input value={praise} maxLength={200} onChange={(event) => setPraise(event.target.value)}
                 placeholder="예: 현장 반장님들을 설득해 가이드가 자리 잡게 한 것이 결정적이었음" aria-label="팀장의 인정 한 줄" />
        </label>
      )}
      {error && <p className="error">{error}</p>}
      <div className="form-actions">
        <button type="submit" disabled={busy}>
          {busy ? "저장 중…" : "저장"}
        </button>
        <button type="button" className="ghost" onClick={onCancel} disabled={busy}>
          {justDone ? "나중에" : "취소"}
        </button>
      </div>
    </form>
  );
}
