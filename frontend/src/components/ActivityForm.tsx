import { useState } from "react";
import { api } from "../api";
import type { Activity, Meta } from "../types";

/**
 * 역량 이력 한 건을 쓰는 자리 (TODO 72).
 *
 * 필수는 **누가 · 언제 · 무엇을** 셋뿐이다. 나머지는 비워 두어도 된다 —
 * 채워야 할 칸이 많으면 기록 자체를 안 하게 되고, 그러면 화면이 무의미해진다.
 * 다만 **얻은 것 한 줄**은 눈에 띄게 둔다. 면담에서 실제로 읽는 칸이 그것이다.
 */
export default function ActivityForm({
  meta,
  activity,
  onClose,
  onSaved,
}: {
  meta: Meta;
  activity: Activity | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const today = new Date().toISOString().slice(0, 10);
  const [person, setPerson] = useState(activity?.person ?? meta.people[0] ?? "");
  const [date, setDate] = useState(activity?.date ?? today);
  const [kind, setKind] = useState(activity?.kind ?? meta.activity_kinds[0]?.key ?? "education");
  const [title, setTitle] = useState(activity?.title ?? "");
  const [host, setHost] = useState(activity?.host ?? "");
  const [place, setPlace] = useState(activity?.place ?? "");
  const [hours, setHours] = useState(activity?.hours?.toString() ?? "");
  const [cost, setCost] = useState(activity?.cost?.toString() ?? "");
  const [takeaway, setTakeaway] = useState(activity?.takeaway ?? "");
  const [link, setLink] = useState(activity?.link ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setBusy(true);
    setError(null);
    // 빈 칸은 보내지 않는다. "" 를 보내면 0 으로 굳어 버려 "안 적었다"와 구분되지 않는다.
    const payload = {
      person: person.trim(),
      date,
      kind,
      title: title.trim(),
      host: host.trim() || null,
      place: place.trim() || null,
      hours: hours.trim() === "" ? null : hours.trim(),
      cost: cost.trim() === "" ? null : cost.trim(),
      takeaway: takeaway.trim() || null,
      link: link.trim() || null,
    } as unknown as Partial<Activity>;
    try {
      if (activity) await api.updateActivity(activity.id, payload);
      else await api.createActivity(payload);
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card activity-form">
      <div className="card-head">
        <h2>{activity ? "기록 수정" : "기록 추가"}</h2>
        <button className="ghost small" onClick={onClose}>
          닫기
        </button>
      </div>

      <div className="form-row">
        <label className="grow">
          누가 *
          <input
            list="activity-people"
            value={person}
            onChange={(event) => setPerson(event.target.value)}
            placeholder="예: 권경락"
          />
          <datalist id="activity-people">
            {meta.people.map((name) => (
              <option key={name} value={name} />
            ))}
          </datalist>
        </label>
        <label>
          언제 *
          <input type="date" value={date} onChange={(event) => setDate(event.target.value)} />
        </label>
        <label>
          구분
          <select value={kind} onChange={(event) => setKind(event.target.value)}>
            {meta.activity_kinds.map((item) => (
              <option key={item.key} value={item.key}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="form-row">
        <label className="grow">
          무엇 *
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="예: 열처리 공정 심화 과정"
          />
        </label>
      </div>

      <div className="form-row">
        <label className="grow">
          주최
          <input value={host} onChange={(event) => setHost(event.target.value)} placeholder="예: 한국금속학회" />
        </label>
        <label className="grow">
          장소
          <input value={place} onChange={(event) => setPlace(event.target.value)} placeholder="예: 서울 코엑스" />
        </label>
      </div>

      <div className="form-row">
        <label>
          시간 (선택)
          <input
            type="number"
            min="0"
            step="0.5"
            value={hours}
            onChange={(event) => setHours(event.target.value)}
            placeholder="비워 두어도 됩니다"
          />
        </label>
        <label>
          비용 (선택, 원)
          <input
            type="number"
            min="0"
            step="1000"
            value={cost}
            onChange={(event) => setCost(event.target.value)}
            placeholder="비워 두어도 됩니다"
          />
        </label>
        <label className="grow">
          자료 위치 (선택)
          <input
            value={link}
            onChange={(event) => setLink(event.target.value)}
            placeholder="수료증·발표자료가 있는 사내 공유 폴더 주소"
          />
        </label>
      </div>

      <label className="stack-label">
        얻은 것 — 한 줄로
        <input
          value={takeaway}
          onChange={(event) => setTakeaway(event.target.value)}
          placeholder="예: 소입 조건 설계 기준을 정리해 옴. 우리 라인에 바로 적용 가능"
        />
      </label>
      <p className="hint">
        면담에서 실제로 읽게 되는 칸입니다. 한 줄이면 충분하고, 자세한 내용은 저장한 뒤
        문서 본문에 이어 쓰면 됩니다.
      </p>

      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button className="ghost" onClick={onClose}>
          취소
        </button>
        <button disabled={busy || !person.trim() || !title.trim()} onClick={() => void save()}>
          {busy ? "저장 중…" : "저장"}
        </button>
      </div>
    </div>
  );
}
