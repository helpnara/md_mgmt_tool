import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import { renderMarkdown } from "../markdown";
import { backTarget, projectLink, setPageTitle } from "../nav";
import LoadError from "./LoadError";
import { notifyError } from "../notify";
import {
  type EditLedger,
  discardQuestion,
  dropDraft,
  hasDraft,
  loadDraft,
  useDrafts,
  useDraftKeeper,
  useEditLedger,
  useUnsaved,
} from "../unsaved";
import PasteOfferBar from "./PasteOffer";
import PrecheckDialog, { BandChip } from "./PrecheckDialog";
import { type PasteOffer, handleEditorPaste } from "../table";
import type { IntakeAttachment, IntakeDetail as Detail, IntakeLog, Meta, Project, PromotionPlan } from "../types";
import { type Attachment, uploadAttachment } from "../upload";
import { dateOrderProblem, effectNumber, todayIso, useEscape } from "../util";
import {
  DATE_MAX,
  DATE_MIN,
  LIMITS,
  checkPeople,
  confirmEffects,
  confirmOutsiders,
  confirmPeople,
  dateProblem as dayProblem,
  effectProblem,
  isDeparted,
  lengthHint,
  similarTeam,
  splitNames,
  titleProblem,
  warningList,
  FORM_SHOWN_WARNING,
} from "../inputRules";
import { confirmSameTitle } from "./ProjectForm";
import AttachmentList from "./AttachmentList";
import IntakeForm from "./IntakeForm";
import TagSuggestions from "./TagSuggestions";
import PreviewToggle, { usePreview } from "./PreviewToggle";
import StatusBadge from "./StatusBadge";
import VersionPanel from "./VersionPanel";
import XlsxPreview from "./XlsxPreview";

/**
 * 접수 상세 (TODO 136) — 요청 내용 · 첨부 · 인터뷰 기록 · 판정 · 승격.
 *
 * **풀에 있을 때만 고친다.** 판정이 난 접수는 그때의 기록으로 굳는다 — 반려·이관·병합은
 * [재검토]로 풀에 되돌릴 수 있고, 착수(승격)는 되돌리지 않는다. 과제가 이미 있다.
 *
 * 인터뷰 기록은 **접수 건에 남기고 과제에서는 링크만** 건다 — 문제 정의가 바뀌거나 구체화되는
 * 과정 자체가 기록이다 (사용자 결정 3).
 */
interface Props {
  intakeId: string;
  meta: Meta;
  back: string | null;
  onMetaChange: () => void;
  /** 홈의 "작성 중이던 글" 에서 왔다 — "body" 면 요청 내용 편집기를 연다 (TODO 170) */
  openDraft?: string | null;
}

const STATUS_LINES: Record<string, string> = {
  on_hold: "보류",
  rejected: "반려",
  transferred: "이관",
  merged: "병합",
};

