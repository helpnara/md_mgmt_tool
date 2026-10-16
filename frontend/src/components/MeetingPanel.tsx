import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { Meeting, MeetingFollowup, MeetingListing, Meta } from "../types";
import { attempt, notifyError } from "../notify";
import { useFormUnsaved } from "../unsaved";
import { confirmDiscard, todayIso } from "../util";
import {
  DATE_MAX,
  DATE_MIN,
  addDays,
  confirmPeople,
  dateProblem,
  isFuture,
  orderProblem,
  personNameProblem,
  warningList,
} from "../inputRules";
import { departedNames, freshRoster } from "./roster";

/** "하기로 한 것" 은 30줄까지 (TODO 214 U6) */
const FOLLOWUP_MAX = 30;

/**
 * 팀원 면담 (TODO 182) — 팀원역량 화면 안.
 *
 * * 사람을 고르면 그 사람의 면담이 날짜순으로, 고르지 않으면 팀 전체의 **아직 닫지 않은 "하기로 한 것"**.
 * * 하기로 한 것은 [완료]로 닫을 때까지 보인다 — 다음 면담에서 꺼낼 첫 줄이다(보고의 "답하지 않은 지시"와 같은 모양).
 * * 민감한 기록이라 통합 검색 · AI 요약 · 내보내기에 넣지 않는다. 화면이 그 사실과, 지워도 보관함 · 이전 버전에 남는다는 것을 알린다.
 */
interface Props {
  meta: Meta;
  person: string;
  people: string[];
  onChanged: () => void;
  onPickPerson: (name: string) => void;
}

// 이 PC 의 날짜 — toISOString 은 UTC 라 한국 오전 9시 전에는 어제가 된다
const today = () => todayIso();

