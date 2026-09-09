import { useEffect, useState } from "react";
import { api } from "../api";
import type { Meta, Partner, Project } from "../types";
import TagSuggestions from "./TagSuggestions";
import UnknownOwners from "./UnknownOwners";

interface Props {
  meta: Meta;
  /** 명부에 사람을 새로 넣었을 때 상단 meta 를 다시 읽는다 */
  onMetaChange?: () => void;
  initial?: Partial<Project>;
  submitLabel: string;
  onSubmit: (payload: Partial<Project>) => Promise<void>;
  onCancel: () => void;
}

export default function ProjectForm({ meta, initial, submitLabel, onSubmit, onCancel, onMetaChange = () => undefined }: Props) {
  // 자동완성은 명부를 먼저 보여 주고, 명부에 없지만 이미 쓰이는 이름을 뒤에 붙인다.
  const ownerOptions = [...meta.people, ...meta.owners.filter((name) => !meta.people.includes(name))];
  const [form, setForm] = useState({
    title: initial?.title ?? "",
    status: initial?.status ?? "in_progress",
    type: initial?.type ?? "",
    group: initial?.group ?? "",
    owners: (initial?.owners ?? []).join(", "),
    start_date: initial?.start_date ?? "",
    due_date: initial?.due_date ?? "",
    completed_at: initial?.completed_at ?? "",
    effect_expected: initial?.effect_expected?.toString() ?? "",
    effect_verified: initial?.effect_verified?.toString() ?? "",
    tags: (initial?.tags ?? []).join(", "),
  });
  /**
   * 유관부서 (TODO 92). 한 줄이 팀 하나이고, 담당자는 그 줄 안에서 쉼표로 적는다.
   *
   * **팀과 사람을 한 칸에 섞어 적게 하지 않는다.** "설비기술팀 김철수" 처럼 한 칸에 두면
   * 어디까지가 팀이고 어디부터가 사람인지 아무도 모른다. 줄을 나누는 편이 입력은
   * 한 번 더지만, 그 뒤로 집계·검색·표시가 전부 흔들리지 않는다.
   */
  const [partners, setPartners] = useState<{ team: string; people: string }[]>(
    () => (initial?.partners ?? []).map((row) => ({ team: row.team, people: row.people.join(", ") })),
  );
  const setPartner = (index: number, key: "team" | "people", value: string) =>
    setPartners((prev) => prev.map((row, i) => (i === index ? { ...row, [key]: value } : row)));

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /**
   * 저장하면 붙을 과제 번호 (TODO 95).
   *
   * 번호의 연도는 **등록한 날이 아니라 착수년도**다. 그 사실은 문장으로 적어 두는 것보다
   * **실제 번호를 미리 보여 주는 편**이 확실하다 — 지난해 과제를 등록하면서 시작일을
   * 비워 둔 채 저장하면 올해 번호가 붙는데, 저장 뒤에는 알아채기 어렵다.
   * 고칠 때는 띄우지 않는다 — 이미 붙은 번호는 이 폼이 바꾸지 않는다.
   */
  const creating = !initial?.id;
  const [nextId, setNextId] = useState<string | null>(null);
  useEffect(() => {
    if (!creating) return;
    let alive = true;
    api
      .nextProjectId(form.start_date)
      .then((row) => alive && setNextId(row.id))
      .catch(() => alive && setNextId(null));
    return () => {
      alive = false;
    };
  }, [creating, form.start_date]);

  const update = (key: string, value: string) => setForm((prev) => ({ ...prev, [key]: value }));

  // 비우면 null 로 보낸다 — "아직 안 정했다"와 "0원"은 다른 뜻이다.
  const effect = (value: string): number | null => (value.trim() === "" ? null : Number(value));
  // 단순 현황 관리를 과제로 세운 경우. 보고 대상 후보에서만 빠진다 (TODO 80).
  const [noReport, setNoReport] = useState(Boolean(initial?.no_report));

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onSubmit({
        title: form.title.trim(),
        status: form.status,
        type: form.type || null,
        group: form.group.trim() || null,
        owners: form.owners
          .split(",")
          .map((name) => name.trim())
          .filter(Boolean),
        start_date: form.start_date || null,
        due_date: form.due_date || null,
        // 완료 상태가 아니면 완료일을 보내지 않는다 — 서버가 비운다 (TODO 104).
        ...(form.status === "done" ? { completed_at: form.completed_at || null } : {}),
        effect_expected: effect(form.effect_expected),
        effect_verified: effect(form.effect_verified),
        no_report: noReport,
        // 팀 이름이 빈 줄은 보내지 않는다. 사람 이름을 나누는 일은 **서버가** 한다 (TODO 74).
        partners: partners
          .filter((row) => row.team.trim())
          .map((row) => ({ team: row.team.trim(), people: row.people })) as unknown as Partner[],
        tags: form.tags
          .split(",")
          .map((tag) => tag.trim())
          .filter(Boolean),
      });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="project-form" onSubmit={handleSubmit}>
      <label>
        과제명
        <input
          value={form.title}
          onChange={(event) => update("title", event.target.value)}
          required
          autoFocus
        />
      </label>
      <div className="form-row">
        <label>
          상태
          <select value={form.status} onChange={(event) => update("status", event.target.value)}>
            {meta.statuses.map((status) => (
              <option key={status.key} value={status.key}>
                {status.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          속성
          <select value={form.type ?? ""} onChange={(event) => update("type", event.target.value)}>
            <option value="">선택 안 함</option>
            {meta.types.map((type) => (
              <option key={type.key} value={type.key}>
                {type.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          그룹 (예 : 회의체, 지시사항 등)
          <input
            list="group-options"
            value={form.group ?? ""}
            onChange={(event) => update("group", event.target.value)}
            placeholder="예: 회의체"
          />
          <datalist id="group-options">
            {meta.groups.map((group) => (
              <option key={group} value={group} />
            ))}
          </datalist>
        </label>
        <label>
          담당자 (여러 명은 쉼표로)
          <input
            list="owner-options"
            value={form.owners}
            onChange={(event) => update("owners", event.target.value)}
            placeholder="예: 권경락, 홍길동"
          />
          <datalist id="owner-options">
            {ownerOptions.map((name) => (
              <option key={name} value={name} />
            ))}
          </datalist>
          <UnknownOwners
            known={meta.people}
            value={form.owners}
            onAdded={onMetaChange}
          />
        </label>
      </div>
      {/* ── 유관부서 (TODO 92) ────────────────────────────────────────
          두 팀 이상이 함께 하고, 팀마다 담당자가 여럿인 일이 흔하다.
          팀은 줄로, 사람은 그 줄 안에서 쉼표로 나눈다. */}
      <div className="partner-field">
        <div className="partner-head">
          <span>유관부서</span>
          <span className="hint">함께 일하는 팀과 그쪽 담당자입니다. 담당자는 나중에 채워도 됩니다.</span>
        </div>
        {partners.length > 0 && (
          <ul className="partner-rows">
            {partners.map((row, index) => (
              <li key={index}>
                <input
                  list="partner-team-options"
                  value={row.team}
                  onChange={(event) => setPartner(index, "team", event.target.value)}
                  placeholder="부서 (예: 설비기술팀)"
                  aria-label={`유관부서 ${index + 1} 부서명`}
                />
                <input
                  list="partner-person-options"
                  value={row.people}
                  onChange={(event) => setPartner(index, "people", event.target.value)}
                  placeholder="담당자 (여러 명은 쉼표로)"
                  aria-label={`유관부서 ${index + 1} 담당자`}
                />
                <button
                  type="button"
                  className="ghost small danger"
                  onClick={() => setPartners((prev) => prev.filter((_, i) => i !== index))}
                >
                  삭제
                </button>
              </li>
            ))}
          </ul>
        )}
        <button
          type="button"
          className="ghost small"
          onClick={() => setPartners((prev) => [...prev, { team: "", people: "" }])}
        >
          + 부서 추가
        </button>
        <datalist id="partner-team-options">
          {meta.partner_teams?.map((team) => (
            <option key={team} value={team} />
          ))}
        </datalist>
        <datalist id="partner-person-options">
          {meta.partner_people?.map((name) => (
            <option key={name} value={name} />
          ))}
        </datalist>
      </div>

      <div className="form-row">
        <label>
          시작일
          <input
            type="date"
            value={form.start_date ?? ""}
            onChange={(event) => update("start_date", event.target.value)}
          />
        </label>
        <label>
          마감일
          <input
            type="date"
            value={form.due_date ?? ""}
            onChange={(event) => update("due_date", event.target.value)}
          />
        </label>
        {/* 완료일 (TODO 104) — 상태가 완료일 때만 선다. 비워 두면 오늘로 남는다.
            지난 과제를 뒤늦게 넣을 때는 여기서 실제 끝난 날을 적는다. */}
        {form.status === "done" && (
          <label>
            완료일
            <input
              type="date"
              value={form.completed_at ?? ""}
              onChange={(event) => update("completed_at", event.target.value)}
            />
            <span className="hint">비워 두면 오늘 날짜로 남습니다</span>
          </label>
        )}

        <label>
          태그(예 : 공정, 쉼표 구분)
          <input
            value={form.tags}
            onChange={(event) => update("tags", event.target.value)}
            placeholder="예: 공정, 수명평가"
          />
          <TagSuggestions
            known={meta.tags}
            value={form.tags}
            onPick={(next) => update("tags", next)}
          />
        </label>
      </div>
      {/* 번호의 연도는 등록한 날이 아니라 **착수년도**다 (TODO 95).
          적어 두기보다 붙을 번호를 그대로 보여 주는 편이 확실하다. */}
      {creating && (
        <p className="hint next-id-hint">
          과제 번호는 <b>시작일의 연도</b>로 붙습니다
          {nextId && (
            <>
              {" "}— 지금 저장하면 <b className="next-id">{nextId}</b>
            </>
          )}
          .{!form.start_date && " 시작일을 비워 두면 올해로 붙습니다."}
        </p>
      )}
      <div className="form-row">
        <label>
          기대효과 (억원/년)
          <input
            type="number"
            step="0.01"
            min="0"
            value={form.effect_expected}
            onChange={(event) => update("effect_expected", event.target.value)}
            placeholder="예: 1.2"
          />
        </label>
        <label>
          실증효과 (억원/년)
          <input
            type="number"
            step="0.01"
            min="0"
            value={form.effect_verified}
            onChange={(event) => update("effect_verified", event.target.value)}
            placeholder="과제가 끝난 뒤 채웁니다"
          />
          {/* 완료로 바꾸는 순간 한 번 묻는다 (TODO 106-C). 막지는 않는다 — 아직 모를 수 있다. */}
          {form.status === "done" && form.effect_verified.trim() === "" && (
            <span className="hint warn-text">
              완료 과제입니다. 실증효과를 적어 두면 홈의 실증 합계에 잡힙니다. (모르면 비워 두어도 됩니다)
            </span>
          )}
        </label>
        <p className="hint effect-hint">
          <b>소수점 둘째 자리까지</b> 적을 수 있습니다 (억원/년 단위라 둘째 자리가 100만 원).
          <br />
          정성적 효과와 산출 근거는 <b>과제 개요</b>에 적습니다.
          근거 자료(엑셀·PPT)는 개요의 [파일 첨부]로 붙일 수 있습니다.
        </p>
      </div>

      <div className="form-row">
        <label className="check-label">
          <input
            type="checkbox"
            checked={noReport}
            onChange={(event) => setNoReport(event.target.checked)}
          />
          <span>
            <b>별도 보고 불필요</b>
            <span className="hint">
              단순 현황 관리처럼 주간보고에 올리지 않는 과제입니다. 체크하면{" "}
              <b>보고 대상 후보에서 빠집니다</b> — 필요할 때 손으로 보고를 남기는 길은 그대로입니다.
            </span>
          </span>
        </label>
      </div>
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button type="button" className="ghost" onClick={onCancel}>
          취소
        </button>
        <button type="submit" disabled={busy}>
          {busy ? "저장 중…" : submitLabel}
        </button>
      </div>
    </form>
  );
}