export default function IntakeDetail({ intakeId, meta, back, onMetaChange, openDraft }: Props) {
  const [intake, setIntake] = useState<Detail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editingMeta, setEditingMeta] = useState(false);
  const [editingBody, setEditingBody] = useState(false);
  // 검토 기록 편집기가 열렸는가 — 2단을 잠시 1단으로 돌릴 때 쓴다 (TODO 141)
  const [editingLog, setEditingLog] = useState(false);
  const [showVersions, setShowVersions] = useState(false);
  // 사전점검 체크리스트 대화상자 (TODO 155)
  const [prechecking, setPrechecking] = useState(false);
  const [deciding, setDeciding] = useState<string | null>(null);
  const [promoting, setPromoting] = useState(false);
  // 남은 임시 보관 — 요청 내용 [수정] 옆 "작성 중" 표시가 본다 (TODO 170)
  useDrafts();
  // 홈의 "작성 중이던 글" 에서 왔으면 요청 내용 편집기를 연다 — 한 번만
  const draftOpened = useRef(false);

  const load = useCallback(() => {
    api
      .getIntake(intakeId)
      .then((row) => {
        setIntake(row);
        setError(null);
      })
      .catch((err: Error) => setError(err.message));
  }, [intakeId]);
  useEffect(load, [load]);
  useEffect(() => {
    if (!intake || draftOpened.current || openDraft !== "body" || !intake.in_pool) return;
    draftOpened.current = true;
    setEditingBody(true);
  }, [intake, openDraft]);
  // 브라우저 탭 제목 (TODO 169)
  useEffect(() => {
    if (intake) setPageTitle(`${intake.id} ${intake.title}`);
  }, [intake]);

  const target = back ? backTarget(back) : { href: "#/intakes", label: "접수" };

  if (!intake) {
    return (
      <section className="intake-detail">
        <a className="back" href={target.href}>
          ← {target.label}
        </a>
        {/* 불러오기 실패는 모든 화면이 같은 판 — 사유와 [다시 시도] (TODO 165) */}
        {error ? <LoadError message={error} onRetry={load} /> : <p className="muted">불러오는 중…</p>}
      </section>
    );
  }

  const open = intake.in_pool;
  const base = `/intake-files/${encodeURIComponent(intake.dir_name)}`;
  const classes = meta.classifications
    .map((info) => ({ info, value: intake[info.key] }))
    .filter((row) => row.value);

  async function run(action: () => Promise<unknown>) {
    try {
      await action();
      load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <section className="intake-detail">
      <a className="back" href={target.href}>
        ← {target.label}
      </a>

      <div className="card detail-header">
        <div className="detail-head">
          <div>
            <span className="intake-id-head">{intake.id}</span>
            <h1>
              {intake.picked && <span className="star on" title="착수 후보">★ </span>}
              {intake.title}
            </h1>
            <div className="meta-line">
              <span className={`intake-status intake-${intake.status}`}>{intake.status_label}</span>
              {/* 직접 만든 과제를 풀로 되돌린 접수 (TODO 171) — 과제는 삭제 보관함에 있다 */}
              {intake.demoted_from && (
                <span className="tag demoted-tag" title="과제는 설정 → 삭제 보관함에 있습니다">
                  과제 {intake.demoted_from} 에서 되돌림
                </span>
              )}
              {intake.priority && (
                <span className={`priority priority-${intake.priority}`} title={intake.priority_note ?? undefined}>
                  중요도 {intake.priority}
                </span>
              )}
              {classes.map(({ info, value }) => (
                <span key={info.key} className="chip class-chip">
                  <span className="class-chip-label">{info.label}</span> {value}
                </span>
              ))}
              {intake.tags.map((tag) => (
                <span key={tag} className="tag">
                  {tag}
                </span>
              ))}
            </div>
            <div className="meta-line muted">
              <span>
                과제리더 {intake.leader ?? "—"}
                {intake.leader_team && ` · ${intake.leader_team}`}
              </span>
              <span>접수 {intake.received_on ?? "—"}</span>
              {(intake.start_date || intake.due_date) && (
                <span>
                  추진 {intake.start_date ?? "?"} ~ {intake.due_date ?? "?"}
                </span>
              )}
              {intake.priority_note && <span>중요도 근거: {intake.priority_note}</span>}
            </div>
            {intake.stale && (
              <p className="warn-text stale-note">
                접수 후 {intake.age_days}일째 판정이 없습니다 ({meta.intake_stale_days}일 기준). 요청자에게 진행 상황을
                알려 주거나, 보류·반려로 정리해 주세요.
              </p>
            )}
            {!open && (
              <div className="decision-line">
                <b>{intake.status_label}</b>
                {intake.decided_on && <span className="muted"> · {intake.decided_on}</span>}
                {intake.linked_project && (
                  <>
                    {" "}
                    →{" "}
                    {intake.linked_project.missing ? (
                      <span className="muted">과제 {intake.linked_project.id} (지금은 찾을 수 없음)</span>
                    ) : (
                      <a href={projectLink(intake.linked_project.id)}>
                        <span className="project-id">{intake.linked_project.id}</span> {intake.linked_project.title}
                      </a>
                    )}
                  </>
                )}
                {intake.decision_note && <p className="decision-note">{intake.decision_note}</p>}
              </div>
            )}
            {open && intake.status === "on_hold" && intake.decision_note && (
              <p className="decision-note">보류 조건: {intake.decision_note}</p>
            )}
          </div>
          <div className="detail-actions">
            {open ? (
              <>
                <button className="primary commit" onClick={() => setPromoting(true)}>
                  착수 · 과제로 승격
                </button>
                <button data-write className="ghost" onClick={() => setEditingMeta((v) => !v)}>
                  {editingMeta ? "닫기" : "접수 정보 수정"}
                </button>
                <button data-write
                  className="ghost"
                  onClick={() => run(() => api.updateIntake(intake.id, { picked: !intake.picked }))}
                >
                  {intake.picked ? "☆ 후보에서 빼기" : "★ 착수 후보로"}
                </button>
                {/* 삭제는 과제 상세와 같은 자리·같은 이름 — 머리의 맨 끝 (TODO 147) */}
                <button
                  className="ghost danger"
                  onClick={() => {
                    if (
                      window.confirm(
                        `${intake.id} 을(를) 삭제 보관함으로 옮길까요?\n\n잘못 만든 접수를 지우는 것입니다. 할 수 없게 된 요청은 지우지 말고 [반려]로 남겨 주세요 — 반년 뒤 같은 요청이 오면 그 기록이 답이 됩니다.`,
                      )
                    )
                      void api
                        .archiveIntake(intake.id)
                        .then(() => (window.location.hash = "#/intakes"))
                        .catch((err: Error) => setError(err.message));
                  }}
                >
                  삭제
                </button>
              </>
            ) : (
              intake.status !== "started" && (
                <button data-write // 쓰기 — 읽기 전용 공유에서는 숨긴다 (TODO 208)
                  className="ghost"
                  onClick={() => {
                    if (window.confirm("풀로 되돌려 다시 검토할까요? 지난 판정은 검토 기록에 남습니다."))
                      void run(() => api.setIntakeStatus(intake.id, "reviewing"));
                  }}
                >
                  재검토 (풀로 되돌리기)
                </button>
              )
            )}
          </div>
        </div>

        {/* 과제 상세와 같은 요약 줄 — 작은 이름 위에 값 (TODO 147) */}
        <dl className="summary-bar">
          {/* 사전점검 (TODO 155) — 요약 줄의 첫 칸. 평소에는 점수 한 칸, 매길 때만 대화상자 */}
          <div className="precheck-cell">
            <dt>사전점검 체크리스트</dt>
            <dd>
              {intake.precheck.score !== null ? (
                <>
                  {intake.precheck.score}점 <BandChip band={intake.precheck.band} />
                </>
              ) : intake.precheck.rated > 0 ? (
                <span className="muted">
                  평가 중 {intake.precheck.rated}/{intake.precheck.total_items}
                </span>
              ) : (
                <span className="muted">미평가</span>
              )}
              {/* 읽기 전용 공유에서도 보인다 — 점수의 근거를 보는 창이고, 창 자체가 읽기 전용으로 열린다 (TODO 208) */}
              <button className="ghost small" onClick={() => setPrechecking(true)}>
                체크리스트
              </button>
            </dd>
          </div>
          <div>
            <dt>경과</dt>
            <dd className={open && intake.stale ? "danger" : undefined}>
              {open && intake.age_days !== null ? `D+${intake.age_days}` : "—"}
            </dd>
          </div>
          <div>
            <dt>검토 기록</dt>
            <dd>{intake.log_count}건</dd>
          </div>
          <div>
            <dt>첨부</dt>
            <dd>{intake.attachments.length}건</dd>
          </div>
          <div title="요청자 추정 — 승격할 때 과제로 옮기지 않고 참고로만 보여 줍니다">
            <dt>요청 기대효과 억원/년</dt>
            <dd>
              {intake.effect_request !== null ? effectNumber(intake.effect_request) : "—"}
              {intake.effect_request !== null && <span className="muted"> · 요청자 추정</span>}
            </dd>
          </div>
          <div>
            <dt>상태</dt>
            <dd>{intake.status_label}</dd>
          </div>
        </dl>

        {open && (
          <div className="decision-bar">
            <span className="muted">판정</span>
            {intake.status === "received" && (
              <button data-write className="ghost small" onClick={() => run(() => api.setIntakeStatus(intake.id, "reviewing"))}>
                검토 시작
              </button>
            )}
            {intake.status === "on_hold" && (
              <button className="ghost small" onClick={() => run(() => api.setIntakeStatus(intake.id, "reviewing"))}>
                보류 풀기 (검토중으로)
              </button>
            )}
            {(["on_hold", "rejected", "transferred", "merged"] as const)
              .filter((key) => key !== intake.status)
              .map((key) => (
                <button
                  key={key}
                  className={`ghost small ${deciding === key ? "on" : ""}`}
                  onClick={() => setDeciding(deciding === key ? null : key)}
                >
                  {STATUS_LINES[key]}
                </button>
              ))}
            <span className="hint">판정은 기록입니다 — 회의에서 정한 것을 적습니다.</span>
          </div>
        )}
        {open && deciding && (
          <DecisionPanel
            kind={deciding}
            meta={meta}
            intakeTitle={intake.title}
            onCancel={() => setDeciding(null)}
            onConfirm={async (note, mergedInto) => {
              await api.setIntakeStatus(intake.id, deciding, note, mergedInto);
              setDeciding(null);
              load();
            }}
          />
        )}
        {editingMeta && open && (
          <IntakeForm
            meta={meta}
            onMetaChange={onMetaChange}
            initial={intake}
            submitLabel="저장"
            onCancel={() => setEditingMeta(false)}
            onSubmit={async (payload) => {
              await api.updateIntake(intake.id, payload);
              setEditingMeta(false);
              load();
            }}
          />
        )}
      </div>

      {error && <p className="error">{error}</p>}

      {prechecking && (
        <PrecheckDialog
          intake={intake}
          meta={meta}
          onClose={() => setPrechecking(false)}
          onSaved={() => {
            setPrechecking(false);
            load();
          }}
        />
      )}

      {promoting && (
        <PromoteDialog
          intake={intake}
          meta={meta}
          onMetaChange={onMetaChange}
          onClose={() => setPromoting(false)}
          onDone={(projectId) => {
            setPromoting(false);
            onMetaChange();
            window.location.hash = projectLink(projectId);
          }}
        />
      )}

      {/* ── 2단 (TODO 141) — 과제 상세와 같은 짜임. 왼쪽은 *무엇을 요청했나*(요청 내용 · 첨부),
          오른쪽은 *어떻게 구체화됐나*(검토 기록). 세로로 늘어놓으면 기록이 쌓일수록 첨부가 밀려
          내려가 스크롤이 길어졌다. 편집기를 연 동안에는 1단으로 넓게 쓰고, 편집 중인 쪽이 위로 온다. */}
      <div
        className={`detail-columns intake-columns${
          editingBody || editingLog ? ` editing editing-${editingBody ? "left" : "right"}` : ""
        }`}
      >
      <div className="detail-left">
      {/* ── 요청 내용 ─────────────────────────────────────────────── */}
      <div className="card intake-body">
        <div className="card-head">
          <h2>
            요청 내용
            {!editingBody && hasDraft(`intake:${intake.id}`) && (
              <span className="draft-waiting" title="저장하지 않은 요청 내용이 남아 있습니다 — [수정] 을 누르면 되살아납니다">
                작성 중
              </span>
            )}
          </h2>
          <div className="card-head-actions">
            {open && (
              <button data-write
                className={showVersions ? "ghost on" : "ghost"}
                onClick={() => setShowVersions((v) => !v)}
                title="문제 정의가 바뀌기 전의 요청 내용을 봅니다 — 고칠 때마다 한 벌씩 남습니다."
              >
                이전 버전
              </button>
            )}
            {open && !editingBody && (
              <button data-write className="ghost" onClick={() => setEditingBody(true)}>
                수정
              </button>
            )}
          </div>
        </div>
        {showVersions && open && (
          <VersionPanel
            path={`intakes/${intake.dir_name}/request.md`}
            onRestored={() => {
              setShowVersions(false);
              setEditingBody(false);
              load();
            }}
          />
        )}
        {editingBody ? (
          <BodyEditor
            intake={intake}
            onCancel={() => setEditingBody(false)}
            onSaved={() => {
              setEditingBody(false);
              load();
            }}
            onUploaded={load}
          />
        ) : (
          <div className="markdown" dangerouslySetInnerHTML={{ __html: renderMarkdown(intake.body, base) }} />
        )}
        <p className="hint">
          섹션 제목의 <b>괄호·줄표 앞 이름</b>이 과제 개요와 같으면(배경·목표·추진내용…) 승격할 때 그 자리로 그대로
          넘어갑니다.
        </p>
      </div>

      {/* 첨부 · 기록 삭제의 실패는 그 자리에서 보이게 알림으로 — 머리 카드 아래 한 줄은 동작 자리에서 안 보였다 (TODO 209 ③) */}
      <Attachments intake={intake} onChanged={load} onError={notifyError} />
      </div>
      <div className="detail-right">
        <Logs intake={intake} base={base} onChanged={load} onError={notifyError} onEditingChange={setEditingLog} />
      </div>
      </div>

    </section>
  );
}

