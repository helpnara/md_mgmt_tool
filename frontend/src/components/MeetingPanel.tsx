import { useEffect, useState } from "react";
import { api } from "../api";
import type { Meeting, MeetingFollowup, MeetingListing, Meta } from "../types";
import { attempt, notifyError } from "../notify";
import { useFormUnsaved } from "../unsaved";
import { todayIso } from "../util";

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

  const load = () =>
    api
      .meetings(person || undefined)
      .then(setData)
      .catch((err: Error) => notifyError(err.message));
  useEffect(() => {
    setAdding(false);
    setEditing(null);
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [person]);

  const changed = () => {
    void load();
    onChanged();
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
        <button onClick={() => { setAdding((value) => !value); setEditing(null); }} className={adding ? "ghost on" : undefined}>
          면담 추가
        </button>
      </div>
      <p className="hint">
        무엇을 이야기했고 <b>무엇을 하기로 했는지</b> 남깁니다. 하기로 한 것은 [완료]로 닫을 때까지 보입니다. 이 기록은{" "}
        <b>통합 검색 · AI 요약 · 내보내기에 들어가지 않고</b>, 역량 이력 수에도 세지 않습니다.
      </p>

      {adding && (
        <MeetingForm
          meta={meta}
          people={people}
          initial={{ person, date: today() }}
          onClose={() => setAdding(false)}
          onSaved={() => { setAdding(false); changed(); }}
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
                <button
                  className={editing === meeting.id ? "ghost small on" : "ghost small"}
                  onClick={() => { setEditing(editing === meeting.id ? null : meeting.id); setAdding(false); }}
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
                  onClose={() => setEditing(null)}
                  onSaved={() => { setEditing(null); changed(); }}
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
  onClose,
  onSaved,
}: {
  meta: Meta;
  people: string[];
  initial: Partial<Meeting>;
  onClose: () => void;
  onSaved: () => void;
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
  const set = (key: keyof typeof form, value: string) => setForm((prev) => ({ ...prev, [key]: value }));
  const kinds = form.kind && !meta.meeting_kinds.includes(form.kind) ? [...meta.meeting_kinds, form.kind] : meta.meeting_kinds;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const payload = {
      ...form,
      kind: form.kind || null,
      next_date: form.next_date || null,
      followups: followups.filter((item) => item.text.trim()),
    };
    try {
      if (initial.id) await api.updateMeeting(initial.id, payload);
      else await api.createMeeting(payload);
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="meeting-form" onSubmit={submit}>
      <div className="form-row">
        <label>
          누구와
          <input list="meeting-people" value={form.person} onChange={(e) => set("person", e.target.value)} required />
          <datalist id="meeting-people">
            {people.map((name) => (
              <option key={name} value={name} />
            ))}
          </datalist>
        </label>
        <label>
          날짜
          <input type="date" value={form.date} onChange={(e) => set("date", e.target.value)} required />
        </label>
        <label>
          구분
          <select value={form.kind} onChange={(e) => set("kind", e.target.value)}>
            {kinds.map((kind) => (
              <option key={kind} value={kind}>
                {kind}
              </option>
            ))}
          </select>
        </label>
        <label>
          다음 면담 (선택)
          <input type="date" value={form.next_date} onChange={(e) => set("next_date", e.target.value)} />
        </label>
      </div>
      <label>
        한 줄 요약
        <input
          value={form.summary}
          onChange={(e) => set("summary", e.target.value)}
          placeholder="예: 3분기 목표 점검 — 일정 지연 원인과 지원 필요 사항"
          required
        />
      </label>
      <div className="label-like meeting-followup-edit">
        <span>하기로 한 것 — 다음 면담에서 확인할 것 (줄마다 하나)</span>
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
            />
            <button type="button" className="ghost small" onClick={() => setFollowups((prev) => prev.filter((_, i) => i !== index))}>
              ×
            </button>
          </div>
        ))}
        <button type="button" className="ghost small" onClick={() => setFollowups((prev) => [...prev, { text: "", done: null }])}>
          + 줄 추가
        </button>
      </div>
      <label>
        이야기한 내용 (선택)
        <textarea value={form.body} onChange={(e) => set("body", e.target.value)} rows={5} />
      </label>
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button type="submit" disabled={busy}>
          {busy ? "저장 중…" : "저장"}
        </button>
        <button type="button" className="ghost" onClick={onClose}>
          취소
        </button>
      </div>
    </form>
  );
}
