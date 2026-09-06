import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { Activity, ActivitySummary, Meta } from "../types";
import { useAddressBar } from "../nav";
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
  const [editing, setEditing] = useState<Activity | null>(null);
  const [adding, setAdding] = useState(false);

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

  if (error) return <LoadError message={error} onRetry={load} />;
  if (!summary) return <p className="hint">불러오는 중…</p>;

  const quiet = summary.people.filter((item) => item.quiet);
  const maxTrend = Math.max(
    1,
    ...summary.people.flatMap((item) => Object.values(item.trend)),
  );

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
          <button onClick={() => { setAdding(true); setEditing(null); }}>기록 추가</button>
        </div>
      </div>

      <p className="hint skills-intro">
        교육·세미나·박람회·학회 참여 이력을 <b>사람 기준</b>으로 쌓습니다. 한 행사에 여러 명이 가면
        사람 수만큼 기록합니다. <b>지나간 이력만</b> 담습니다 — 이 화면의 쓸모는 계획표가 아니라,
        쌓인 이력을 놓고 <b>내년에 무엇을 하면 좋을지 면담에서 이야기하는 것</b>입니다.
      </p>

      {(adding || editing) && (
        <ActivityForm
          meta={meta}
          activity={editing}
          onClose={() => { setAdding(false); setEditing(null); }}
          onSaved={() => { setAdding(false); setEditing(null); load(); }}
        />
      )}

      {/* ── 팀 합계 ─────────────────────────────────────────────────── */}
      <div className="card">
        <h2>{year === ALL_YEARS ? "전체" : `${year}년`} 합계</h2>
        <div className="home-stats">
          <div className="home-stat">
            <span className="home-stat-label">기록</span>
            <strong>{summary.team.count}건</strong>
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
          시간·비용은 <b>옵션</b>입니다. 채워 넣은 기록만 합계에 들어가므로, 이 수는
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
        <p className="hint">
          추이 막대는 {summary.trend_years.join(" · ") || "—"}년이며 <b>연도 조건을 따르지 않습니다</b> —
          과거를 봐야 다음을 이야기할 수 있기 때문입니다. 시간·비용에 마우스를 올리면 그 합계가
          몇 건에서 나온 값인지 보입니다.
        </p>
      </div>

      {/* ── 기록 목록 ──────────────────────────────────────────────── */}
      <div className="card wide">
        <div className="card-head">
          <h2>
            기록 {rows.length}건
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
            {rows.map((item) => (
              <li key={item.id}>
                <div className="activity-head">
                  <span className="activity-date">{item.date}</span>
                  <span className="tag">{kindLabel(item.kind)}</span>
                  <strong className="activity-title">{item.title}</strong>
                  <span className="activity-person">{item.person}</span>
                  <span className="grow" />
                  <button className="ghost small" onClick={() => { setEditing(item); setAdding(false); }}>
                    수정
                  </button>
                  <button
                    className="ghost small danger"
                    onClick={async () => {
                      if (!window.confirm(`'${item.title}' 기록을 지울까요? 보관함으로 옮겨집니다.`)) return;
                      await api.deleteActivity(item.id);
                      load();
                    }}
                  >
                    삭제
                  </button>
                </div>
                <div className="activity-meta">
                  {item.host && <span>{item.host}</span>}
                  {item.place && <span>{item.place}</span>}
                  {item.hours !== null && <span>{item.hours}시간</span>}
                  {item.cost !== null && <span>{won(item.cost)}</span>}
                  {item.link && (
                    <span className="activity-link" title="수료증·자료 위치">
                      {item.link}
                    </span>
                  )}
                </div>
                {item.takeaway && <p className="activity-takeaway">{item.takeaway}</p>}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
