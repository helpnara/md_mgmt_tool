import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { getMe } from "../me";
import { personLink } from "../nav";
import { isLeader, leftLabel } from "../people";
import type { Contribution, Meta, Project } from "../types";
import Explain from "./Explain";

/**
 * 담당과 역할 (TODO 237) — 사람마다 역할 · 맡은 부분 · 담당 기간 · 회고 세 줄.
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
  { key: "problem", label: "무엇이 문제였나", placeholder: "예: 월말 집계를 손으로 해 주 4시간이 들었다" },
  { key: "did", label: "내가 한 일", placeholder: "예: 집계 스크립트를 만들고 현장 담당자 교육" },
  { key: "result", label: "결과", placeholder: "예: 주 4시간 → 30분, 집계 오류 0건" },
] as const;

type RetroKey = (typeof RETRO)[number]["key"];

/** 지금의 나 — 팀원 PC 면 그 사람, 서버 PC 면 명부의 팀장 */
export function myName(meta: Meta): string {
  const me = getMe();
  if (me.role === "member") return me.name;
  if (me.role === "owner") return meta.leader || "";
  return "";
}

function hasRetro(row: Contribution): boolean {
  return Boolean(row.problem || row.did || row.result);
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
}: {
  project: Project;
  meta: Meta;
  onSaved: (saved: Project) => void;
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
    me.role === "owner" || (me.role === "member" && name === me.name && me.projects.includes(project.id));

  return (
    <div className="card contributions-card" ref={card} data-contributions>
      <div className="card-head">
        <h2>담당과 역할</h2>
      </div>
      <Explain
        id="contributions"
        lead={<>사람마다 <b>역할 · 맡은 부분 · 담당 기간 · 회고</b>를 남깁니다 — 나중에 본인의 업무 이력 · 성과를 정리할 때의 재료입니다.</>}
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
                    {hasRetro(row) || row.role || row.part ? "고치기" : "적기"}
                  </button>
                )}
              </div>
              {hasRetro(row) && editing !== row.name && (
                <dl className="contrib-retro">
                  {RETRO.map((item) =>
                    row[item.key] ? (
                      <div key={item.key}>
                        <dt>{item.label}</dt>
                        <dd>{row[item.key]}</dd>
                      </div>
                    ) : null,
                  )}
                </dl>
              )}
              {editing === row.name && (
                <ContributionForm
                  project={project}
                  row={row}
                  ownerView={me.role === "owner"}
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

function ContributionForm({
  project,
  row,
  ownerView,
  justDone,
  onCancel,
  onSaved,
}: {
  project: Project;
  row: Contribution;
  ownerView: boolean;
  justDone: boolean;
  onCancel: () => void;
  onSaved: (saved: Project) => void;
}) {
  const [role, setRole] = useState(row.role);
  const [part, setPart] = useState(row.part);
  const [from, setFrom] = useState(row.from ?? "");
  const [to, setTo] = useState(row.to ?? "");
  const [retro, setRetro] = useState<Record<RetroKey, string>>({ problem: row.problem, did: row.did, result: row.result });
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
          과제가 끝났습니다 — 기억이 생생할 때 <b>회고 세 줄</b>을 남겨 두세요. 비워 두고 닫아도 됩니다(홈 [할 일]에 1년 동안 남습니다).
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
      </div>
      <div className="contrib-retro-fields">
        {RETRO.map((item) => (
          <label key={item.key}>
            {item.label}
            <textarea
              rows={2}
              maxLength={1000}
              value={retro[item.key]}
              placeholder={item.placeholder}
              aria-label={item.label}
              onChange={(event) => setRetro((prev) => ({ ...prev, [item.key]: event.target.value }))}
            />
          </label>
        ))}
      </div>
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
