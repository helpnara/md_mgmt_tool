import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { Person } from "../types";

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

  const update = (index: number, key: keyof Person, value: string) =>
    setPeople((prev) => prev.map((p, i) => (i === index ? { ...p, [key]: value } : p)));

  return (
    <div className="card">
      <div className="card-head">
        <h2>담당자 명부 {people.length}명</h2>
        <button
          className="ghost"
          onClick={() => setPeople((prev) => [...prev, { name: "", employee_id: "", account: "" }])}
        >
          + 사람 추가
        </button>
      </div>
      <p className="hint">
        과제의 담당자 자동완성이 이 목록을 씁니다. 명부에 없는 이름도 <b>쓸 수는 있고</b>,
        아래 <b>명부에 없는 이름</b>에 모여 보입니다.
        <br />
        사번·계정 칸은 지금 비워 두어도 됩니다 — 나중에 로그인이 생기면 그 칸만 채우면 됩니다.
      </p>

      {people.length > 0 && (
        <table className="people-table">
          <thead>
            <tr>
              <th>이름</th>
              <th>사번</th>
              <th>계정</th>
              <th>과제</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {people.map((person, index) => (
              <tr key={index}>
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
                <td className="muted">{person.used ?? 0}건</td>
                <td>
                  <button
                    className="ghost small danger"
                    onClick={() => setPeople((prev) => prev.filter((_, i) => i !== index))}
                  >
                    빼기
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
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
