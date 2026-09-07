import { useState } from "react";
import { api } from "../api";
import type { Activity, Meta } from "../types";
import { splitPeople } from "../people";

/**
 * 역량 이력 한 건을 쓰는 자리 (TODO 72 · 74).
 *
 * 필수는 **누가 · 언제 · 무엇을** 셋뿐이다. 나머지는 비워 두어도 된다 —
 * 채워야 할 칸이 많으면 기록 자체를 안 하게 되고, 그러면 화면이 무의미해진다.
 * 다만 **얻은 것 한 줄**은 눈에 띄게 둔다. 면담에서 실제로 읽는 칸이 그것이다.
 *
 * **여러 명을 한 번에 넣을 수 있다.** 한 교육에 셋이 갔으면 이름을 쉼표로 이어 적으면 되고,
 * 저장하면 **사람마다 한 건씩** 만들어진다. 나누는 일은 서버가 한다 — 화면만 고치면
 * 다른 길로 같은 사고가 다시 난다. 여기서는 **무엇이 만들어질지 미리 보여 주는 것**이 몫이다.
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
  onSaved: (message: string) => void;
}) {
  const editing = activity !== null;
  const today = new Date().toISOString().slice(0, 10);
  const [person, setPerson] = useState(activity?.person ?? "");
  const [date, setDate] = useState(activity?.date ?? today);
  const [endDate, setEndDate] = useState(activity?.end_date ?? "");
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

  const picked = splitPeople(person);
  // 예전에 한 칸에 여러 이름이 들어간 줄은 칩으로 내주지 않는다 —
  // 누르면 그 붙은 이름이 또 들어간다 (TODO 74).
  const roster = meta.people.filter((name) => splitPeople(name).length === 1);

  /** 명부에서 이름을 눌러 넣고 뺀다. 고칠 때는 한 사람만 들어간다. */
  function toggle(name: string) {
    if (editing) {
      setPerson(person === name ? "" : name);
      return;
    }
    setPerson(
      picked.includes(name)
        ? picked.filter((item) => item !== name).join(", ")
        : [...picked, name].join(", "),
    );
  }

  async function save() {
    setBusy(true);
    setError(null);
    // 빈 칸은 null 로 보낸다. "" 를 보내면 0 으로 굳어 "안 적었다"와 구분되지 않는다.
    const payload = {
      person: person.trim(),
      date,
      end_date: endDate.trim() || null,
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
      if (activity) {
        await api.updateActivity(activity.id, payload);
        onSaved("기록을 고쳤습니다.");
      } else {
        const result = await api.createActivity(payload);
        onSaved(
          result.count > 1
            ? `${result.count}명의 기록으로 나눠 저장했습니다.`
            : "기록을 저장했습니다.",
        );
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card activity-form">
      <div className="card-head">
        <h2>{editing ? "기록 수정" : "기록 추가"}</h2>
        <button className="ghost small" onClick={onClose}>
          닫기
        </button>
      </div>

      <label className="stack-label">
        누가 *
        <input
          value={person}
          onChange={(event) => setPerson(event.target.value)}
          placeholder={editing ? "예: 권경락" : "예: 권경락, 김현우 — 쉼표로 여러 명"}
        />
      </label>
      {roster.length > 0 && (
        <div className="tag-suggest">
          <span className="muted">명부</span>
          {roster.map((name) => (
            <button
              key={name}
              type="button"
              className={picked.includes(name) ? "tag-pick on" : "tag-pick"}
              onClick={() => toggle(name)}
            >
              {name}
            </button>
          ))}
        </div>
      )}
      {editing ? (
        <p className="hint">
          한 기록은 한 사람의 것입니다. 여러 명은 <b>[기록 추가]</b> 에서 한 번에 넣으세요.
        </p>
      ) : (
        <p className="hint">
          쉼표(<code>,</code>)나 세미콜론(<code>;</code>)으로 여러 명을 적을 수 있습니다.
          {picked.length > 1 ? (
            <>
              {" "}저장하면 <b>{picked.join(" · ")}</b> 앞으로 <b>{picked.length}건</b>이 각각 만들어집니다.
            </>
          ) : (
            " 저장할 때 사람마다 한 건씩 나뉘어 기록됩니다."
          )}
        </p>
      )}

      <div className="form-row">
        <label>
          언제 *
          <input type="date" value={date} onChange={(event) => setDate(event.target.value)} />
        </label>
        <label>
          종료일 (여러 날이면)
          <input
            type="date"
            value={endDate}
            min={date}
            onChange={(event) => setEndDate(event.target.value)}
          />
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
        <label className="grow">
          무엇 *
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="예: 열처리 공정 심화 과정"
          />
        </label>
      </div>
      <p className="hint">하루짜리 교육이면 종료일은 비워 두세요.</p>

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
            placeholder="비워도 됨"
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
            placeholder="비워도 됨"
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
        {!editing && picked.length > 1 && " 여러 명으로 나뉜 기록에는 이 내용이 똑같이 들어갑니다."}
      </p>

      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button className="ghost" onClick={onClose}>
          취소
        </button>
        <button disabled={busy || picked.length === 0 || !title.trim()} onClick={() => void save()}>
          {busy
            ? "저장 중…"
            : !editing && picked.length > 1
              ? `${picked.length}건 저장`
              : "저장"}
        </button>
      </div>
    </div>
  );
}
