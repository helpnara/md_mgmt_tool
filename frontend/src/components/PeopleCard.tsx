import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { Person, Visitor } from "../types";
import { splitPeople } from "../people";
import { useEditedUnsaved } from "../util";
import { DATE_MAX, DATE_MIN, LEFT_REASONS, dateProblem, isDeparted, isFuture, personNameProblem } from "../inputRules";
import NameDialog, { changeCounts } from "./NameDialog";
import { enterToSave } from "./enterSave";
import { isAdmin } from "../me";

/** IP 칸의 글 → 주소 목록 (TODO 233). 쉼표 · 띄어쓰기로 여럿 */
function parseIps(text: string): string[] {
  return text.split(/[\s,;]+/).map((item) => item.trim()).filter(Boolean);
}

/** 화면에서 먼저 보는 IP 모양 — 정확한 검사는 서버(who.check_ip)가 한다 */
function ipProblem(ip: string): string | null {
  const v4 = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(ip);
  if (v4) return v4.slice(1).every((part) => Number(part) <= 255) ? null : `${ip} — 0~255 를 넘는 칸이 있습니다`;
  return ip.includes(":") ? null : `${ip} — IP 주소 모양이 아닙니다(예: 10.1.2.31)`;
}

/** PC 주소 칸 — 쓰는 동안의 글자는 그대로 두고(쉼표를 막 친 순간), 주소 목록만 위로 올린다 */
function IpCell({ ips, onChange, problem, locked }: { ips: string[]; onChange: (ips: string[]) => void; problem: string | null; locked?: string }) {
  const [text, setText] = useState(ips.join(", "));
  useEffect(() => {
    // 바깥(오늘 접속한 주소 [붙이기] · 다시 읽기)에서 바뀌었으면 글자를 따라간다
    if (parseIps(text).join(",") !== ips.join(",")) setText(ips.join(", "));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ips.join(",")]);
  return (
    <>
      <input
        value={text}
        onChange={(event) => {
          setText(event.target.value);
          onChange(parseIps(event.target.value));
        }}
        placeholder="개인 PC 만"
        aria-label="PC 주소"
        aria-invalid={problem ? true : undefined}
        disabled={Boolean(locked)}
        title={locked ?? problem ?? "이 사람 PC 의 IP. 여기서 연 화면은 이 사람으로 보고, 담당 과제의 진행일지 · 첨부 · 개요를 고칠 수 있습니다. 여럿이면 쉼표로"}
      />
      {problem && <span className="field-error ip-error">{problem}</span>}
    </>
  );
}

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
const LEADER_LOCKED = "팀장 줄의 이름 · PC 주소 · 떠난 날은 서버 PC(관리자)에서만 바꿉니다 (TODO 247)";

