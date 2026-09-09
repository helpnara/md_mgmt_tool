import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { Activity, ActivitySummary, Meta } from "../types";
import { useAddressBar } from "../nav";
import { splitPeople } from "../people";
import LoadError from "./LoadError";
import ActivityForm from "./ActivityForm";

/**
 * 팀원 역량 이력 (TODO 72).
 *
 * 사용자가 정한 것 셋을 화면이 그대로 따른다.
 *  1. **기록 단위는 사람.** 한 행사에 세 명이 가면 줄도 세 개다.
 *  2. **시간·비용은 옵션.** 비워 둔 것을 채우라고 재촉하지 않는다. 다만 합계 옆에
 *     "몇 건에서 나온 값인지"를 적는다 — 그러지 않으면 채운 사람만 커 보인다.
 *  3. **지나간 이력만.** 예정은 담지 않는다. 이 화면의 쓸모는 계획표가 아니라
 *     *면담에서 꺼낼 이야깃거리*이므로, **비어 있는 곳이 먼저 보여야 한다.**
 */

const ALL = "";
const THIS_YEAR = String(new Date().getFullYear());
const ALL_YEARS = "all";

function won(value: number): string {
  return value ? `${Math.round(value).toLocaleString("ko-KR")}원` : "—";
}

export default function Skills({ meta, query }: { meta: Meta; query: string }) {
  const initial = useMemo(() => new URLSearchParams(query), [query]);
  const [year, setYear] = useState(initial.get("year") ?? THIS_YEAR);
  const [person, setPerson] = useState(initial.get("person") ?? ALL);
  const [kind, setKind] = useState(initial.get("kind") ?? ALL);
  const [find, setFind] = useState(initial.get("q") ?? "");

  const [summary, setSummary] = useState<ActivitySummary | null>(null);
  const [rows, setRows] = useState<Activity[]>([]);
  const [error, setError] = useState<string | null>(null);
  // 고칠 때는 **그 줄 아래**에 폼을 편다. 화면 맨 위에 열면 방금 누른 자리가 화면 밖으로
  // 밀려나 무엇을 고치는 중인지 알 수 없다 (TODO 74).
  const [editingId, setEditingId] = useState<number | null>(null);
  const [adding, setAdding] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const say = (message: string) => {
    setNotice(message);
    window.setTimeout(() => setNotice(null), 4000);
  };

  const yearParam = year === ALL_YEARS ? "" : year;

  const load = useCallback(() => {
    Promise.all([
      api.activitySummary(yearParam),
      api.activities({ year: yearParam, person, kind, q: find.trim() }),
    ])
      .then(([nextSummary, nextRows]) => {
        setSummary(nextSummary);
        setRows(nextRows);
        setError(null);
      })
      .catch((err: Error) => setError(err.message));
  }, [yearParam, person, kind, find]);

  useEffect(load, [load]);

  useAddressBar(
    "skills",
    Object.fromEntries(
      Object.entries({ year: year === THIS_YEAR ? "" : year, person, kind, q: find.trim() })
        .filter(([, value]) => value),
    ) as Record<string, string>,
    (params) => {
      setYear(params.get("year") ?? THIS_YEAR);
      setPerson(params.get("person") ?? ALL);
      setKind(params.get("kind") ?? ALL);
      setFind(params.get("q") ?? "");
    },
  );

  const kindLabel = (key: string) =>
    meta.activity_kinds.find((item) => item.key === key)?.label ?? key;

  const remove = async (item: Activity) => {
    if (!window.confirm(`${item.person} 님의 '${item.title}' 기록을 지울까요? 보관함으로 옮겨집니다.`))
      return;
    await api.deleteActivity(item.id);
    load();
  };

  /** 하루면 날짜 하나, 여러 날이면 기간. 같은 해면 뒤쪽은 월·일만 적는다. */
  const period = (item: Activity) => {
    if (!item.end_date) return item.date;
    const tail = item.end_date.slice(0, 4) === item.date.slice(0, 4)
      ? item.end_date.slice(5)
      : item.end_date;
    return `${item.date} ~ ${tail}`;
  };

  if (error) return <LoadError message={error} onRetry={load} />;
  if (!summary) return <p className="hint">불러오는 중…</p>;

  // 붙은 이름은 사람이 아니므로 면담 대상에 세우지 않는다. 다만 **사람별 표에는 남겨 둔다** —
  // 거기서 보여야 사용자가 존재를 알고 정리한다 (TODO 74).
  const quiet = summary.people.filter(
    (item) => item.quiet && splitPeople(item.name).length === 1,
  );
  // 쉼표로 여러 명을 적었다가 한 덩이로 굳은 이름. 지금은 서버가 나눠 주지만,
  // 그 전에 명부로 들어간 이름은 사람별 표에 **없는 사람**으로 남는다 (TODO 74).
  const glued = summary.people.filter((item) => splitPeople(item.name).length > 1);
  const maxTrend = Math.max(
    1,
    ...summary.people.flatMap((item) => Object.values(item.trend)),
  );

  /** 같은 행사끼리 묶는다 (TODO 85). 목록은 이미 날짜순이라 순서는 그대로 지켜진다. */
  const events: Activity[][] = [];
  const seen = new Map<string, Activity[]>();
  for (const row of rows) {
    const group = seen.get(row.event_key);
    if (group) group.push(row);
    else {
      const fresh = [row];
      seen.set(row.event_key, fresh);
      events.push(fresh);
    }
  }

  return (
    <section className="skills">
      <div className="home-head">
        <h1>팀원 역량 이력</h1>
        <div className="skills-head-right">
          <label className="home-year">
            기준 연도
            <select value={year} onChange={(event) => setYear(event.target.value)}>
              {!summary.years.includes(THIS_YEAR) && <option value={THIS_YEAR}>{THIS_YEAR}년</option>}
              {summary.years.map((item) => (
                <option key={item} value={item}>
                  {item}년
                </option>
              ))}
              <option value={ALL_YEARS}>전체</option>
            </select>
          </label>
          <button onClick={() => { setAdding(true); setEditingId(null); }}>기록 추가</button>
        </div>
      </div>

      <p className="hint skills-intro">
        교육·세미나·박람회·학회 참여 이력을 <b>사람 기준</b>으로 쌓습니다. 한 행사에 여러 명이 가면
        사람 수만큼 기록합니다. <b>지나간 이력만</b> 담습니다 — 이 화면의 쓸모는 계획표가 아니라,
        쌓인 이력을 놓고 <b>내년에 무엇을 하면 좋을지 면담에서 이야기하는 것</b>입니다.
      </p>

      {adding && (
        <ActivityForm
          meta={meta}
          activity={null}
          onClose={() => setAdding(false)}
          onSaved={(message) => { setAdding(false); say(message); load(); }}
        />
      )}

      {notice && <p className="hint notice">{notice}</p>}

      {/* ── 팀 합계 ─────────────────────────────────────────────────── */}
      <div className="card">
        <h2>{year === ALL_YEARS ? "전체" : `${year}년`} 합계</h2>
        <div className="home-stats">
          {/* "기록 11건" 은 **참여 연인원**이다. 한 교육에 세 명이 가면 기록도 세 건이라
              (TODO 74), 그대로 두면 "올해 교육을 열한 번 보냈다"로 읽힌다.
              팀장이 실제로 묻는 수는 행사 수이므로 그쪽을 크게 세운다 (TODO 85). */}
          <div className="home-stat">
            <span className="home-stat-label">행사</span>
            <strong>{summary.team.events}건</strong>
            <span className="home-stat-note">참여 기록 {summary.team.count}건</span>
          </div>
          <div className="home-stat">
            <span className="home-stat-label">참여 인원</span>
            <strong>{summary.team.people}명</strong>
          </div>
          <div className="home-stat">
            <span className="home-stat-label">교육 시간</span>
            <strong>{summary.team.hours || "—"}{summary.team.hours ? "h" : ""}</strong>
          </div>
          <div className="home-stat">
            <span className="home-stat-label">비용</span>
            <strong>{won(summary.team.cost)}</strong>
          </div>
        </div>
        <p className="hint">
          <b>행사</b>는 날짜·구분·제목이 같으면 한 건으로 셉니다. <b>참여 기록</b>은 사람 수만큼
          늘어나므로 두 수는 다릅니다 — 사람별 집계에서 아무도 빠지지 않게 하려는 것입니다.
          {" "}시간·비용은 <b>옵션</b>입니다. 채워 넣은 기록만 합계에 들어가므로, 이 수는
          &ldquo;쓴 돈 전부&rdquo;가 아니라 <b>적어 둔 만큼</b>입니다.
        </p>
      </div>

      {/* ── 면담에서 먼저 꺼낼 줄 ───────────────────────────────────── */}
      {quiet.length > 0 && (
        <div className="card skills-quiet">
          <h2>면담에서 먼저 볼 사람</h2>
          <p className="hint">
            {year === ALL_YEARS ? "" : `${year}년에 `}기록이 없거나 마지막 활동이{" "}
            {summary.quiet_days}일을 넘긴 사람입니다. 비어 있다는 사실 자체가 이야깃거리입니다.
          </p>
          <div className="skills-quiet-row">
            {quiet.map((item) => (
              <button
                key={item.name}
                className="skills-quiet-chip"
                onClick={() => setPerson(item.name)}
                title="이 사람의 기록만 봅니다"
              >
                {item.name}
                <span className="muted">
                  {item.last_date ? ` 마지막 ${item.last_date}` : " 기록 없음"}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* ── 사람별 ─────────────────────────────────────────────────── */}
      <div className="card wide">
        <h2>사람별</h2>
        {/* 명부가 비어 있으면 머리행만 있는 빈 표가 남는다 — 무엇을 해야 하는지
            알려 주지 않는 화면이다 (TODO 84). 이름이 먼저라는 것을 적어 준다. */}
        {summary.people.length === 0 && (
          <p className="empty">
            아직 이름이 없습니다. <a href="#/settings">설정 → 담당자 명부</a> 에 팀원을 넣어 두면
            기록이 없는 사람도 이 표에 서고, 그 빈칸이 곧 면담에서 꺼낼 이야깃거리가 됩니다.
            {" "}명부 없이 <b>[기록 추가]</b> 로 바로 시작해도 됩니다.
          </p>
        )}
        {glued.length > 0 && (
          <p className="hint warn-text">
            <b>{glued.map((item) => item.name).join(", ")}</b> 처럼 한 칸에 여러 이름이 든 줄이 있습니다.
            실제로는 없는 사람이므로 <a href="#/settings">설정 → 담당자 명부</a> 에서{" "}
            <b>[사람별로 나누기]</b> 를 누르고 <b>[명부 저장]</b> 하시면 사라집니다.
          </p>
        )}
        {summary.people.length > 0 && (
        <div className="table-scroll">
          <table className="grid skills-table">
            <thead>
              <tr>
                <th>이름</th>
                <th>기록</th>
                {meta.activity_kinds.map((item) => (
                  <th key={item.key}>{item.label}</th>
                ))}
                <th>시간</th>
                <th>비용</th>
                <th>최근 추이</th>
                <th>마지막 활동</th>
              </tr>
            </thead>
            <tbody>
              {summary.people.map((item) => (
                <tr key={item.name} className={item.quiet ? "quiet-row" : undefined}>
                  <td>
                    <button
                      className={person === item.name ? "linkish on" : "linkish"}
                      onClick={() => setPerson(person === item.name ? ALL : item.name)}
                    >
                      {item.name}
                    </button>
                  </td>
                  <td>{item.count}</td>
                  {meta.activity_kinds.map((kindInfo) => (
                    <td key={kindInfo.key} className={item.by_kind[kindInfo.key] ? undefined : "zero"}>
                      {item.by_kind[kindInfo.key] ?? 0}
                    </td>
                  ))}
                  <td title={`시간을 적어 둔 기록 ${item.with_hours}건`}>
                    {item.hours ? `${item.hours}h` : "—"}
                  </td>
                  <td title={`비용을 적어 둔 기록 ${item.with_cost}건`}>{won(item.cost)}</td>
                  <td>
                    {/* 한 해만 보면 늘고 주는 것을 알 수 없다. 최근 몇 해를 나란히 놓는다. */}
                    {summary.trend_years.length >= 3 ? (
                      <span className="spark" aria-label="최근 연도별 건수">
                        {summary.trend_years.map((y) => (
                          <span
                            key={y}
                            className="spark-bar"
                            title={`${y}년 ${item.trend[y] ?? 0}건`}
                            style={{ height: `${((item.trend[y] ?? 0) / maxTrend) * 100 || 4}%` }}
                          />
                        ))}
                      </span>
                    ) : (
                      /* 해가 둘뿐이면 6px 막대 두 개라 부스러기처럼 보인다 (TODO 103-E).
                         셋이 쌓일 때까지는 숫자로 쓴다. */
                      <span className="spark-text muted">
                        {summary.trend_years.map((y) => `${y.slice(2)}년 ${item.trend[y] ?? 0}`).join(" · ") || "—"}
                      </span>
                    )}
                  </td>
                  <td className="muted">
                    {item.last_date ?? "—"}
                    {item.days_since !== null && item.days_since >= summary.quiet_days && (
                      <span className="due due-warn"> D+{item.days_since}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        )}
        {summary.people.length > 0 && (
          <p className="hint">
            추이 막대는 {summary.trend_years.join(" · ") || "—"}년이며 <b>연도 조건을 따르지 않습니다</b> —
            과거를 봐야 다음을 이야기할 수 있기 때문입니다. 시간·비용에 마우스를 올리면 그 합계가
            몇 건에서 나온 값인지 보입니다. <b>기록</b>은 참여 건수이고, 한 행사에 여럿이 가면
            사람마다 한 건씩 잡힙니다.
          </p>
        )}
      </div>

      {/* ── 기록 목록 ──────────────────────────────────────────────── */}
      <div className="card wide">
        <div className="card-head">
          <h2>
            행사 {events.length}건
            <span className="hint"> · 참여 기록 {rows.length}건</span>
            {person && <span className="hint"> · {person}</span>}
          </h2>
          <div className="filters">
            <select value={person} onChange={(event) => setPerson(event.target.value)}>
              <option value={ALL}>사람 전체</option>
              {summary.people.map((item) => (
                <option key={item.name} value={item.name}>
                  {item.name}
                </option>
              ))}
            </select>
            <select value={kind} onChange={(event) => setKind(event.target.value)}>
              <option value={ALL}>구분 전체</option>
              {meta.activity_kinds.map((item) => (
                <option key={item.key} value={item.key}>
                  {item.label}
                </option>
              ))}
            </select>
            <input
              type="search"
              value={find}
              onChange={(event) => setFind(event.target.value)}
              placeholder="제목·주최·얻은 것에서 찾기"
              aria-label="역량 이력 찾기"
            />
          </div>
        </div>

        {rows.length === 0 ? (
          <p className="empty">조건에 맞는 기록이 없습니다.</p>
        ) : (
          <ul className="activity-list">
            {events.map((group) => {
              const first = group[0];
              const shared = group.length > 1;
              return (
                <li key={first.event_key}>
                  <div className="activity-head">
                    <span className="activity-date">{period(first)}</span>
                    <span className="tag">{kindLabel(first.kind)}</span>
                    <strong className="activity-title">{first.title}</strong>
                    {/* 한 행사에 여러 명이면 이름을 나란히 세운다. 줄이 사람 수만큼
                        늘어나면 "올해 몇 번 갔나"를 눈으로 셀 수 없다 (TODO 85). */}
                    {group.map((item) => (
                      <span key={item.id} className="activity-person">
                        {item.person}
                      </span>
                    ))}
                    {shared && <span className="hint activity-count">{group.length}명</span>}
                    <span className="grow" />
                    {!shared && (
                      <>
                        <button
                          className={editingId === first.id ? "ghost small on" : "ghost small"}
                          onClick={() => {
                            setAdding(false);
                            setEditingId(editingId === first.id ? null : first.id);
                          }}
                        >
                          수정
                        </button>
                        <button
                          className="ghost small danger"
                          onClick={() => remove(first)}
                        >
                          삭제
                        </button>
                      </>
                    )}
                  </div>
                  <div className="activity-meta">
                    {first.host && <span>{first.host}</span>}
                    {first.place && <span>{first.place}</span>}
                    {first.hours !== null && <span>{first.hours}시간</span>}
                    {first.cost !== null && <span>{won(first.cost)}</span>}
                    {first.link && (
                      <span className="activity-link" title="수료증·자료 위치">
                        {first.link}
                      </span>
                    )}
                  </div>
                  {/* 고치고 지우는 일은 **사람마다** 따로다 — 한 사람만 빠졌을 수도 있다. */}
                  {shared && (
                    <div className="activity-people">
                      {group.map((item) => (
                        <span key={item.id} className="activity-person-row">
                          <b>{item.person}</b>
                          <button
                            className={editingId === item.id ? "ghost small on" : "ghost small"}
                            onClick={() => {
                              setAdding(false);
                              setEditingId(editingId === item.id ? null : item.id);
                            }}
                          >
                            수정
                          </button>
                          <button className="ghost small danger" onClick={() => remove(item)}>
                            삭제
                          </button>
                        </span>
                      ))}
                    </div>
                  )}
                  {group.map(
                    (item) =>
                      item.takeaway && (
                        <p key={`t-${item.id}`} className="activity-takeaway">
                          {shared && <b>{item.person} · </b>}
                          {item.takeaway}
                        </p>
                      ),
                  )}
                  {group.map(
                    (item) =>
                      editingId === item.id && (
                        <ActivityForm
                          key={`f-${item.id}`}
                          meta={meta}
                          activity={item}
                          onClose={() => setEditingId(null)}
                          onSaved={(message) => { setEditingId(null); say(message); load(); }}
                        />
                      ),
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </section>
  );
}