// ── 판정 사유 ──────────────────────────────────────────────────────────────

function DecisionPanel({
  kind,
  meta,
  intakeTitle,
  onCancel,
  onConfirm,
}: {
  kind: string;
  meta: Meta;
  intakeTitle: string;
  onCancel: () => void;
  onConfirm: (note: string, mergedInto?: string) => Promise<void>;
}) {
  const [note, setNote] = useState("");
  const [target, setTarget] = useState("");
  const [query, setQuery] = useState("");
  // null = 아직 받는 중. 못 받았으면 빈 목록이 아니라 오류를 보인다 — 조용한 빈 칸은
  // "원래 고를 것이 없다" 로 읽혀 원인을 알 길이 없다 (TODO 140).
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (kind !== "merged") return;
    api
      .listProjects({ sort: "updated" })
      .then((rows) => setProjects(rows.filter((row) => !["done", "dropped"].includes(row.status))))
      .catch((err: Error) => {
        setProjects([]);
        setError(`과제 목록을 불러오지 못했습니다 — ${err.message}`);
      });
  }, [kind]);

  const prompts: Record<string, string> = {
    on_hold: "다시 볼 조건 — 예: 설비 교체(2027 상반기) 이후 재검토",
    rejected: "반려 사유 — 반년 뒤 같은 요청이 오면 이 한 줄이 답이 됩니다",
    transferred: "어느 팀 소관인지, 누구에게 넘겼는지",
    merged: "왜 같은 일로 보았는지 (선택)",
  };
  const required = kind !== "merged";
  // [정리] 단추가 꺼진 까닭 (TODO 214 U2)
  const why =
    kind === "merged" && !target
      ? "흡수할 과제를 골라 주세요."
      : required && !note.trim()
        ? `${STATUS_LINES[kind]} 사유를 적어 주세요.`
        : null;

  // 흡수할 과제 고르기 (TODO 151) — **과제 번호순**, 찾기 칸의 낱말은 띄어 쓰면 **모두 든 것**만 남긴다.
  // 번호로도 찾는다(`007`). 찾기 전에는 접수 제목과 낱말이 겹치는 과제를 위에 따로 세운다 — 같은
  // 요청이면 대개 제목이 닮았다.
  const sorted = [...(projects ?? [])].sort((a, b) => a.id.localeCompare(b.id, "ko", { numeric: true }));
  const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const matches = sorted.filter((project) => {
    const hay = `${project.id} ${project.title}`.toLowerCase();
    return words.every((word) => hay.includes(word));
  });
  const titleWords = intakeTitle.split(/[\s·,()/\-]+/).filter((word) => word.length >= 2);
  const similar = words.length
    ? []
    : sorted.filter((project) => titleWords.some((word) => project.title.includes(word)));
  const chosen = sorted.find((project) => project.id === target);
  const row = (project: Project) => (
    <li key={project.id}>
      <button type="button" className="merge-option" onClick={() => setTarget(project.id)}>
        <span className="merge-option-id">{project.id}</span>
        <span className="merge-option-title">{project.title}</span>
        <StatusBadge status={project.status} meta={meta} />
      </button>
    </li>
  );

  return (
    <div className="decision-panel">
      {kind === "merged" && (
        <div className="merge-picker">
          <span className="merge-picker-label">흡수할 과제</span>
          {chosen ? (
            <p className="merge-chosen">
              <b>{chosen.id}</b> {chosen.title} <StatusBadge status={chosen.status} meta={meta} />
              <button type="button" className="ghost small" onClick={() => setTarget("")}>
                다시 고르기
              </button>
            </p>
          ) : (
            <>
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="과제명·번호의 낱말 — 띄어 쓰면 모두 든 과제만 (예: 온도 예측)"
                aria-label="흡수할 과제 찾기"
                disabled={projects === null}
                autoFocus
              />
              {projects === null && <p className="hint">불러오는 중…</p>}
              {projects !== null && projects.length === 0 && !error && (
                <p className="hint">끝나지 않은 과제가 없습니다 — 병합은 진행 중인 과제에 잇는 것입니다.</p>
              )}
              {similar.length > 0 && (
                <>
                  <p className="hint merge-group">접수 제목과 낱말이 겹치는 과제</p>
                  <ul className="merge-list">{similar.map(row)}</ul>
                  <p className="hint merge-group">전체 (과제 번호순)</p>
                </>
              )}
              {projects !== null && projects.length > 0 && (
                <ul className="merge-list">
                  {matches.length === 0 ? <li className="hint">맞는 과제가 없습니다.</li> : matches.map(row)}
                </ul>
              )}
            </>
          )}
        </div>
      )}
      <label>
        {/* 필수 표시 * (TODO 214 U1) */}
        {STATUS_LINES[kind]} {required ? "사유 *" : "메모"}
        <textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder={prompts[kind]} rows={2} />
      </label>
      {error && <p className="error form-error">{error}</p>}
      <div className="form-actions left">
        <button
          disabled={busy || Boolean(why)}
          title={why ?? undefined}
          onClick={async () => {
            setBusy(true);
            setError(null);
            try {
              await onConfirm(note.trim(), target || undefined);
            } catch (err) {
              setError((err as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          {STATUS_LINES[kind]}(으)로 정리
        </button>
        <button className="ghost" onClick={onCancel} disabled={busy}>
          취소
        </button>
        {/* 단추가 꺼진 까닭은 단추 옆에 (TODO 214 U1 · U2) */}
        {why && <span className="hint warn-text decision-why">{why}</span>}
      </div>
    </div>
  );
}

// ── 본문 편집기 — 붙여넣기(이미지·엑셀 표)와 끌어다 놓기를 받는다 ───────────

function useMarkdownField(initial: string) {
  const [value, setValue] = useState(initial);
  const ref = useRef<HTMLTextAreaElement>(null);
  const insert = (snippet: string) => {
    const area = ref.current;
    const start = area ? area.selectionStart : value.length;
    const end = area ? area.selectionEnd : value.length;
    let inserted = snippet;
    setValue((prev) => {
      const before = prev.slice(0, start);
      const after = prev.slice(end);
      const lead = before.length > 0 && !before.endsWith("\n") ? "\n\n" : "";
      const trail = after.startsWith("\n") || after.length === 0 ? "\n" : "\n\n";
      inserted = `${lead}${snippet}${trail}`;
      return `${before}${inserted}${after}`;
    });
    if (area)
      window.requestAnimationFrame(() => {
        area.focus();
        const caret = start + inserted.length;
        area.setSelectionRange(caret, caret);
      });
  };
  return { value, setValue, ref, insert };
}

async function uploadFiles(intakeId: string, files: File[]): Promise<IntakeAttachment[]> {
  const out: IntakeAttachment[] = [];
  for (const file of files) {
    const handle = uploadAttachment(`/api/intakes/${encodeURIComponent(intakeId)}/attachments`, file, () => undefined);
    out.push((await handle.promise) as unknown as IntakeAttachment);
  }
  return out;
}

/**
 * 이 글이 가리키는 첨부인가. 첨부는 `assets/<날짜>/NNN-이름` 이고 번호는 날마다 001 부터라,
 * 파일 이름만으로는 다른 날의 같은 이름과 섞인다 — **날짜 폴더부터** 견준다(공백은 `<…>` 로 감싸거나 %20).
 */
function referencedIn(text: string, item: IntakeAttachment): boolean {
  const tail = item.rel_path.replace(/^assets\//, "");
  return !!tail && (text.includes(tail) || text.includes(encodeURI(tail)));
}

/** 접수 첨부를 과제 첨부 목록 모양으로 — 진행일지와 **같은 목록 부품**을 쓰려고 (TODO 138). */
function asAttachments(items: IntakeAttachment[], kind: "markdown" | "markdown_log"): Attachment[] {
  return items.map((item, index) => ({
    id: index,
    entry_id: null,
    report_id: null,
    preview_url: item.preview_url ?? null,
    rel_path: item.rel_path,
    orig_name: item.orig_name,
    mime: item.mime,
    size_bytes: item.size_bytes,
    is_image: item.is_image,
    url: item.url,
    thumb_url: null,
    markdown: item[kind],
    orphan: false,
    deduplicated: false,
  }));
}

/**
 * 첨부 판 — 📎 · 끌어다 놓기 안내 · 목록 · [본문에 삽입] · [내용 보기] · 삭제 (TODO 138).
 *
 * 136 에서 접수 편집기를 새로 짜며 진행일지의 첨부 판을 옮겨 오지 않아, 편집 중에는 📎 가 없고
 * 첨부 카드에는 작은 흐린 단추뿐이었다. **파일을 붙이는 자리는 모두 이 판 하나를 쓴다.**
 */
function AttachPanel({
  intake,
  kind,
  heading,
  onUpload,
  onInsert,
  onChanged,
  onError,
  only,
  emptyText,
  ledger,
}: {
  intake: Detail;
  kind: "markdown" | "markdown_log";
  heading: "h2" | "h3";
  onUpload: (files: File[]) => Promise<void>;
  onInsert?: (markdown: string) => void;
  onChanged: () => void;
  onError: (message: string) => void;
  /** 보일 첨부만 고른다 — 검토 기록은 **그 기록의 첨부만** (TODO 150). 없으면 전부 */
  only?: (item: IntakeAttachment) => boolean;
  emptyText?: string;
  /**
   * 편집기 안의 첨부 판이면 그 편집의 장부 (TODO 213 ③) — [삭제] 는 "지울 예정" 으로만, 실제 삭제는 [저장] 때.
   * 없으면(첨부 카드) 지금처럼 바로 지운다.
   */
  ledger?: EditLedger<string>;
}) {
  const items = only ? intake.attachments.filter(only) : intake.attachments;
  const [busy, setBusy] = useState(0);
  const [previewing, setPreviewing] = useState<Attachment | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const Title = heading;
  const editable = intake.in_pool;

  async function upload(files: File[]) {
    if (files.length === 0) return;
    setBusy((n) => n + files.length);
    try {
      await onUpload(files);
    } finally {
      setBusy((n) => Math.max(0, n - files.length));
    }
  }

  return (
    <div className={heading === "h3" ? "attachment-panel" : undefined}>
      <div className="card-head">
        <Title>첨부 ({items.length})</Title>
        {editable && (
          <div className="attach-actions">
            <span className="hint">이미지는 Ctrl+V, 파일은 끌어다 놓아도 됩니다.</span>
            <button className="attach-button" disabled={busy > 0} onClick={() => inputRef.current?.click()}>
              {busy > 0 ? `올리는 중… (${busy})` : "📎 파일 첨부"}
            </button>
            <input
              ref={inputRef}
              type="file"
              multiple
              hidden
              onChange={(event) => {
                const files = Array.from(event.target.files ?? []);
                event.target.value = ""; // 같은 파일을 다시 골라도 반응하도록 비운다
                void upload(files);
              }}
            />
          </div>
        )}
      </div>
      {items.length === 0 ? (
        <p className="hint">
          {emptyText ?? "과제정의서(PPT)·부연 설명·공정 설명·활용 화면을 붙여 두세요. 승격하면 과제로 복사됩니다."}
        </p>
      ) : (
        <AttachmentList
          attachments={asAttachments(items, kind)}
          onInsert={onInsert ? (item) => onInsert(item.markdown) : undefined}
          onPreview={setPreviewing}
          pending={ledger ? (item) => ledger.isDoomed(item.rel_path) : undefined}
          onRestore={ledger ? (item) => ledger.toggleDoomed(item.rel_path) : undefined}
          onDelete={
            editable && ledger
              ? (item) => ledger.toggleDoomed(item.rel_path)
              : editable
              ? async (item) => {
                  const used = intake.body.includes(item.rel_path.split("/").pop() ?? "");
                  const warn = used ? "\n\n이 첨부는 요청 본문에서 쓰이는 중입니다. 지우면 그 자리가 깨집니다." : "";
                  if (!window.confirm(`${item.orig_name} 을(를) 삭제 보관함으로 옮길까요?${warn}`)) return;
                  try {
                    await api.deleteIntakeAttachment(intake.id, item.rel_path);
                    onChanged();
                  } catch (err) {
                    onError((err as Error).message);
                  }
                }
              : undefined
          }
        />
      )}
      {ledger && ledger.doomed.length > 0 && (
        <p className="hint pending-note">지울 예정인 첨부 {ledger.doomed.length}건은 [저장] 할 때 삭제 보관함으로 옮깁니다.</p>
      )}
      {previewing && <XlsxPreview attachment={previewing} onClose={() => setPreviewing(null)} />}
    </div>
  );
}

/**
 * 검토 기록의 임시 보관 열쇠 (TODO 211 ③). 서버가 받는 열쇠 모양은 `intake:<글자 · 숫자 · _ · ->` 라(drafts.py),
 * 접수 번호 뒤에 `--log-<기록 이름>` 을 붙인다. 기록 이름의 `.md` · 점 · 공백은 `_` 로 바꾸고 80자 안으로 자른다.
 */
function logDraftKey(intakeId: string, name?: string): string {
  const prefix = `${intakeId}--log-`;
  const stem = (name ?? "new").replace(/\.md$/, "").replace(/[^0-9A-Za-z가-힣_-]/g, "_");
  return `intake:${prefix}${stem.slice(0, Math.max(1, 80 - prefix.length))}`;
}

function MarkdownArea({
  field,
  intake,
  base,
  linkKind,
  onUploaded,
  onError,
  placeholder,
  ledger,
}: {
  field: ReturnType<typeof useMarkdownField>;
  intake: Detail;
  base: string;
  linkKind: "markdown" | "markdown_log";
  onUploaded: () => void;
  onError: (message: string) => void;
  placeholder: string;
  /** 이 편집의 장부 (TODO 213 ⑦) — 올린 첨부를 적어 두어 버리면 지운다. Ctrl+S 는 편집기 루트가 받는다(211 ⑥). */
  ledger: EditLedger<string>;
}) {
  const [preview, togglePreview] = usePreview();
  const [pasteOffer, setPasteOffer] = useState<PasteOffer | null>(null);
  const closeOffer = useCallback(() => setPasteOffer(null), []);
  // 이번 편집에서 올린 첨부(장부) — 본문에서 링크를 지웠어도 목록에는 남겨 다시 넣을 수 있게 (TODO 150)
  const uploadedNow = ledger.uploaded;

  // 올린 파일은 링크를 커서 자리에 넣는다 — 진행일지 편집기와 같다.
  async function handleFiles(files: File[]) {
    if (files.length === 0) return;
    try {
      const saved = await uploadFiles(intake.id, files);
      for (const item of saved) field.insert(item[linkKind]);
      for (const item of saved) ledger.addUploaded(item.rel_path);
      onUploaded();
    } catch (err) {
      onError((err as Error).message);
    }
  }

  return (
    <div
      onDragOver={(event) => event.preventDefault()}
      onDrop={(event) => {
        event.preventDefault();
        void handleFiles(Array.from(event.dataTransfer.files));
      }}
    >
      <PreviewToggle on={preview} onToggle={togglePreview} />
      <div className={preview ? "split" : "split solo"}>
        <textarea
          ref={field.ref}
          value={field.value}
          onChange={(event) => field.setValue(event.target.value)}
          onPaste={(event) =>
            handleEditorPaste(event, {
              onInsert: field.insert,
              onFiles: (files) => void handleFiles(files),
              onOffer: setPasteOffer,
            })
          }
          placeholder={placeholder}
          spellCheck={false}
        />
        {preview && (
          <div className="preview markdown" dangerouslySetInnerHTML={{ __html: renderMarkdown(field.value, base) }} />
        )}
      </div>
      <PasteOfferBar
        offer={pasteOffer}
        area={field.ref.current}
        setValue={field.setValue}
        onFiles={(files) => void handleFiles(files)}
        onClose={closeOffer}
      />
      <AttachPanel
        intake={intake}
        kind={linkKind}
        heading="h3"
        onUpload={handleFiles}
        onInsert={field.insert}
        onChanged={onUploaded}
        onError={onError}
        ledger={ledger}
        // 검토 기록은 그날 한 번의 인터뷰다 — 접수의 첨부 전부가 아니라 **이 기록의 첨부만** (TODO 150).
        // 요청 내용은 접수 전체를 다루므로 전부.
        only={
          linkKind === "markdown_log"
            ? (item) => uploadedNow.includes(item.rel_path) || referencedIn(field.value, item)
            : undefined
        }
        emptyText={
          linkKind === "markdown_log"
            ? "이 기록에 붙인 첨부가 없습니다. 📎 로 올리거나 끌어다 놓으면 여기에 섭니다. 접수의 첨부 전체는 왼쪽 첨부 카드에 있습니다."
            : undefined
        }
      />
    </div>
  );
}

function BodyEditor({
  intake,
  onCancel,
  onSaved,
  onUploaded,
}: {
  intake: Detail;
  onCancel: () => void;
  onSaved: () => void;
  onUploaded: () => void;
}) {
  // 요청 내용 — 떠날 때 묻고, 쓰던 글은 임시 보관한다 (TODO 162)
  const draftKey = `intake:${intake.id}`;
  const original = intake.body ?? "";
  const [restored, setRestored] = useState(false);
  const field = useMarkdownField(original);
  // 남은 글이 있으면 되살린다 — 데이터 폴더에서 가져오므로 편집기가 열린 뒤 곧 채워진다 (TODO 170)
  useEffect(() => {
    let alive = true;
    void loadDraft<string>(draftKey, (content) => content === original).then((kept) => {
      if (!alive || typeof kept !== "string") return;
      field.setValue(kept);
      setRestored(true);
    });
    return () => {
      alive = false;
    };
    // 편집기를 열 때 한 번
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const base = `/intake-files/${encodeURIComponent(intake.dir_name)}`;
  const dirty = field.value !== original;
  // 편집 한 번의 장부 (TODO 213 ⑦) — 올린 첨부 · 지우기로 한 첨부(접수 폴더 기준 경로)
  const ledger = useEditLedger<string>();
  useUnsaved(draftKey, dirty || !ledger.empty);
  useDraftKeeper(draftKey, field.value, field.value === original);

  async function save() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await api.updateIntake(intake.id, { body: field.value });
      // 지우기로 한 첨부는 저장할 때 지운다 (TODO 213 ③)
      await ledger.commit((path) => api.deleteIntakeAttachment(intake.id, path));
      dropDraft(draftKey);
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  /** [취소] — 진행일지 [닫기] 와 같은 규칙: 사실대로 묻고, 버리면 이번에 올린 첨부를 지운다 (TODO 213 ⑦) */
  async function discard() {
    if (
      (dirty || !ledger.empty) &&
      !window.confirm(
        discardQuestion({ what: "요청 내용을", uploaded: ledger.uploaded.length, doomed: ledger.doomedExisting.length }),
      )
    )
      return;
    const had = ledger.uploaded.length > 0;
    setBusy(true);
    await ledger.rollback((path) => api.deleteIntakeAttachment(intake.id, path));
    dropDraft(draftKey);
    onCancel();
    if (had) onUploaded(); // 지운 첨부가 목록에서 빠지게 다시 읽는다
  }

  return (
    <div
      className="body-editor"
      onKeyDown={(event) => {
        // Ctrl+S 는 편집기 어디서나 — 본문 칸에서만 먹던 것을 루트로 (TODO 211 ⑥)
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
          event.preventDefault();
          void save();
        }
      }}
    >
      <MarkdownArea
        field={field}
        intake={intake}
        base={base}
        linkKind="markdown"
        onUploaded={onUploaded}
        onError={setError}
        ledger={ledger}
        placeholder="과제정의서의 내용을 옮겨 적습니다. 이미지는 Ctrl+V 로, 엑셀 표는 그대로 붙여넣으면 표가 됩니다."
      />
      {restored && (
        <p className="hint restored">
          저장하지 않은 작성 중 내용을 복구했습니다.{" "}
          <button
            className="ghost small"
            onClick={() => {
              dropDraft(draftKey);
              field.setValue(original);
              setRestored(false);
            }}
          >
            복구한 내용 버리기
          </button>
        </p>
      )}
      {error && <p className="error">{error}</p>}
      <div className="form-actions">
        <button className="ghost" onClick={() => void discard()} disabled={busy}>
          취소
        </button>
        <button disabled={busy} onClick={() => void save()}>
          {busy ? "저장 중…" : "저장"}
        </button>
      </div>
    </div>
  );
}

// ── 첨부 ───────────────────────────────────────────────────────────────────

function Attachments({
  intake,
  onChanged,
  onError,
}: {
  intake: Detail;
  onChanged: () => void;
  onError: (message: string) => void;
}) {
  const upload = async (files: File[]) => {
    try {
      await uploadFiles(intake.id, files);
      onChanged();
    } catch (err) {
      onError((err as Error).message);
    }
  };
  return (
    <div
      className="card intake-files"
      // 카드에 끌어다 놓아도 받는다 — 과제 개요 카드와 같다 (TODO 138)
      onDragOver={(event) => intake.in_pool && event.preventDefault()}
      onDrop={(event) => {
        if (!intake.in_pool) return;
        event.preventDefault();
        void upload(Array.from(event.dataTransfer.files));
      }}
    >
      <AttachPanel intake={intake} kind="markdown" heading="h2" onUpload={upload} onChanged={onChanged} onError={onError} />
    </div>
  );
}

// ── 검토 기록 (인터뷰) ──────────────────────────────────────────────────────

function Logs({
  intake,
  base,
  onChanged,
  onError,
  onEditingChange,
}: {
  intake: Detail;
  base: string;
  onChanged: () => void;
  onError: (message: string) => void;
  onEditingChange: (editing: boolean) => void;
}) {
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  useEffect(() => onEditingChange(adding || editing !== null), [adding, editing, onEditingChange]);
  // 과제 상세의 수행 이력과 **같은 짜임**이다 (TODO 147) — 머리는 카드 밖, 기록은 한 장씩 카드,
  // [기록 추가]는 주 단추, [수정]·[삭제]는 보통 크기. 2단의 오른쪽이 두 화면에서 같게 읽히게 한다.
  return (
    <div className="intake-logs">
      <div className="card-head timeline-head">
        <h2>검토 기록 ({intake.log_count}건)</h2>
        {intake.in_pool && !adding && (
          <div className="timeline-actions">
            {/* 쓰다 만 새 검토 기록이 남아 있다 — [기록 추가] 를 누르면 되살아난다 (TODO 211 ③) */}
            {hasDraft(logDraftKey(intake.id)) && (
              <span className="draft-waiting" title="저장하지 않고 남은 기록이 있습니다 — [기록 추가] 를 누르면 되살아납니다">
                작성 중이던 기록 있음
              </span>
            )}
            <button onClick={() => setAdding(true)}>기록 추가</button>
          </div>
        )}
      </div>
      <p className="hint timeline-hint">
        인터뷰·협의로 문제 정의가 바뀌고 구체화되는 과정을 남깁니다. 승격해도 여기 남고, 과제에서는 링크로 이어집니다.
      </p>
      {adding && (
        <div className="card log-editor-card">
          <LogEditor
            intake={intake}
            base={base}
            onCancel={() => setAdding(false)}
            onSaved={() => {
              setAdding(false);
              onChanged();
            }}
            onUploaded={onChanged}
          />
        </div>
      )}
      {intake.logs.length === 0 && !adding && <p className="empty card">아직 기록이 없습니다.</p>}
      <ol className="timeline">
        {intake.logs.map((log) => {
          const auto = log.tags.includes("상태변경");
          if (editing === log.name)
            return (
              <li key={log.name} className="card log-editor-card">
                <LogEditor
                  intake={intake}
                  base={base}
                  log={log}
                  onCancel={() => setEditing(null)}
                  onSaved={() => {
                    setEditing(null);
                    onChanged();
                  }}
                  onUploaded={onChanged}
                />
              </li>
            );
          return (
            <li key={log.name} className={`card entry${auto ? " status-change" : ""}`}>
              <div className="entry-head">
                <div>
                  <span className="entry-date">
                    {log.date}
                    {log.author && <span className="entry-author">{log.author}</span>}
                  </span>
                  <h3>{log.title}</h3>
                </div>
                {intake.in_pool && !auto && (
                  <div className="entry-actions">
                    {hasDraft(logDraftKey(intake.id, log.name)) && (
                      <span className="draft-waiting" title="저장하지 않은 고친 내용이 남아 있습니다 — [수정] 을 누르면 되살아납니다">
                        작성 중
                      </span>
                    )}
                    <button data-write className="ghost" onClick={() => setEditing(log.name)}>
                      수정
                    </button>
                    <button
                      className="ghost danger"
                      onClick={async () => {
                        if (!window.confirm(`"${log.title}" 기록을 삭제 보관함으로 옮길까요?`)) return;
                        try {
                          await api.deleteIntakeLog(intake.id, log.name);
                          onChanged();
                        } catch (err) {
                          onError((err as Error).message);
                        }
                      }}
                    >
                      삭제
                    </button>
                  </div>
                )}
              </div>
              <div className="markdown" dangerouslySetInnerHTML={{ __html: renderMarkdown(log.body, `${base}/logs`) }} />
              {/* 이 기록의 첨부만 — 진행일지의 *첨부* 줄과 같은 모양 (TODO 150) */}
              {intake.attachments.some((item) => referencedIn(log.body, item)) && (
                <div className="entry-files">
                  <span className="muted">첨부</span>
                  {intake.attachments
                    .filter((item) => referencedIn(log.body, item))
                    .map((item) => (
                      <a key={item.rel_path} href={item.url} target="_blank" rel="noreferrer" className="file-chip">
                        {item.is_image ? "🖼" : "📄"} {item.orig_name}
                      </a>
                    ))}
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function LogEditor({
  intake,
  base,
  log,
  onCancel,
  onSaved,
  onUploaded,
}: {
  intake: Detail;
  base: string;
  log?: IntakeLog;
  onCancel: () => void;
  onSaved: () => void;
  onUploaded: () => void;
}) {
  const [date, setDate] = useState(log?.date ?? todayIso());
  const [title, setTitle] = useState(log?.title ?? "");
  const field = useMarkdownField(log?.body ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // 떠날 때 묻는다 (TODO 162)
  const dirty =
    field.value !== (log?.body ?? "") || title !== (log?.title ?? "") || date !== (log?.date ?? todayIso());
  // 편집 한 번의 장부 (TODO 213 ⑦)
  const ledger = useEditLedger<string>();
  useUnsaved(`intake-log:${intake.id}:${log?.name ?? "new"}`, dirty || !ledger.empty);
  // 임시 보관 (TODO 211 ③) — 요청 내용 · 진행일지와 같은 안전망. 인터뷰 기록을 길게 쓰다 창이 죽어도 돌아온다
  const draftKey = logDraftKey(intake.id, log?.name);
  const [restored, setRestored] = useState(false);
  useDraftKeeper(draftKey, { date, title, body: field.value }, !dirty);
  useEffect(() => {
    let alive = true;
    const original = { date: log?.date ?? todayIso(), title: log?.title ?? "", body: log?.body ?? "" };
    void loadDraft<{ date?: string; title?: string; body?: string }>(
      draftKey,
      (kept) =>
        typeof kept !== "object" ||
        kept === null ||
        (kept.body === original.body && kept.title === original.title && kept.date === original.date),
    ).then((kept) => {
      if (!alive || !kept || typeof kept.body !== "string") return;
      setDate(kept.date || original.date);
      setTitle(kept.title ?? "");
      field.setValue(kept.body);
      setRestored(true);
    });
    return () => {
      alive = false;
    };
    // 편집기를 열 때 한 번
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 날짜 · 제목 검사 (TODO 214 D5 · D14 · U10) — 비우면 서버가 오늘로 남긴다
  const dateError = dayProblem(date, "날짜");
  const titleError = titleProblem(title, "제목");
  const titleLeft = lengthHint(title, LIMITS.title);
  const blocker = dateError ?? titleError;

  async function save() {
    if (busy) return;
    if (blocker) {
      setError(blocker);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (log) await api.updateIntakeLog(intake.id, log.name, { date, title, body: field.value, mtime: log.mtime });
      else await api.createIntakeLog(intake.id, { date, title, body: field.value });
      // 지우기로 한 첨부는 저장할 때 지운다 (TODO 213 ③)
      await ledger.commit((path) => api.deleteIntakeAttachment(intake.id, path));
      dropDraft(draftKey);
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  /** [취소] — 사실대로 묻고, 버리면 이번에 올린 첨부를 지운다 (TODO 213 ⑦) */
  async function discard() {
    if (
      (dirty || !ledger.empty) &&
      !window.confirm(
        discardQuestion({ what: "기록을", uploaded: ledger.uploaded.length, doomed: ledger.doomedExisting.length }),
      )
    )
      return;
    const had = ledger.uploaded.length > 0;
    setBusy(true);
    await ledger.rollback((path) => api.deleteIntakeAttachment(intake.id, path));
    dropDraft(draftKey);
    onCancel();
    if (had) onUploaded();
  }

  return (
    <div
      className="log-editor"
      onKeyDown={(event) => {
        // Ctrl+S 는 편집기 어디서나 — 날짜 · 제목 칸에서도 (TODO 211 ⑥)
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
          event.preventDefault();
          void save();
        }
      }}
    >
      <div className="form-row">
        <label>
          날짜
          <input
            type="date"
            value={date}
            min={DATE_MIN}
            max={DATE_MAX}
            onChange={(e) => setDate(e.target.value)}
            aria-invalid={dateError ? true : undefined}
          />
          {!date && <span className="hint">비우면 오늘</span>}
          {dateError && <span className="form-warn date-warn">{dateError}</span>}
        </label>
        <label className="grow">
          제목
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="예: 1차 인터뷰 — 적용 범위 협의"
            autoFocus
            aria-invalid={titleError ? true : undefined}
          />
          {titleError ? (
            <span className="form-warn">{titleError}</span>
          ) : (
            titleLeft && <span className="hint length-count">{titleLeft}</span>
          )}
        </label>
      </div>
      <MarkdownArea
        field={field}
        intake={intake}
        base={`${base}/logs`}
        linkKind="markdown_log"
        onUploaded={onUploaded}
        onError={setError}
        ledger={ledger}
        placeholder="누구와 무엇을 이야기했고, 문제 정의가 어떻게 바뀌었는지 적습니다."
      />
      {restored && (
        <p className="hint restored">
          저장하지 않은 작성 중 내용을 복구했습니다.{" "}
          <button
            className="ghost small"
            onClick={() => {
              dropDraft(draftKey);
              setDate(log?.date ?? todayIso());
              setTitle(log?.title ?? "");
              field.setValue(log?.body ?? "");
              setRestored(false);
            }}
          >
            복구한 내용 버리기
          </button>
        </p>
      )}
      {error && <p className="error form-error">{error}</p>}
      <div className="form-actions">
        <button className="ghost" onClick={() => void discard()} disabled={busy}>
          취소
        </button>
        <button disabled={busy || Boolean(blocker)} title={blocker ?? undefined} onClick={() => void save()}>
          {busy ? "저장 중…" : "저장"}
        </button>
      </div>
    </div>
  );
}

// ── 승격 ───────────────────────────────────────────────────────────────────

/** 유관부서 담당자 칸의 이름들 — 서버처럼 쉼표 · 세미콜론 · 줄바꿈으로 나눈다 */
const partnerNames = (value: string) => splitNames(value.replace(/[;\n]/g, ","));

function PromoteDialog({
  intake,
  meta,
  onMetaChange,
  onClose,
  onDone,
}: {
  intake: Detail;
  meta: Meta;
  onMetaChange: () => void;
  onClose: () => void;
  onDone: (projectId: string) => void;
}) {
  const [plan, setPlan] = useState<PromotionPlan | null>(null);
  const [form, setForm] = useState<Record<string, string>>({});
  const [partners, setPartners] = useState<{ team: string; people: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showBody, setShowBody] = useState(false);
  // Esc 로 닫는다 — 보내는 중에는 막는다 (TODO 169)
  useEscape(onClose, !busy);

  useEffect(() => {
    api
      .promotionPlan(intake.id)
      .then((row) => {
        setPlan(row);
        setForm({
          title: row.title,
          type: row.type ?? "",
          status: row.status,
          owners: row.owners.join(", "),
          start_date: row.start_date ?? "",
          due_date: row.due_date ?? "",
          effect_expected: "",
          nature: row.nature ?? "",
          category: row.category ?? "",
          delivery: row.delivery ?? "",
          cost_kind: row.cost_kind ?? "",
          tags: row.tags.join(", "),
          decision_note: "",
        });
        setPartners(row.partners.map((p) => ({ team: p.team, people: p.people.join(", ") })));
      })
      .catch((err: Error) => setError(err.message));
  }, [intake.id]);

  const set = (key: string, value: string) => setForm((prev) => ({ ...prev, [key]: value }));

  // ── 과제 폼과 같은 검사 (TODO 214 F9 · U2 · U4) — 전에는 시작 > 마감을 막지 않았고, 효과는 `<form>` 밖이라
  //    음수 · `1,000` 이 저장한 뒤에야 400 이었다.
  const title = form.title ?? "";
  const titleError = plan ? (title.trim() ? titleProblem(title, "과제명") : "과제명을 적어 주세요.") : null;
  const titleLeft = lengthHint(title, LIMITS.title);
  const startProblem = dayProblem(form.start_date, "시작일");
  const dueProblem =
    dayProblem(form.due_date, "마감일") ?? dateOrderProblem(form.start_date, form.due_date, "시작일", "마감일");
  const effectError = effectProblem(form.effect_expected ?? "", "기대효과");
  // 유관부서 — 담당자만 적고 부서를 비운 줄은 말없이 사라졌다 (F8)
  const partnerMissingTeam = partners
    .map((row, index) => (!row.team.trim() && row.people.trim() ? index : -1))
    .filter((index) => index >= 0);
  const blockers = [
    titleError,
    startProblem,
    dueProblem,
    effectError,
    partnerMissingTeam.length > 0 ? "유관부서 줄에 부서를 적어 주세요." : null,
  ].filter((item): item is string => Boolean(item));
  // 담당 자동완성 — 떠난 사람은 뺀다 (D7 · D8). 전에는 명부 전체가 보였다
  const departed = new Set((meta.people_left ?? []).filter(isDeparted).map((person) => person.name));
  const ownerOptions = meta.people.filter((name) => !departed.has(name));

  async function promote() {
    if (!plan || busy || blockers.length > 0) return;
    setBusy(true);
    setError(null);
    try {
      // 같은 이름 과제 (D11)
      if (!(await confirmSameTitle(title))) return setBusy(false);
      // 담당자 — 명부에 없으면 추가할지, 떠난 사람이면 그래도 맡길지 (D6 · D7)
      const owners = splitNames(form.owners ?? "");
      const addsPeople = checkPeople(owners, meta).unknown.length > 0;
      if (!(await confirmPeople(owners, meta, api.addPerson, "담당자"))) return setBusy(false);
      if (addsPeople) onMetaChange();
      // 유관부서 담당자 — 처음 적는 이름이면 묻는다(명부에는 넣지 않는다). 접수에서 넘어온 이름은 묻지 않는다
      const planned = plan.partners.flatMap((row) => row.people);
      const newPartnerPeople = partners
        .flatMap((row) => partnerNames(row.people))
        .filter((name) => !planned.includes(name));
      if (
        !(await confirmOutsiders(newPartnerPeople, meta, { role: "유관부서 담당자", known: meta.partner_people ?? [] }))
      )
        return setBusy(false);
      // 금액 단위 (D4)
      const effect = (form.effect_expected ?? "").trim() === "" ? null : Number(form.effect_expected);
      if (!confirmEffects([{ label: "기대효과", value: effect }], meta)) return setBusy(false);
      const result = await api.promoteIntake(intake.id, {
        title: title.trim(),
        type: form.type,
        status: form.status,
        owners,
        partners: partners
          .filter((row) => row.team.trim())
          .map((row) => ({ team: row.team.trim(), people: partnerNames(row.people) })),
        start_date: form.start_date || null,
        due_date: form.due_date || null,
        effect_expected: effect,
        nature: form.nature || null,
        category: form.category || null,
        delivery: form.delivery || null,
        cost_kind: form.cost_kind || null,
        tags: form.tags.split(",").map((t) => t.trim()).filter(Boolean),
        // 착수 판정 메모 — 선택 (D17). 비우면 보내지 않는다
        ...((form.decision_note ?? "").trim() ? { decision_note: form.decision_note.trim() } : {}),
      });
      // 서버가 막지 않고 알린 것 — 같은 이름 · 명부에 없는 이름 · 떠난 사람은 위에서 물었으니 빼고
      for (const warning of warningList(result, FORM_SHOWN_WARNING)) notifyError(`승격했습니다 — ${warning}`);
      onDone(result.project_id);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="과제로 승격">
      <div className="modal promote-dialog">
        <div className="card-head">
          <h2>착수 · 과제로 승격</h2>
          <button className="ghost small" onClick={onClose}>
            닫기
          </button>
        </div>
        {!plan && !error && <p className="muted">준비 중…</p>}
        {plan && (
          <>
            <p className="hint">
              <b>{intake.id}</b> 을(를) 과제로 만듭니다 — 지금 승격하면 과제 번호 <b className="next-id">{plan.next_project_id}</b>
              {form.start_date ? " (시작일의 연도 기준)" : ""}. 접수 건은 <b>착수</b>로 닫히고, 양쪽에 링크가 남습니다.
            </p>
            <label>
              {/* 필수 표시 * (TODO 214 U1) · 남은 글자 (D14) */}
              과제명 *
              <input value={title} onChange={(e) => set("title", e.target.value)} aria-invalid={titleError ? true : undefined} />
              {titleError ? (
                <span className="form-warn">{titleError}</span>
              ) : (
                titleLeft && <span className="hint length-count">{titleLeft}</span>
              )}
            </label>
            <div className="form-row">
              <label>
                속성
                <select value={form.type} onChange={(e) => set("type", e.target.value)}>
                  <option value="">선택 안 함</option>
                  {meta.types.map((type) => (
                    <option key={type.key} value={type.key}>
                      {type.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                상태
                <select value={form.status} onChange={(e) => set("status", e.target.value)}>
                  {meta.statuses.map((status) => (
                    <option key={status.key} value={status.key}>
                      {status.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                시작일
                <input
                  type="date"
                  value={form.start_date}
                  min={DATE_MIN}
                  max={DATE_MAX}
                  onChange={(e) => set("start_date", e.target.value)}
                  aria-invalid={startProblem ? true : undefined}
                />
                {startProblem && <span className="form-warn date-warn">{startProblem}</span>}
              </label>
              <label>
                마감일
                <input
                  type="date"
                  value={form.due_date}
                  min={form.start_date || DATE_MIN}
                  max={DATE_MAX}
                  onChange={(e) => set("due_date", e.target.value)}
                  aria-invalid={dueProblem ? true : undefined}
                />
                {dueProblem && <span className="form-warn date-warn">{dueProblem}</span>}
              </label>
            </div>
            <label>
              담당자 (우리 팀 · 쉼표로 여러 명)
              <input list="promote-owner-options" value={form.owners} onChange={(e) => set("owners", e.target.value)} />
              <datalist id="promote-owner-options">
                {ownerOptions.map((name) => (
                  <option key={name} value={name} />
                ))}
              </datalist>
            </label>
            {plan.leader && (
              <p className="hint">
                과제리더 <b>{plan.leader}</b>
                {plan.leader_in_roster
                  ? "은(는) 담당자 명부에 있어 담당자로 넣었습니다."
                  : "은(는) 명부에 없어(현업) 유관부서 줄로 보냈습니다. 우리 팀 담당자를 위에 적어 주세요."}
              </p>
            )}
            <div className="partner-field">
              <div className="partner-head">
                <span>유관부서</span>
                <button data-write
                  type="button"
                  className="ghost small"
                  onClick={() => setPartners((prev) => [...prev, { team: "", people: "" }])}
                >
                  + 부서 추가
                </button>
              </div>
              {partners.map((row, index) => {
                // 비슷한 팀 이름 (D13) · 부서 없는 줄 (F8)
                const similar = similarTeam(row.team.trim(), meta.partner_teams ?? []);
                const noTeam = partnerMissingTeam.includes(index);
                return (
                  <div key={index} className="partner-row">
                    <input
                      value={row.team}
                      placeholder="부서"
                      list="promote-team-options"
                      aria-label={`유관부서 ${index + 1} 부서명`}
                      aria-invalid={noTeam ? true : undefined}
                      onChange={(e) =>
                        setPartners((prev) => prev.map((r, i) => (i === index ? { ...r, team: e.target.value } : r)))
                      }
                    />
                    <input
                      value={row.people}
                      placeholder="담당자 (쉼표로)"
                      list="promote-partner-person-options"
                      aria-label={`유관부서 ${index + 1} 담당자`}
                      onChange={(e) =>
                        setPartners((prev) => prev.map((r, i) => (i === index ? { ...r, people: e.target.value } : r)))
                      }
                    />
                    <button
                      type="button"
                      className="ghost small"
                      onClick={() => setPartners((prev) => prev.filter((_, i) => i !== index))}
                    >
                      삭제
                    </button>
                    {noTeam && <span className="form-warn partner-warn">부서를 적어 주세요 — 담당자만 적은 줄은 저장할 수 없습니다.</span>}
                    {similar && <span className="hint warn-text partner-warn">비슷한 팀이 있습니다: {similar}</span>}
                  </div>
                );
              })}
              {/* 자동완성 출처 통일 — 팀은 쓰던 팀, 사람은 쓰던 유관부서 담당자(떠난 사람 빼고) (U7) */}
              <datalist id="promote-team-options">
                {(meta.partner_teams ?? []).map((team) => (
                  <option key={team} value={team} />
                ))}
              </datalist>
              <datalist id="promote-partner-person-options">
                {(meta.partner_people ?? [])
                  .filter((name) => !departed.has(name))
                  .map((name) => (
                    <option key={name} value={name} />
                  ))}
              </datalist>
            </div>
            <div className="form-row class-row">
              {meta.classifications.map((info) => (
                <label key={info.key}>
                  {info.label}
                  <select value={form[info.key]} onChange={(e) => set(info.key, e.target.value)}>
                    <option value="">선택 안 함</option>
                    {[...info.items, ...(form[info.key] && !info.items.includes(form[info.key]) ? [form[info.key]] : [])].map(
                      (item) => (
                        <option key={item} value={item}>
                          {item}
                        </option>
                      ),
                    )}
                  </select>
                </label>
              ))}
            </div>
            <div className="form-row">
              <label>
                기대효과 (억원/년) — 검토한 값
                {/* 글 칸으로 받아 직접 검사한다 — 숫자 칸은 `1,000` 을 빈 값으로 넘겼다 (U4) */}
                <input
                  type="text"
                  inputMode="decimal"
                  value={form.effect_expected}
                  onChange={(e) => set("effect_expected", e.target.value)}
                  placeholder="검토 후 확정한 값"
                  aria-label="기대효과 (억원/년)"
                  aria-invalid={effectError ? true : undefined}
                />
                {effectError && <span className="form-warn">{effectError}</span>}
                {plan.effect_request !== null && (
                  <span className="hint">
                    요청자 추정 <b>{effectNumber(plan.effect_request)}</b> — 참고용입니다. 홈의 팀 합계에는 검토한 값만
                    들어갑니다.
                  </span>
                )}
              </label>
              <label className="grow">
                태그
                <input value={form.tags} onChange={(e) => set("tags", e.target.value)} />
                <TagSuggestions known={meta.tags ?? []} value={form.tags ?? ""} onPick={(next) => set("tags", next)} />
              </label>
            </div>
            {/* 착수 판정 메모 — 선택 (TODO 214 D17). 판정 줄 · 검토 기록에 남는다 */}
            <label className="stack-label">
              판정 메모 (선택)
              <textarea
                rows={2}
                value={form.decision_note ?? ""}
                onChange={(e) => set("decision_note", e.target.value)}
                placeholder="예: 9/12 사업부장 회의에서 착수 결정 — 1단계는 3라인만"
              />
            </label>
            <div className="promote-preview">
              <p>
                <b>개요로 넘어가는 것</b> —{" "}
                {plan.matched_sections.length > 0 ? (
                  <>같은 제목 {plan.matched_sections.map((s) => `「${s}」`).join(" ")}</>
                ) : (
                  <span className="muted">같은 제목으로 넘어가는 섹션이 없습니다 (요청 내용이 서식 그대로)</span>
                )}
                {plan.leftover_sections.length > 0 && (
                  <>
                    {" "}
                    · 짝 없는 섹션 {plan.leftover_sections.map((s) => `「${s}」`).join(" ")} → 맨 아래 「접수 내용」
                  </>
                )}
              </p>
              <p>
                <b>첨부</b> — {plan.attachments.length > 0 ? `${plan.attachments.length}건을 과제로 복사합니다 (접수에도 원본이 남습니다)` : "없음"}
              </p>
              <button type="button" className="ghost small" onClick={() => setShowBody((v) => !v)}>
                {showBody ? "개요 미리보기 접기" : "개요 미리보기"}
              </button>
              {showBody && (
                <div
                  className="markdown promote-body"
                  dangerouslySetInnerHTML={{
                    __html: renderMarkdown(plan.body_preview, `/intake-files/${encodeURIComponent(intake.dir_name)}`),
                  }}
                />
              )}
            </div>
          </>
        )}
        {/* 오류 · 막는 까닭은 단추 바로 위에 (TODO 214 U5) */}
        {error && <p className="error form-error">{error}</p>}
        {plan && blockers.length > 0 && (
          <p className="hint warn-text form-blocker">
            {startProblem || dueProblem ? "날짜를 고쳐야 승격할 수 있습니다." : `승격하려면 — ${blockers[0]}`}
          </p>
        )}
        <div className="form-actions">
          <button className="ghost" onClick={onClose} disabled={busy}>
            취소
          </button>
          <button
            className="primary commit"
            disabled={busy || !plan || blockers.length > 0}
            title={blockers[0]}
            onClick={() => void promote()}
          >
            {busy ? "승격 중…" : "승격하고 과제 열기"}
          </button>
        </div>
      </div>
    </div>
  );
}
