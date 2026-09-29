import { useEffect, useState } from "react";
import { api } from "../api";
import type { ClassificationKey, Intake, Meta } from "../types";

/**
 * 접수의 칸 (TODO 136) — 등록할 때와 고칠 때 같은 폼이다.
 *
 * **필수는 과제명 하나다.** 1단계는 팀장이 받은 파일을 보고 대리 입력하는 것이라, 모르는 칸이
 * 있어도 일단 받아 두고 인터뷰에서 채운다. 현업에게 열 때 입력 부담이 크면 아무도 안 쓴다.
 * 본문(배경·성과지표·추진내용…)은 여기가 아니라 상세 화면의 [요청 내용]에서 쓴다.
 */
interface Props {
  meta: Meta;
  initial?: Partial<Intake>;
  submitLabel: string;
  /** 등록할 때 고른 파일도 함께 넘긴다 — 등록 직후 차례로 올린다 (TODO 138) */
  onSubmit: (payload: Partial<Intake>, files: File[]) => Promise<void>;
  onCancel: () => void;
}

const PRIORITIES = ["상", "중", "하"];

export default function IntakeForm({ meta, initial, submitLabel, onSubmit, onCancel }: Props) {
  const creating = !initial?.id;
  const [form, setForm] = useState(() => ({
    title: initial?.title ?? "",
    leader: initial?.leader ?? "",
    leader_team: initial?.leader_team ?? "",
    received_on: initial?.received_on ?? new Date().toISOString().slice(0, 10),
    start_date: initial?.start_date ?? "",
    due_date: initial?.due_date ?? "",
    effect_request: initial?.effect_request?.toString() ?? "",
    priority: initial?.priority ?? "",
    priority_note: initial?.priority_note ?? "",
    tags: (initial?.tags ?? []).join(", "),
  }));
  const [classes, setClasses] = useState<Record<ClassificationKey, string>>(() => ({
    nature: initial?.nature ?? "",
    category: initial?.category ?? "",
    delivery: initial?.delivery ?? "",
    cost_kind: initial?.cost_kind ?? "",
  }));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // 받은 과제정의서·부연 설명을 들고 **한 번에** 등록한다. 예전에는 등록한 뒤 상세에 다시 들어가야 했다.
  const [files, setFiles] = useState<File[]>([]);
  // FileList 는 **살아 있는 목록**이다 — 입력 칸을 비우거나 끌어다 놓기가 끝나면 비워진다.
  // 상태 갱신 함수 안에서 읽으면 그때는 이미 비어 있으므로 여기서 바로 배열로 떠 둔다.
  const addFiles = (list: FileList | File[] | null) => {
    const picked = Array.from(list ?? []);
    if (picked.length > 0) setFiles((prev) => [...prev, ...picked]);
  };
  const [nextId, setNextId] = useState<string | null>(null);
  const update = (key: keyof typeof form, value: string) => setForm((prev) => ({ ...prev, [key]: value }));

  // 붙을 접수 번호를 미리 보여 준다 — 번호의 연도는 접수일을 따른다
  useEffect(() => {
    if (!creating) return;
    let alive = true;
    api
      .nextIntakeId(form.received_on)
      .then((row) => alive && setNextId(row.id))
      .catch(() => alive && setNextId(null));
    return () => {
      alive = false;
    };
  }, [creating, form.received_on]);

  // 과제리더 자동완성 — 명부의 이름을 먼저 보여 준다. 명부에 없는 이름(현업 사람)도 받는다.
  const leaders = meta.people.filter((name) => !(meta.people_left ?? []).some((p) => p.name === name));

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onSubmit({
        title: form.title.trim(),
        leader: form.leader.trim() || null,
        leader_team: form.leader_team.trim() || null,
        received_on: form.received_on || null,
        start_date: form.start_date || null,
        due_date: form.due_date || null,
        effect_request: form.effect_request.trim() === "" ? null : Number(form.effect_request),
        priority: form.priority || null,
        priority_note: form.priority_note.trim() || null,
        tags: form.tags.split(",").map((tag) => tag.trim()).filter(Boolean),
        nature: classes.nature || null,
        category: classes.category || null,
        delivery: classes.delivery || null,
        cost_kind: classes.cost_kind || null,
      }, creating ? files : []);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="project-form intake-form" onSubmit={submit}>
      <label>
        과제명 <span className="hint">예: 00을 위한 00 구축/개발</span>
        <input value={form.title} onChange={(e) => update("title", e.target.value)} required autoFocus />
      </label>
      <div className="form-row">
        <label>
          과제리더
          <input
            list="intake-leader-options"
            value={form.leader}
            onChange={(e) => update("leader", e.target.value)}
            placeholder="예: 홍길동"
          />
          <datalist id="intake-leader-options">
            {leaders.map((name) => (
              <option key={name} value={name} />
            ))}
          </datalist>
        </label>
        <label>
          소속
          <input
            list="intake-team-options"
            value={form.leader_team}
            onChange={(e) => update("leader_team", e.target.value)}
            placeholder="예: 압연기술팀"
          />
          <datalist id="intake-team-options">
            {(meta.partner_teams ?? []).map((team) => (
              <option key={team} value={team} />
            ))}
          </datalist>
        </label>
        <label>
          접수일
          <input type="date" value={form.received_on} onChange={(e) => update("received_on", e.target.value)} />
        </label>
      </div>
      <p className="hint">
        과제리더가 <b>담당자 명부</b>에 있는 사람이면 승격할 때 과제의 담당자로, 없으면(현업) <b>유관부서</b>로 들어갑니다.
      </p>
      <div className="form-row class-row">
        {meta.classifications.map((info) => {
          const value = classes[info.key];
          const items = value && !info.items.includes(value) ? [...info.items, value] : info.items;
          return (
            <label key={info.key}>
              {info.label}
              <select value={value} onChange={(e) => setClasses((prev) => ({ ...prev, [info.key]: e.target.value }))}>
                <option value="">선택 안 함</option>
                {items.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
          );
        })}
      </div>
      <div className="form-row">
        <label>
          추진 시작
          <input type="date" value={form.start_date} onChange={(e) => update("start_date", e.target.value)} />
        </label>
        <label>
          추진 종료
          <input type="date" value={form.due_date} onChange={(e) => update("due_date", e.target.value)} />
        </label>
        <label>
          요청 기대효과 (억원/년)
          <input
            type="number"
            step="0.01"
            min="0"
            value={form.effect_request}
            onChange={(e) => update("effect_request", e.target.value)}
            placeholder="요청자 추정"
          />
          <span className="hint">과제로 옮기지 않습니다 — 승격할 때 참고로만 보입니다</span>
        </label>
      </div>
      <div className="form-row">
        <label>
          중요도
          <select value={form.priority} onChange={(e) => update("priority", e.target.value)}>
            <option value="">정하지 않음</option>
            {PRIORITIES.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        <label className="grow">
          중요도 근거 (한 줄)
          <input
            value={form.priority_note}
            onChange={(e) => update("priority_note", e.target.value)}
            placeholder="예: 품질 클레임 직결"
          />
        </label>
        <label>
          태그
          <input value={form.tags} onChange={(e) => update("tags", e.target.value)} placeholder="쉼표로 구분" />
        </label>
      </div>
      {creating && (
        <div
          className="intake-form-files"
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => {
            event.preventDefault();
            addFiles(event.dataTransfer.files);
          }}
        >
          <label className="attach-button">
            📎 파일 첨부
            <input
              type="file"
              multiple
              hidden
              onChange={(event) => {
                addFiles(event.target.files);
                event.target.value = "";
              }}
            />
          </label>
          <span className="hint">
            받은 과제정의서(PPT)·부연 설명을 함께 올립니다 — 끌어다 놓아도 됩니다. 등록하면 첨부에 들어갑니다.
          </span>
          {files.length > 0 && (
            <ul className="intake-form-file-list">
              {files.map((file, index) => (
                <li key={`${file.name}-${index}`}>
                  {file.name}
                  <button
                    type="button"
                    className="ghost small"
                    onClick={() => setFiles((prev) => prev.filter((_, i) => i !== index))}
                    aria-label={`${file.name} 빼기`}
                  >
                    빼기
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {creating && (
        <p className="hint next-id-hint">
          접수 번호는 <b>접수일의 연도</b>로 붙습니다{nextId && <> — 지금 등록하면 <b className="next-id">{nextId}</b></>}.
          과제 번호는 <b>착수할 때</b> 붙습니다.
        </p>
      )}
      {error && <p className="error">{error}</p>}
      <div className="form-actions">
        <button type="button" className="ghost" onClick={onCancel} disabled={busy}>
          취소
        </button>
        <button type="submit" disabled={busy}>
          {busy ? "저장 중…" : submitLabel}
        </button>
      </div>
    </form>
  );
}
