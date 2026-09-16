import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { Person } from "../types";
import { splitPeople } from "../people";

/**
 * 담당자 명부.
 *
 * 담당자가 그냥 문자열이라 `권경락` / `권 경락` / `권경락 책임` 이 따로 쌓인다.
 * **지금도 문제이고**, 나중에 계정을 붙일 때는 더 큰 문제가 된다.
 *
 * 사번·계정 칸은 지금 비워 두는 것이 정상이다 — 로그인이 생길 때 채운다.
 * 그때 칸을 새로 만들면 그 전 데이터가 비므로, 자리만 미리 잡아 둔다.
 */
export default function PeopleCard({ onChanged }: { onChanged: () => void }) {
  const [people, setPeople] = useState<Person[]>([]);
  const [unregistered, setUnregistered] = useState<{ name: string; used: number }[]>([]);
  const [busy, setBusy] = useState(false);
  // 스무 명이 넘으면 스크롤보다 이름 한 글자가 빠르다 (TODO 121)
  const [find, setFind] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .people()
      .then((data) => {
        setPeople(data.people);
        setUnregistered(data.unregistered);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  useEffect(load, [load]);

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

  const unify = (from: string) => {
    const to = window.prompt(`"${from}" 을(를) 어떤 이름으로 통일할까요?`, from);
    if (!to || to.trim() === from) return;
    if (!window.confirm(`"${from}" 을(를) "${to.trim()}" 으로 바꿉니다. 과제 파일까지 함께 바뀝니다.`)) return;
    void run(async () => {
      const result = await api.renameOwner(from, to.trim());
      return `과제 ${result.count}건의 표기를 "${to.trim()}" 으로 바꿨습니다.`;
    });
  };

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
        .map((name) => ({ name, employee_id: "", account: "", left_on: "", left_reason: "" }));
      return [...rest, ...added].sort((a, b) => a.name.localeCompare(b.name, "ko"));
    });

  /** 담당자를 넘긴다 (TODO 122). 표기 통일과 달리 **명부는 그대로** 둔다. */
  const handover = (from: string, unfinished: number) => {
    if (unfinished === 0) return;
    const to = window.prompt(`"${from}" 의 과제를 누구에게 넘길까요?`, "");
    if (!to || !to.trim()) return;
    if (
      !window.confirm(
        `"${from}" 이(가) 담당인 **끝나지 않은 과제 ${unfinished}건**을 "${to.trim()}" 에게 넘깁니다.\n` +
          "끝난 과제는 그대로 둡니다 — 그때 그 사람이 한 것은 사실이기 때문입니다.\n" +
          "명부에서 이름이 사라지지는 않습니다.",
      )
    )
      return;
    void run(async () => {
      const result = await api.handover(from, to.trim());
      return `과제 ${result.count}건을 "${to.trim()}" 에게 넘겼습니다.`;
    });
  };

  const glued = people.filter((person) => splitPeople(person.name).length > 1);
  const needle = find.trim();
  // 찾기는 **보여 주는 것만** 거른다 — 저장은 늘 명부 전체를 보낸다.
  const shown = needle
    ? people.filter((person) => person.name.includes(needle) || (person.employee_id ?? "").includes(needle))
    : people;
  const leftCount = people.filter((person) => person.left_on).length;

  const update = (index: number, key: keyof Person, value: string) =>
    setPeople((prev) => prev.map((p, i) => (i === index ? { ...p, [key]: value } : p)));

  return (
    <div className="card">
      <div className="card-head">
        <h2>
          담당자 명부 {people.length}명
          {leftCount > 0 && <span className="muted"> · 떠난 사람 {leftCount}명</span>}
        </h2>
        <button
          className="ghost"
          onClick={() =>
            setPeople((prev) => [
              ...prev,
              { name: "", employee_id: "", account: "", left_on: "", left_reason: "" },
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
        사번·계정 칸은 지금 비워 두어도 됩니다 — 나중에 로그인이 생기면 그 칸만 채우면 됩니다.
        <br />
        전배·퇴사한 사람은 <b>빼지 말고 [떠난 날]을 적어 주세요.</b> 지우면 그 사람이 지난해 한 일이
        &ldquo;명부에 없는 이름&rdquo;이 되어 오타와 뒤섞입니다. 날짜를 적으면 자동완성에서 빠지고,
        아직 담당으로 남은 과제가 있으면 <b>홈이 대체 담당자를 정하라고 알려 줍니다.</b>
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
          <thead>
            <tr>
              <th>이름</th>
              <th>사번</th>
              <th>계정</th>
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
                className={person.left_on ? "person-left" : undefined}
                data-name={person.name}
              >
                <td>
                  <input value={person.name} onChange={(e) => update(index, "name", e.target.value)} />
                </td>
                <td>
                  <input
                    value={person.employee_id}
                    onChange={(e) => update(index, "employee_id", e.target.value)}
                    placeholder="나중에"
                  />
                </td>
                <td>
                  <input
                    value={person.account}
                    onChange={(e) => update(index, "account", e.target.value)}
                    placeholder="나중에"
                  />
                </td>
                <td className="muted">
                  {person.used ?? 0}건
                  {(person.unfinished ?? 0) > 0 && person.left_on && (
                    <span className="warn-text"> · 남은 {person.unfinished}건</span>
                  )}
                </td>
                <td className="person-left-cell">
                  <input
                    type="date"
                    value={person.left_on ?? ""}
                    onChange={(e) => update(index, "left_on", e.target.value)}
                    title="전배·퇴사한 날. 비워 두면 지금 있는 사람입니다."
                  />
                  <select
                    value={person.left_reason ?? ""}
                    disabled={!person.left_on}
                    onChange={(e) => update(index, "left_reason", e.target.value)}
                  >
                    <option value="">사유</option>
                    <option value="전배">전배</option>
                    <option value="퇴사">퇴사</option>
                  </select>
                </td>
                <td className="person-actions">
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
                  <button
                    className="ghost small danger"
                    onClick={() => setPeople((prev) => prev.filter((_, i) => i !== index))}
                  >
                    빼기
                  </button>
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
                <button
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

      {notice && <p className="hint notice">{notice}</p>}
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button disabled={busy} onClick={() => void save()}>
          {busy ? "저장 중…" : "명부 저장"}
        </button>
      </div>
    </div>
  );
}
