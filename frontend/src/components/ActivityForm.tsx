import { useState } from "react";
import { api } from "../api";
import type { Activity, Meta } from "../types";
import { splitPeople } from "../people";
import { useFormUnsaved } from "../unsaved";
import { confirmDiscard, dateOrderProblem, isPlainEnter, todayIso } from "../util";
import { DATE_MIN, confirmPeople, dateProblem as dayProblem, daySpan, numberProblem, personNameProblem, warningList } from "../inputRules";
import { departedNames, freshRoster } from "./roster";

/** 비용 상한 (TODO 214 F14) — 서버와 같은 1조 원 */
const COST_MAX = 1e12;

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
  const today = todayIso(); // 이 PC 의 오늘 — UTC 로 하면 오전 9시 전엔 어제다 (TODO 207)
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
  // 쓰다가 떠나면 묻는다 (TODO 162)
  const snapshot = { person, date, endDate, kind, title, host, place, hours, cost, takeaway, link };
  useFormUnsaved(`activity-form:${activity?.id ?? "new"}`, snapshot, busy);
  const [initialSnapshot] = useState(() => JSON.stringify(snapshot));
  const dirty = JSON.stringify(snapshot) !== initialSnapshot;
  // [취소] · [닫기] · Esc — 고친 것이 있으면 버릴지 묻는다 (TODO 211 ①)
  const close = () => {
    if (busy) return;
    if (confirmDiscard(dirty)) onClose();
  };
  // 날짜 화면 검사 (TODO 212) — 언제는 필수 · 종료일이 앞서면 안 된다(서버 422)
  const missingDate = !date;
  // 역량 기록은 지나간 이력이다 — 미래 날짜는 막는다 (TODO 214 D5). 2000~2100 년 밖도
  const futureText = "역량 기록은 지난 일만 적습니다 — 오늘 뒤의 날짜는 저장할 수 없습니다.";
  const startProblem = dayProblem(date, "날짜") ?? (date > today ? futureText : null);
  const dateProblem =
    dayProblem(endDate, "종료일") ?? (endDate > today ? futureText : null) ?? dateOrderProblem(date, endDate, "시작일", "종료일");

  // 시간 · 비용 (TODO 214 F14 · U4) — `<form>` 밖이라 min · step 이 막지 못한다. 시간은 하루 24시간 × 날수까지
  const span = daySpan(date, endDate);
  const hoursProblem =
    numberProblem(hours, { min: 0, optional: true }) ??
    (hours.trim() && Number(hours) > 24 * span ? `시간은 ${span}일 × 24시간 = ${24 * span}시간까지입니다.` : null);
  const costProblem = numberProblem(cost, { min: 0, max: COST_MAX, optional: true });

  const picked = splitPeople(person);
  // 예전에 한 칸에 여러 이름이 들어간 줄은 칩으로 내주지 않는다 —
  // 누르면 그 붙은 이름이 또 들어간다 (TODO 74).
  // 떠난 사람도 지난 기록의 주인이라 숨기지 않고 "(떠남)" 딱지로 뒤에 둔다 (TODO 214 D7)
  const departed = departedNames(meta);
  const roster = meta.people
    .filter((name) => splitPeople(name).length === 1)
    .sort((a, b) => Number(departed.has(a)) - Number(departed.has(b)));
  const nameProblem = picked.map((name) => personNameProblem(name)).find(Boolean) ?? null;
  const pickedDeparted = picked.filter((name) => departed.has(name));
  const originalPerson = activity?.person ?? "";

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

  const canSave =
    !busy &&
    picked.length > 0 &&
    Boolean(title.trim()) &&
    !missingDate &&
    !startProblem &&
    !dateProblem &&
    !hoursProblem &&
    !costProblem &&
    !nameProblem;

  async function save() {
    if (!canSave) return;
    setBusy(true);
    setError(null);
    // 명부에 없는 이름은 묻는다 — 예전에는 오타가 명부에 조용히 들어갔다 (TODO 214 D6). 고칠 때 사람이 그대로면 묻지 않는다
    const asking = editing && picked.length === 1 && picked[0] === originalPerson.trim() ? [] : picked;
    if (asking.length > 0) {
      try {
        if (!(await confirmPeople(asking, await freshRoster(meta), api.addPerson, "역량 기록 대상"))) {
          setBusy(false);
          return;
        }
      } catch (err) {
        setError((err as Error).message);
        setBusy(false);
        return;
      }
    }
    // 빈 칸은 null 로 보낸다. "" 를 보내면 0 으로 굳어 "안 적었다"와 구분되지 않는다.
    const payload = {
      person: person.trim(),
      date,
      end_date: endDate.trim() || null,
      kind,
      title: title.trim(),
      host: host.trim() || null,
      place: place.trim() || null,
      hours: hours.trim() === "" ? null : Number(hours.trim()),
      cost: cost.trim() === "" ? null : Number(cost.trim().replace(/,/g, "")),
      takeaway: takeaway.trim() || null,
      link: link.trim() || null,
    } as unknown as Partial<Activity>;
    try {
      if (activity) {
        const result = await api.updateActivity(activity.id, payload);
        onSaved(["기록을 고쳤습니다.", ...warningList(result)].join(" "));
      } else {
        const result = await api.createActivity(payload);
        // 서버가 알린 것(명부 · 떠난 사람 등)을 함께 (TODO 214)
        onSaved(
          [
            result.count > 1 ? `${result.count}명의 기록으로 나눠 저장했습니다.` : "기록을 저장했습니다.",
            ...warningList(result),
          ].join(" "),
        );
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="card activity-form"
      onKeyDown={(event) => {
        // Enter 규칙 (TODO 211 ⑥) — 한 줄 칸에서 Enter = 저장(필수 칸이 차 있을 때). Esc = 닫기(고쳤으면 묻는다)
        if (event.key === "Escape" && !event.defaultPrevented) {
          event.preventDefault();
          close();
        } else if (isPlainEnter(event)) {
          event.preventDefault();
          void save();
        }
      }}
    >
      <div className="card-head">
        <h2>{editing ? "기록 수정" : "기록 추가"}</h2>
        <button className="ghost small" onClick={close}>
          닫기
        </button>
      </div>

      <label className="stack-label">
        누가 *
        <input
          value={person}
          onChange={(event) => setPerson(event.target.value)}
          placeholder={editing ? "예: 권경락" : "예: 권경락, 김현우 — 쉼표로 여러 명"}
          aria-invalid={nameProblem ? true : undefined}
        />
        {nameProblem && <span className="field-error">{nameProblem}</span>}
        {!nameProblem && pickedDeparted.length > 0 && (
          <span className="form-warn activity-departed-warn">
            {pickedDeparted.join(", ")} — 명부에서 떠난 사람입니다. 지난 기록이면 그대로 저장해도 됩니다.
          </span>
        )}
      </label>
      {roster.length > 0 && (
        <div className="tag-suggest">
          <span className="muted">명부</span>
          {roster.map((name) => (
            <button
              key={name}
              type="button"
              className={[picked.includes(name) ? "tag-pick on" : "tag-pick", departed.has(name) ? "departed" : ""].join(" ").trim()}
              onClick={() => toggle(name)}
              title={departed.has(name) ? "명부에서 떠난 사람 — 지난 기록에만" : undefined}
            >
              {name}
              {departed.has(name) && <span className="departed-tag"> (떠남)</span>}
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
          쉼표(<code>,</code>)로 여러 명을 적을 수 있습니다.
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
          <input
            type="date"
            value={date}
            min={DATE_MIN}
            max={today}
            onChange={(event) => setDate(event.target.value)}
            required
            aria-invalid={missingDate || startProblem ? true : undefined}
          />
          {missingDate && <span className="form-warn date-warn">날짜를 적어 주세요.</span>}
          {startProblem && <span className="field-error date-warn activity-future">{startProblem}</span>}
        </label>
        <label>
          종료일 (여러 날이면)
          <input
            type="date"
            value={endDate}
            min={date || DATE_MIN}
            max={today}
            onChange={(event) => setEndDate(event.target.value)}
            aria-invalid={dateProblem ? true : undefined}
          />
          {dateProblem && <span className="form-warn date-warn">{dateProblem}</span>}
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
            max={24 * span}
            step="0.5"
            value={hours}
            onChange={(event) => setHours(event.target.value)}
            placeholder="비워도 됨"
            aria-invalid={hoursProblem ? true : undefined}
          />
          {hoursProblem && <span className="field-error">{hoursProblem}</span>}
        </label>
        <label>
          비용 (선택, 원)
          <input
            type="number"
            min="0"
            max={COST_MAX}
            step="1000"
            value={cost}
            onChange={(event) => setCost(event.target.value)}
            placeholder="비워도 됨"
            aria-invalid={costProblem ? true : undefined}
          />
          {costProblem && <span className="field-error">{costProblem}</span>}
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

      {/* 서버가 거절한 사유는 단추 바로 위에 (TODO 205) */}
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="form-actions">
        <button className="ghost" onClick={close}>
          취소
        </button>
        <button disabled={!canSave} onClick={() => void save()}>
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