export default function MeetingPanel({ meta, person, people, onChanged, onPickPerson }: Props) {
  const [data, setData] = useState<MeetingListing | null>(null);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<number | null>(null);
  const [opened, setOpened] = useState<Set<number>>(new Set());
  // 저장은 됐지만 알릴 것 — 미래 날짜 면담 같은 서버의 warnings (TODO 214 D5)
  const [notice, setNotice] = useState<string[]>([]);
  // 열린 면담 폼이 고쳐졌는가 — [면담 추가] · [수정] 을 다시 눌러 닫을 때도 묻는다 (TODO 211 ①)
  const formDirty = useRef(false);
  const closeFormOk = () => {
    if (!confirmDiscard(formDirty.current)) return false;
    formDirty.current = false;
    return true;
  };

  const load = () =>
    api
      .meetings(person || undefined)
      .then(setData)
      .catch((err: Error) => notifyError(err.message));
  useEffect(() => {
    setAdding(false);
    setEditing(null);
    setNotice([]);
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [person]);

  const changed = () => {
    void load();
    onChanged();
  };
  const saved = (warnings: string[]) => {
    setNotice(warnings);
    changed();
  };

  const toggle = async (meeting: Meeting, index: number) => {
    const followups = meeting.followups.map((item, i) =>
      i === index ? { ...item, done: item.done ? null : today() } : item,
    );
    if (await attempt(() => api.updateMeeting(meeting.id, { followups }))) changed();
  };

  const remove = async (meeting: Meeting) => {
    if (
      !window.confirm(
        `${meeting.person} 님과의 ${meeting.date} 면담 기록을 삭제할까요?\n\n삭제 보관함과 이전 버전에는 남습니다 — 완전히 없애려면 설정 → 삭제 보관함에서 비우세요.`,
      )
    )
      return;
    if (await attempt(() => api.deleteMeeting(meeting.id))) changed();
  };

  const items = data?.items ?? [];
  const open = data?.open_followups ?? [];

  return (
    <div className="card wide meeting-panel">
      <div className="card-head">
        <h2>
          면담 기록
          {person ? <span className="hint"> · {person} · {items.length}건</span> : <span className="hint"> · 팀 전체의 하기로 한 것</span>}
        </h2>
        <button
          onClick={() => {
            if ((adding || editing !== null) && !closeFormOk()) return;
            setAdding((value) => !value);
            setEditing(null);
          }}
          className={adding ? "ghost on" : undefined}
        >
          면담 추가
        </button>
      </div>
      <p className="hint">
        무엇을 이야기했고 <b>무엇을 하기로 했는지</b> 남깁니다. 하기로 한 것은 [완료]로 닫을 때까지 보입니다. 이 기록은{" "}
        <b>통합 검색 · AI 요약 · 내보내기에 들어가지 않고</b>, 역량 이력 수에도 세지 않습니다.
      </p>

      {notice.length > 0 && (
        <p className="hint warn-text meeting-notice" role="status">
          저장했습니다 — {notice.join(" · ")}
        </p>
      )}

      {adding && (
        <MeetingForm
          meta={meta}
          people={people}
          initial={{ person, date: today() }}
          dirtyRef={formDirty}
          onClose={() => setAdding(false)}
          onSaved={(warnings) => { setAdding(false); saved(warnings); }}
        />
      )}

      {!person ? (
        open.length === 0 ? (
          <p className="empty">열려 있는 "하기로 한 것"이 없습니다. 사람을 고르면 그 사람의 면담 기록이 보입니다.</p>
        ) : (
          <ul className="meeting-open-list">
            {open.map((item) => (
              <li key={`${item.meeting_id}-${item.index}`}>
                <input
                  type="checkbox"
                  aria-label={`${item.text} 완료`}
                  onChange={async () => {
                    const meeting = (await api.meetings(item.person)).items.find((m) => m.id === item.meeting_id);
                    if (meeting) await toggle(meeting, item.index);
                  }}
                />
                <button className="linkish" onClick={() => onPickPerson(item.person)}>
                  {item.person}
                </button>
                <span className="muted">{item.date} 면담</span>
                <span>{item.text}</span>
              </li>
            ))}
          </ul>
        )
      ) : items.length === 0 ? (
        <p className="empty">{person} 님과의 면담 기록이 아직 없습니다.</p>
      ) : (
        <ul className="meeting-list">
          {items.map((meeting) => (
            <li key={meeting.id} className="meeting-item">
              <div className="meeting-head">
                <span className="activity-date">{meeting.date}</span>
                {meeting.kind && <span className="tag">{meeting.kind}</span>}
                <strong className="meeting-summary">{meeting.summary}</strong>
                {meeting.next_date && <span className="muted">다음 면담 {meeting.next_date}</span>}
                <span className="grow" />
                {meeting.body && (
                  <button
                    className={opened.has(meeting.id) ? "ghost small on" : "ghost small"}
                    onClick={() =>
                      setOpened((prev) => {
                        const next = new Set(prev);
                        if (next.has(meeting.id)) next.delete(meeting.id);
                        else next.add(meeting.id);
                        return next;
                      })
                    }
                  >
                    내용
                  </button>
                )}
                <button data-write
                  className={editing === meeting.id ? "ghost small on" : "ghost small"}
                  onClick={() => {
                    if ((adding || editing !== null) && !closeFormOk()) return;
                    setEditing(editing === meeting.id ? null : meeting.id);
                    setAdding(false);
                  }}
                >
                  수정
                </button>
                <button className="ghost small danger" onClick={() => void remove(meeting)}>
                  삭제
                </button>
              </div>
              {meeting.followups.length > 0 && (
                <ul className="meeting-followups">
                  {meeting.followups.map((item, index) => (
                    <li key={index} className={item.done ? "done" : undefined}>
                      <label>
                        <input type="checkbox" checked={Boolean(item.done)} onChange={() => void toggle(meeting, index)} />
                        <span>{item.text}</span>
                        {item.done && <span className="muted"> · {item.done} 완료</span>}
                      </label>
                    </li>
                  ))}
                </ul>
              )}
              {opened.has(meeting.id) && meeting.body && <div className="meeting-body">{meeting.body}</div>}
              {editing === meeting.id && (
                <MeetingForm
                  meta={meta}
                  people={people}
                  initial={meeting}
                  dirtyRef={formDirty}
                  onClose={() => setEditing(null)}
                  onSaved={(warnings) => { setEditing(null); saved(warnings); }}
                />
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function MeetingForm({
  meta,
  people,
  initial,
  dirtyRef,
  onClose,
  onSaved,
}: {
  meta: Meta;
  people: string[];
  initial: Partial<Meeting>;
  /** 고쳤는가를 바깥(패널의 [면담 추가] · [수정] 토글)에 알린다 */
  dirtyRef?: { current: boolean };
  onClose: () => void;
  /** 저장했다 — 서버가 알린 것(warnings)을 함께 */
  onSaved: (warnings: string[]) => void;
}) {
  const [form, setForm] = useState({
    person: initial.person ?? "",
    date: initial.date ?? today(),
    kind: initial.kind ?? meta.meeting_kinds[0] ?? "",
    summary: initial.summary ?? "",
    next_date: initial.next_date ?? "",
    body: initial.body ?? "",
  });
  const [followups, setFollowups] = useState<MeetingFollowup[]>(
    initial.followups?.length ? initial.followups : [{ text: "", done: null }],
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useFormUnsaved(`meeting-form:${initial.id ?? "new"}`, { form, followups }, busy);
  // [취소] · Esc — 고친 것이 있으면 버릴지 묻는다 (TODO 211 ①)
  const [initialSnapshot] = useState(() => JSON.stringify({ form, followups }));
  const dirty = JSON.stringify({ form, followups }) !== initialSnapshot;
  if (dirtyRef) dirtyRef.current = dirty && !busy;
  useEffect(
    () => () => {
      if (dirtyRef) dirtyRef.current = false; // 닫히면 바깥 표시도 지운다
    },
    [dirtyRef],
  );
  const cancel = () => {
    if (busy) return;
    if (confirmDiscard(dirty)) onClose();
  };
  const listRef = useRef<HTMLDivElement>(null);
  /** "하기로 한 것" 칸에서 Enter — 저장하지 않고 **아래에 줄을 하나 더해** 그리로 간다 (TODO 211 ⑥) */
  const addLineAfter = (index: number) => {
    setFollowups((prev) => [...prev.slice(0, index + 1), { text: "", done: null }, ...prev.slice(index + 1)]);
    window.requestAnimationFrame(() =>
      listRef.current?.querySelectorAll<HTMLInputElement>('input[data-enter="add"]')[index + 1]?.focus(),
    );
  };
  const set = (key: keyof typeof form, value: string) => setForm((prev) => ({ ...prev, [key]: value }));
  // 구분은 설정의 목록만 (TODO 214 F15) — 고칠 때는 그 기록의 옛 구분도 남겨 둔다(목록에서 빠졌어도 지우지 않게)
  const oldKind = initial.id && initial.kind && !meta.meeting_kinds.includes(initial.kind) ? initial.kind : null;
  const kinds = oldKind ? [...meta.meeting_kinds, oldKind] : meta.meeting_kinds;

  // 새 면담 상대에서 떠난 사람은 뺀다 (TODO 214 D7) — 떠난 날이 오늘 이후면 아직 있는 사람(D8)
  const departed = departedNames(meta);
  const options = people.filter((name) => !departed.has(name));
  const person = form.person.trim();
  const personChanged = person !== (initial.person ?? "").trim() || !initial.id;

  // 화면이 먼저 막는다 (TODO 216 · 214 U2 · U3) — 다음 면담 ≤ 면담일은 서버가 400 으로 거절한다(같은 날도)
  const personProblem = personNameProblem(form.person);
  const departedWarn = personChanged && departed.has(person) ? `${person} — 명부에서 떠난 사람입니다. 저장할 때 한 번 더 묻습니다.` : null;
  const dateIssue = form.date ? dateProblem(form.date, "면담일") : "면담일을 적어 주세요.";
  const futureWarn = !dateIssue && isFuture(form.date) ? "오늘보다 뒤의 날짜입니다 — 잡아 둔 면담이면 그대로 저장해도 됩니다." : null;
  const nextIssue =
    dateProblem(form.next_date, "다음 면담") ??
    orderProblem(form.date, form.next_date, "다음 면담은 면담일 뒤여야 합니다.", true);
  const filled = followups.filter((item) => item.text.trim());
  const followupIssue = filled.length > FOLLOWUP_MAX ? `하기로 한 것은 ${FOLLOWUP_MAX}줄까지입니다 (지금 ${filled.length}줄).` : null;
  const canSave =
    !busy && Boolean(person) && Boolean(form.summary.trim()) && !personProblem && !dateIssue && !nextIssue && !followupIssue;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!canSave) return;
    setBusy(true);
    setError(null);
    const payload = {
      ...form,
      person,
      kind: form.kind || null,
      next_date: form.next_date || null,
      followups: filled,
    };
    try {
      // 명부에 없는 이름은 묻는다 — 예전에는 오타가 명부에 조용히 들어갔다 (TODO 214 D6). 고칠 때 사람이 그대로면 묻지 않는다
      if (personChanged && !(await confirmPeople([person], await freshRoster(meta), api.addPerson, "면담 상대"))) return;
      const result = initial.id ? await api.updateMeeting(initial.id, payload) : await api.createMeeting(payload);
      onSaved(warningList(result));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      className="meeting-form"
      onSubmit={submit}
      onKeyDown={(event) => {
        if (event.key === "Escape" && !event.defaultPrevented) {
          event.preventDefault();
          cancel();
        }
      }}
    >
      <div className="form-row">
        <label>
          누구와 *
          <input
            list="meeting-people"
            value={form.person}
            onChange={(e) => set("person", e.target.value)}
            required
            aria-invalid={personProblem ? true : undefined}
          />
          <datalist id="meeting-people">
            {options.map((name) => (
              <option key={name} value={name} />
            ))}
          </datalist>
          {personProblem && <span className="field-error">{personProblem}</span>}
          {!personProblem && departedWarn && <span className="form-warn">{departedWarn}</span>}
        </label>
        <label>
          날짜 *
          <input
            type="date"
            value={form.date}
            min={DATE_MIN}
            max={DATE_MAX}
            onChange={(e) => set("date", e.target.value)}
            required
            aria-invalid={dateIssue ? true : undefined}
          />
          {dateIssue && <span className="field-error">{dateIssue}</span>}
          {futureWarn && <span className="form-warn">{futureWarn}</span>}
        </label>
        <label>
          구분
          <select value={form.kind} onChange={(e) => set("kind", e.target.value)}>
            {(kinds.length === 0 || !form.kind) && <option value="">(구분 없음)</option>}
            {kinds.map((kind) => (
              <option key={kind} value={kind}>
                {kind === oldKind ? `${kind} (목록에 없음)` : kind}
              </option>
            ))}
          </select>
        </label>
        <label>
          다음 면담 (선택)
          {/* 하한은 면담일 다음 날 (TODO 216) — 면담일을 뒤로 옮겨 앞서게 되면 아래에 바로 알린다 */}
          <input
            type="date"
            className="meeting-next-date"
            value={form.next_date}
            min={form.date ? addDays(form.date, 1) : DATE_MIN}
            max={DATE_MAX}
            onChange={(e) => set("next_date", e.target.value)}
            aria-invalid={nextIssue ? true : undefined}
          />
          {nextIssue && <span className="field-error meeting-next-error">{nextIssue}</span>}
        </label>
      </div>
      <label>
        한 줄 요약 *
        <input
          value={form.summary}
          onChange={(e) => set("summary", e.target.value)}
          placeholder="예: 3분기 목표 점검 — 일정 지연 원인과 지원 필요 사항"
          required
        />
      </label>
      <div className="label-like meeting-followup-edit" ref={listRef}>
        <span>하기로 한 것 — 다음 면담에서 확인할 것 (줄마다 하나, {FOLLOWUP_MAX}줄까지)</span>
        {followups.map((item, index) => (
          <div key={index} className="meeting-followup-row">
            <input
              type="checkbox"
              checked={Boolean(item.done)}
              aria-label="완료"
              onChange={() =>
                setFollowups((prev) => prev.map((row, i) => (i === index ? { ...row, done: row.done ? null : today() } : row)))
              }
            />
            <input
              value={item.text}
              onChange={(e) => setFollowups((prev) => prev.map((row, i) => (i === index ? { ...row, text: e.target.value } : row)))}
              placeholder="예: 열처리 심화 과정 신청"
              aria-label={`하기로 한 것 ${index + 1}`}
              data-enter="add"
              onKeyDown={(event) => {
                // 목록에 줄을 더하는 칸 — Enter 는 제출이 아니라 다음 줄 (TODO 211 ⑥). 한글 조합 중 Enter 는 그대로 둔다
                if (event.key !== "Enter" || event.nativeEvent.isComposing || event.keyCode === 229) return;
                event.preventDefault();
                addLineAfter(index);
              }}
            />
            <button type="button" className="ghost small" onClick={() => setFollowups((prev) => prev.filter((_, i) => i !== index))}>
              ×
            </button>
          </div>
        ))}
        <button data-write type="button" className="ghost small" onClick={() => setFollowups((prev) => [...prev, { text: "", done: null }])}>
          + 줄 추가
        </button>
      </div>
      <label>
        이야기한 내용 (선택)
        <textarea value={form.body} onChange={(e) => set("body", e.target.value)} rows={5} />
      </label>
      {followupIssue && <p className="field-error">{followupIssue}</p>}
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button type="submit" disabled={!canSave}>
          {busy ? "저장 중…" : "저장"}
        </button>
        <button type="button" className="ghost" onClick={cancel}>
          취소
        </button>
      </div>
    </form>
  );
}
