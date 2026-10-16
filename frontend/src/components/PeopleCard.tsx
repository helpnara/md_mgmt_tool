import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { Person } from "../types";
import { splitPeople } from "../people";
import { useEditedUnsaved } from "../util";
import { DATE_MAX, DATE_MIN, LEFT_REASONS, dateProblem, isDeparted, isFuture, personNameProblem } from "../inputRules";
import NameDialog, { changeCounts } from "./NameDialog";
import { enterToSave } from "./enterSave";

/** 이름 창 — [넘기기] 또는 [다른 이름으로 통일] (TODO 214 D9 · F6) */
type Asking = { kind: "handover"; from: string; unfinished: number } | { kind: "rename"; from: string };

/**
 * 담당자 명부.
 *
 * 담당자가 그냥 문자열이라 `권경락` / `권 경락` / `권경락 책임` 이 따로 쌓인다.
 * **지금도 문제이고**, 나중에 계정을 붙일 때는 더 큰 문제가 된다.
 *
 * 사번 칸은 지금 비워 두는 것이 정상이다 — 로그인이 생길 때 채운다.
 * 계정 칸은 TODO 126 에서 뺐다 — 로그인을 *이름 + 사번* 으로 가기로 했기 때문이다.
 * 그때 칸을 새로 만들면 그 전 데이터가 비므로, 자리만 미리 잡아 둔다.
 */