export default function PeopleCard({ onChanged }: { onChanged: () => void }) {
  // 팀장 PC 에서는 팀장 지정 · 팀장 줄을 잠근다 — 서버가 403 으로 지키고, 화면은 미리 잠가 헛걸음을 막는다 (TODO 247)
  const admin = isAdmin();
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
  // 오늘 바깥에서 접속한 주소 (TODO 233) — 등록 안 된 주소를 골라 사람에게 붙인다
  const [visitors, setVisitors] = useState<Visitor[]>([]);
  const [pickFor, setPickFor] = useState<Record<string, string>>({});

  const load = useCallback(() => {
    api
      .people()
      .then((data) => {
        setPeople(data.people);
        setSaved(data.people);
        setUnregistered(data.unregistered);
      })
      .catch((err: Error) => setError(err.message));
    api.peopleVisitors().then((data) => setVisitors(data.items)).catch(() => setVisitors([]));
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
    left:
      dateProblem(person.left_on, "떠난 날") ??
      (person.leader && person.left_on && isDeparted(person) ? "팀장은 떠난 사람이 될 수 없습니다 — 팀장을 먼저 옮기세요." : null),
  }));
  // PC 주소 (TODO 233) — 모양 · 한 주소에 두 사람(공용 PC 가 잘못 등록되지 않게)
  const ipOwners = new Map<string, string[]>();
  for (const person of people) for (const ip of person.ips ?? []) ipOwners.set(ip, [...(ipOwners.get(ip) ?? []), person.name.trim()]);
  const ipProblems = people.map((person) => {
    for (const ip of person.ips ?? []) {
      const shape = ipProblem(ip);
      if (shape) return shape;
      if ((ipOwners.get(ip) ?? []).length > 1) return `${ip} — 두 사람에게 있습니다(공용 PC 는 적지 않습니다)`;
    }
    return null;
  });
  const problemCount = rowProblems.filter((row) => row.name || row.id || row.left).length + ipProblems.filter(Boolean).length;
  const setIps = (index: number, ips: string[]) => setPeople((prev) => prev.map((p, i) => (i === index ? { ...p, ips } : p)));
  // 팀장 (TODO 235) — 한 명. 고르면 다른 사람의 표시는 풀린다
  const setLeader = (index: number) => setPeople((prev) => prev.map((p, i) => ({ ...p, leader: i === index })));
  const leaderRow = people.find((person) => person.leader);
  const registered = new Set([...ipOwners.keys()]);
  const attachIp = (ip: string, name: string) =>
    setPeople((prev) => prev.map((p) => (p.name === name ? { ...p, ips: [...(p.ips ?? []).filter((item) => item !== ip), ip] } : p)));
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
        <br />
        <b>팀장</b> — 이름 왼쪽 동그라미로 <b>한 명</b>을 고릅니다. 고르면 서버 PC · 팀장 PC 에서 쓴 기록의 작성자가 그 이름이 되고, 면담 대상에서 빠지며,
        화면 곳곳에 "팀장" 딱지가 붙습니다(과제 · 숫자는 그대로 셉니다). 팀장이 바뀌면 동그라미를 옮기면 됩니다.
        <br />
        <b>팀장 PC</b> — 팀장 줄에 적은 IP 는 <b>팀장 PC</b> 입니다. 서버를 따로 두었을 때 그 PC 에서 연 화면은 <b>서버 운영(데이터 위치 · 백업 폴더 ·
        되살리기)을 뺀 모든 것</b>을 할 수 있습니다. 팀장 지정 · 팀장 PC 주소 · 팀장의 떠난 날은 <b>서버 PC(관리자)에서만</b> 바꿉니다 (TODO 247).
        <br />
        <b>PC 주소</b> — 팀원 <b>개인 PC 의 IP</b> 를 적으면, 그 PC 에서 공유 주소로 연 화면은 그 사람으로 보고{" "}
        <b>담당 과제의 진행일지 · 첨부 · 개요</b>를 고칠 수 있습니다. 본인 면담은 보기만 됩니다. 가상 PC · 공용 PC 는 적지 마세요 —
        적지 않은 PC 는 지금처럼 보기만 됩니다. IP 가 바뀌면 여기서 고치면 됩니다.
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

      {people.length > 0 && !leaderRow && (
        <p className="hint warn-text leader-missing">아직 팀장을 고르지 않았습니다 — 이름 왼쪽 동그라미로 고르면 작성자 · 면담 대상이 따라갑니다.</p>
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
            <col className="col-ip" />
            <col className="col-left" />
            <col className="col-act" />
          </colgroup>
          <thead>
            <tr>
              <th title="이름 왼쪽 동그라미 — 팀장 한 명 (TODO 235)">이름 · 팀장</th>
              <th>사번</th>
              <th>과제</th>
              <th title="이 사람 PC 의 IP — 여기서 연 화면은 담당 과제를 고칠 수 있습니다 (TODO 233)">PC 주소</th>
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
                className={[isDeparted(person) ? "person-left" : person.left_on ? "person-leaving" : "", person.leader ? "person-leader" : ""].filter(Boolean).join(" ") || undefined}
                data-name={person.name}
              >
                <td>
                  <div className="name-with-leader">
                  {/* 팀장 한 명 (TODO 235) — 작성자 · 면담 대상 · 딱지가 이것을 따른다 */}
                  <input
                    type="radio"
                    name="people-leader"
                    className="leader-pick"
                    checked={Boolean(person.leader)}
                    onChange={() => setLeader(index)}
                    disabled={!admin}
                    aria-label={`${person.name || "이 사람"} 을(를) 팀장으로`}
                    title={person.leader ? "팀장" : "팀장으로 고르기 — 한 명만"}
                  />
                  <input
                    value={person.name}
                    onChange={(e) => update(index, "name", e.target.value)}
                    aria-invalid={rowProblems[index]?.name ? true : undefined}
                    disabled={!admin && Boolean(person.leader)}
                    title={!admin && person.leader ? LEADER_LOCKED : (rowProblems[index]?.name ?? undefined)}
                  />
                  </div>
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
                <td className="person-ip-cell">
                  <IpCell
                    ips={person.ips ?? []}
                    onChange={(ips) => setIps(index, ips)}
                    problem={ipProblems[index]}
                    locked={!admin && person.leader ? LEADER_LOCKED : undefined}
                  />
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
                      disabled={!admin && Boolean(person.leader)}
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
                    disabled={!admin && Boolean(person.leader)}
                    title={!admin && person.leader ? LEADER_LOCKED : undefined}
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

      {/* 오늘 접속한 주소 (TODO 233) — IP 를 묻고 받아 적지 않아도 되게. 팀원이 공유 주소로 한 번 들어오면 여기 선다 */}
      {visitors.length > 0 && (
        <div className="people-visitors">
          <p className="hint">
            <b>오늘 접속한 주소</b> — 다른 PC 에서 공유 주소로 들어온 기록입니다. 등록 안 된 주소는 사람을 골라 <b>[붙이기]</b> 한 뒤{" "}
            <b>[명부 저장]</b> 하면, 그 PC 에서 연 화면이 그 사람의 담당 과제를 고칠 수 있게 됩니다.
          </p>
          <ul className="visitor-list">
            {visitors.map((item) => (
              <li key={item.ip}>
                <code>{item.ip}</code>
                <span className="muted">
                  마지막 {item.last_at.slice(11, 16)} · {item.requests}회
                </span>
                {item.name ? (
                  <span>
                    → <b>{item.name}</b> 님으로 알아봤습니다
                  </span>
                ) : registered.has(item.ip) ? (
                  <span className="muted">명부에 적었습니다 — [명부 저장] 뒤부터 알아봅니다</span>
                ) : (
                  <>
                    <select
                      value={pickFor[item.ip] ?? ""}
                      onChange={(event) => setPickFor((prev) => ({ ...prev, [item.ip]: event.target.value }))}
                      aria-label={`${item.ip} 를 붙일 사람`}
                    >
                      <option value="">사람 고르기</option>
                      {people
                        .filter((person) => person.name.trim() && !isDeparted(person) && (admin || !person.leader))
                        .map((person) => (
                          <option key={person.name} value={person.name}>
                            {person.name}
                          </option>
                        ))}
                    </select>
                    <button
                      className="ghost small"
                      disabled={!pickFor[item.ip]}
                      onClick={() => attachIp(item.ip, pickFor[item.ip])}
                    >
                      붙이기
                    </button>
                    <span className="muted">공용 · 가상 PC 면 붙이지 마세요(보기만)</span>
                  </>
                )}
              </li>
            ))}
          </ul>
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