export default function PeopleCard({ onChanged }: { onChanged: () => void }) {
  const [people, setPeople] = useState<Person[]>([]);
  // 마지막으로 불러온 명부 — 이것과 다르면 "저장 안 함" (TODO 211 ②). 여러 명의 떠난 날을 고치다 메뉴를 누르면 사라졌다
  const [saved, setSaved] = useState<Person[] | null>(null);
  const [unregistered, setUnregistered] = useState<{ name: string; used: number }[]>([]);
  const [busy, setBusy] = useState(false);
  // 스무 명이 넘으면 스크롤보다 이름 한 글자가 빠르다 (TODO 121)
  const [find, setFind] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [asking, setAsking] = useState<Asking | null>(null);

  const load = useCallback(() => {
    api
      .people()
      .then((data) => {
        setPeople(data.people);
        setSaved(data.people);
        setUnregistered(data.unregistered);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  useEffect(load, [load]);
  useEditedUnsaved("settings:people", people, saved, busy);

  const say = (message: string) => {
    setNotice(message);
    window.setTimeout(() => setNotice(null), 4000);
  };

  async function run(work: () => Promise<string>) {
    setBusy(true);
    setError(null);
    try {
      say(await work());
      load();
      onChanged();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const save = () =>
    run(async () => {
      await api.savePeople(people);
      return "명부를 저장했습니다.";
    });

  const add = (name: string) =>
    run(async () => {
      await api.addPerson(name);
      return `${name} 을(를) 명부에 넣었습니다.`;
    });

  // 브라우저 prompt() 대신 이름 창 (TODO 214 F6) — 새 이름을 검사하고, 결과를 종류별로 보인다
  const unify = (from: string) => setAsking({ kind: "rename", from });

  /** 이름 창이 서버에 보내고, 끝나면 명부를 다시 읽는다 */
  async function changeName(work: () => Promise<unknown>, head: string): Promise<string[]> {
    const result = await work();
    load();
    onChanged();
    return [head, `바꾼 것 — ${changeCounts(result)}`];
  }

  /** `"권경락,김현우"` 처럼 한 칸에 여러 명이 들어간 줄을 사람마다 한 줄로 푼다.
   *
   *  역량 이력에서 이름을 쉼표로 적었다가 그대로 명부에 들어간 적이 있다 (TODO 74).
   *  지금은 서버가 나눠 주지만, 그 전에 들어간 이름은 여기서 풀어야 한다. */
  const splitRow = (index: number) =>
    setPeople((prev) => {
      const target = prev[index];
      const names = splitPeople(target.name);
      const rest = prev.filter((_, i) => i !== index);
      const added = names
        .filter((name) => !rest.some((person) => person.name === name))
        .map((name) => ({ name, employee_id: "", left_on: "", left_reason: "" }));
      return [...rest, ...added].sort((a, b) => a.name.localeCompare(b.name, "ko"));
    });

  /** 담당자를 넘긴다 (TODO 122). 표기 통일과 달리 **명부는 그대로** 둔다. */
  const handover = (from: string, unfinished: number) => {
    if (unfinished === 0) return;
    setAsking({ kind: "handover", from, unfinished });
  };

  const glued = people.filter((person) => splitPeople(person.name).length > 1);
  const needle = find.trim();
  // 찾기는 **보여 주는 것만** 거른다 — 저장은 늘 명부 전체를 보낸다.
  const shown = needle
    ? people.filter((person) => person.name.includes(needle) || (person.employee_id ?? "").includes(needle))
    : people;
  // 떠난 날이 오늘 이후면 아직 있는 사람 — 그날부터 떠난 사람으로 본다 (TODO 214 D8)
  const leftCount = people.filter((person) => isDeparted(person)).length;
  const leavingCount = people.filter((person) => person.left_on && !isDeparted(person)).length;
  const activeNames = people.filter((person) => person.name.trim() && !isDeparted(person)).map((person) => person.name.trim());
  const departedSet = new Set(people.filter((person) => isDeparted(person)).map((person) => person.name.trim()));

  const update = (index: number, key: keyof Person, value: string) =>
    setPeople((prev) =>
      prev.map((p, i) =>
        i !== index
          ? p
          : // 떠난 날을 지우면 사유도 지운다 — 예전에는 꺼진 칸에 사유가 남아 저장됐다 (TODO 214 D8)
            key === "left_on" && !value
            ? { ...p, left_on: "", left_reason: "" }
            : { ...p, [key]: value },
      ),
    );

  // 저장 전에 칸 옆에서 먼저 (TODO 214 D10 · U2) — 이름 규칙 · 같은 이름 · 같은 사번 · 떠난 날 형식
  const nameCount = new Map<string, number>();
  const idCount = new Map<string, number>();
  for (const person of people) {
    const name = person.name.trim();
    const id = (person.employee_id ?? "").trim();
    if (name) nameCount.set(name, (nameCount.get(name) ?? 0) + 1);
    if (id) idCount.set(id, (idCount.get(id) ?? 0) + 1);
  }
  const rowProblems = people.map((person) => ({
    name:
      personNameProblem(person.name) ??
      ((nameCount.get(person.name.trim()) ?? 0) > 1 ? "같은 이름이 명부에 둘 있습니다." : null),
    id: (idCount.get((person.employee_id ?? "").trim()) ?? 0) > 1 ? "같은 사번이 둘 있습니다." : null,
    left: dateProblem(person.left_on, "떠난 날"),
  }));
  const problemCount = rowProblems.filter((row) => row.name || row.id || row.left).length;
  const dupIds = [...idCount.entries()].filter(([, count]) => count > 1).map(([id]) => id);

  return (
    <div className="card people-card" onKeyDown={enterToSave(() => void save(), !busy && problemCount === 0)}>
      <div className="card-head">
        <h2>
          담당자 명부 {people.length}명
          {leftCount > 0 && <span className="muted"> · 떠난 사람 {leftCount}명</span>}
          {leavingCount > 0 && <span className="muted"> · 떠날 예정 {leavingCount}명</span>}
        </h2>
        <button
          className="ghost"
          onClick={() =>
            setPeople((prev) => [
              ...prev,
              { name: "", employee_id: "", left_on: "", left_reason: "" },
            ])
          }
        >
          + 사람 추가
        </button>
      </div>
      <p className="hint">
        과제의 담당자 자동완성이 이 목록을 씁니다. 명부에 없는 이름도 <b>쓸 수는 있고</b>,
        아래 <b>명부에 없는 이름</b>에 모여 보입니다.
        <br />
        사번 칸은 지금 비워 두어도 됩니다 — 나중에 로그인이 생기면 이름과 사번으로 확인합니다.
        <br />
        전배·퇴사한 사람은 <b>빼지 말고 [떠난 날]을 적어 주세요.</b> 지우면 그 사람이 지난해 한 일이
        &ldquo;명부에 없는 이름&rdquo;이 되어 오타와 뒤섞입니다. 날짜를 적으면 자동완성에서 빠지고,
        아직 담당으로 남은 과제가 있으면 <b>홈이 대체 담당자를 정하라고 알려 줍니다.</b> 앞으로 떠날 날을 적어 두면
        <b>그날부터</b> 떠난 사람으로 봅니다.
        <br />
        이름은 한 칸에 한 사람 — 쉼표 · <code>/ \</code> 없이 40자까지. 사번은 비워 두거나, 적으면 사람마다 달라야 합니다.
      </p>

      {people.length > 8 && (
        <label className="people-find">
          찾기
          <input
            type="search"
            value={find}
            onChange={(event) => setFind(event.target.value)}
            placeholder="이름·사번"
          />
          {needle && <span className="muted">{shown.length}명</span>}
        </label>
      )}

      {/* 인원이 늘어도 카드 키가 자라지 않게 목록 안에서만 스크롤한다 (TODO 121) */}
      {people.length > 0 && (
        <div className="people-scroll">
        <table className="people-table">
          {/* 칸 폭은 `nth-child` 번호가 아니라 **이름**으로 잡는다 (TODO 134).
              126 에서 계정 칸을 빼자 번호가 한 칸씩 밀려, 날짜 칸이 60px 로 눌리면서
              표가 카드 밖으로 밀려나 맨 오른쪽 단추가 안 보였다. 칸이 늘거나 줄어도
              이름표를 따라가면 다시는 밀리지 않는다. */}
          <colgroup>
            <col className="col-name" />
            <col className="col-id" />
            <col className="col-used" />
            <col className="col-left" />
            <col className="col-act" />
          </colgroup>
          <thead>
            <tr>
              <th>이름</th>
              <th>사번</th>
              <th>과제</th>
              <th>떠난 날</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {shown.map((person) => {
              const index = people.indexOf(person);
              return (
              <tr
                key={index}
                className={isDeparted(person) ? "person-left" : person.left_on ? "person-leaving" : undefined}
                data-name={person.name}
              >
                <td>
                  <input
                    value={person.name}
                    onChange={(e) => update(index, "name", e.target.value)}
                    aria-invalid={rowProblems[index]?.name ? true : undefined}
                    title={rowProblems[index]?.name ?? undefined}
                  />
                  {rowProblems[index]?.name && <span className="field-error person-name-error">{rowProblems[index].name}</span>}
                </td>
                <td>
                  <input
                    value={person.employee_id}
                    onChange={(e) => update(index, "employee_id", e.target.value)}
                    placeholder="나중에"
                    aria-invalid={rowProblems[index]?.id ? true : undefined}
                    title={rowProblems[index]?.id ?? undefined}
                  />
                  {rowProblems[index]?.id && <span className="field-error person-id-error">{rowProblems[index].id}</span>}
                </td>
                <td className="muted">
                  {person.used ?? 0}건
                  {/* 좁은 칸이라 아랫줄로 내린다 — 가운뎃점으로 이으면 줄 사이에서 끊긴다 */}
                  {(person.unfinished ?? 0) > 0 && person.left_on && isDeparted(person) && (
                    <span className="warn-text">남은 {person.unfinished}건</span>
                  )}
                </td>
                <td className="person-left-cell">
                  {/* 나란히 놓는 일은 안쪽 div 가 한다 — `<td>` 에 display:flex 를 걸면
                      그 칸이 표의 칸 계산에서 빠져 옆 칸과 겹쳐 그려진다 (TODO 134). */}
                  <div className="cell-row">
                    <input
                      type="date"
                      value={person.left_on ?? ""}
                      min={DATE_MIN}
                      max={DATE_MAX}
                      onChange={(e) => update(index, "left_on", e.target.value)}
                      title="전배·퇴사한 날. 비워 두면 지금 있는 사람입니다. 앞날을 적으면 그날부터 떠난 사람으로 봅니다."
                      aria-invalid={rowProblems[index]?.left ? true : undefined}
                    />
                    {/* 떠난 날이 없으면 사유도 없다 — 꺼진 칸에 값이 남지 않게 빈 값으로 보인다 (D8) */}
                    <select
                      value={person.left_on ? person.left_reason ?? "" : ""}
                      disabled={!person.left_on}
                      onChange={(e) => update(index, "left_reason", e.target.value)}
                    >
                      <option value="">사유</option>
                      {LEFT_REASONS.map((reason) => (
                        <option key={reason} value={reason}>
                          {reason}
                        </option>
                      ))}
                    </select>
                  </div>
                  {rowProblems[index]?.left && <span className="field-error">{rowProblems[index].left}</span>}
                  {person.left_on && isFuture(person.left_on) && !rowProblems[index]?.left && (
                    <span className="hint person-leaving-hint">그날부터 떠난 사람으로 봅니다</span>
                  )}
                </td>
                <td className="person-actions">
                  <div className="cell-row">
                  {person.left_on && (person.unfinished ?? 0) > 0 && (
                    <button
                      className="ghost small"
                      disabled={busy}
                      title="끝나지 않은 과제만 다른 사람에게 넘깁니다."
                      onClick={() => handover(person.name, person.unfinished ?? 0)}
                    >
                      넘기기
                    </button>
                  )}
                  <button data-write
                    className="ghost small danger"
                    onClick={() => setPeople((prev) => prev.filter((_, i) => i !== index))}
                  >
                    빼기
                  </button>
                  </div>
                </td>
              </tr>
              );
            })}
          </tbody>
        </table>
        </div>
      )}

      {glued.length > 0 && (
        <div className="unregistered">
          <p className="hint warn-text">
            <b>한 칸에 여러 이름이 들어간 줄 {glued.length}건</b> — 쉼표로 여러 명을 적었을 때
            생깁니다. 이대로 두면 사람별 집계에 <b>없는 사람</b>으로 남습니다.
          </p>
          <ul className="trash-list">
            {glued.map((person) => (
              <li key={person.name}>
                <span className="trash-label">{person.name}</span>
                <span className="muted trash-when">→ {splitPeople(person.name).join(" · ")}</span>
                <button data-write
                  className="ghost small"
                  onClick={() => splitRow(people.indexOf(person))}
                >
                  사람별로 나누기
                </button>
              </li>
            ))}
          </ul>
          <p className="hint">나눈 뒤 아래 <b>[명부 저장]</b> 을 눌러야 반영됩니다.</p>
        </div>
      )}

      {unregistered.length > 0 && (
        <div className="unregistered">
          <p className="hint warn-text">
            <b>명부에 없는 이름 {unregistered.length}건</b> — 오타이거나, 명부에 넣어야 할 사람입니다.
          </p>
          <ul className="trash-list">
            {unregistered.map((item) => (
              <li key={item.name}>
                <span className="trash-label">{item.name}</span>
                <span className="muted trash-when">과제 {item.used}건</span>
                <button className="ghost small" disabled={busy} onClick={() => void add(item.name)}>
                  명부에 넣기
                </button>
                <button className="ghost small" disabled={busy} onClick={() => unify(item.name)}>
                  다른 이름으로 통일
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {dupIds.length > 0 && (
        <p className="field-error people-dup-ids">같은 사번이 둘 이상입니다: {dupIds.join(", ")} — 사람마다 다른 사번이어야 저장됩니다.</p>
      )}
      {notice && <p className="hint notice">{notice}</p>}
      {error && <p className="form-error">{error}</p>}
      {asking && (
        <NameDialog
          title={asking.kind === "handover" ? `"${asking.from}" 의 일을 누구에게 넘길까요?` : `"${asking.from}" 을(를) 어떤 이름으로 통일할까요?`}
          from={asking.from}
          initial={asking.kind === "rename" ? asking.from : ""}
          label={asking.kind === "handover" ? "받을 사람" : "새 이름"}
          confirmLabel={asking.kind === "handover" ? "넘기기" : "통일하기"}
          roster={activeNames}
          departed={departedSet}
          warnUnknown={asking.kind === "handover"}
          message={
            asking.kind === "handover" ? (
              <>
                <b>끝나지 않은 과제 {asking.unfinished}건</b>의 담당을 넘깁니다. 함께 바뀐 기록(유관부서 담당 · 접수 과제리더 등)은
                넘긴 뒤 종류별로 보입니다. 끝난 과제는 그대로 둡니다 — 그때 그 사람이 한 것은 사실이기 때문입니다. 명부에서 이름이 사라지지는 않습니다.
              </>
            ) : (
              <>
                과제 담당 · 유관부서 담당 · 역량 기록 · 면담 기록 · 접수 과제리더의 표기를 함께 바꾸고, 명부의 이름도 바꿉니다.
                작성자는 그때의 사실이라 그대로 둡니다.
              </>
            )
          }
          onSubmit={(to) =>
            asking.kind === "handover"
              ? changeName(() => api.handover(asking.from, to), `"${asking.from}" 의 일을 "${to}" 에게 넘겼습니다.`)
              : changeName(() => api.renameOwner(asking.from, to), `"${asking.from}" 을(를) "${to}" 으로 바꿨습니다.`)
          }
          onClose={() => setAsking(null)}
        />
      )}
      <div className="form-actions">
        {problemCount > 0 && <span className="form-warn">고칠 칸 {problemCount}줄 — 칸 옆의 안내를 보세요.</span>}
        <button disabled={busy || problemCount > 0} onClick={() => void save()}>
          {busy ? "저장 중…" : "명부 저장"}
        </button>
      </div>
    </div>
  );
}
