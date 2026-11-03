import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { Activity, ActivitySummary, Meta } from "../types";
import { backTarget, useAddressBar } from "../nav";
import { leftLabel, splitPeople } from "../people";
import { isReadonly } from "../readonly";
import LoadError from "./LoadError";
import ActivityForm from "./ActivityForm";
import MeetingPanel from "./MeetingPanel";
import TotalRow from "./TotalRow";
import ViewTabs from "./ViewTabs";
import Explain from "./Explain";
import { cellCount, DASH, sumBy, todayIso, useLatest } from "../util";
import { isDeparted } from "../inputRules";

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

/** 기록 목록에 처음 세우는 행사 수 — 더 보기로 이만큼씩 늘린다 (TODO 227) */
const EVENT_PAGE = 20;
/** 예정 묶음에 처음 세우는 행사 수 (TODO 232 ⑥) — 가까운 것부터 */
const PLANNED_PAGE = 10;

/** 화면 안 탭 (TODO 232 ②) — "" = 사람별 · records = 기록 · meetings = 면담(팀장 PC 만) */
type SkillsTab = "" | "records" | "meetings";
function tabFrom(params: URLSearchParams, readonly: boolean): SkillsTab {
  const value = params.get("tab");
  if (value === "records") return "records";
  if (value === "meetings") return readonly ? "" : "meetings";
  // 탭 없이 조건(예정만 · 구분 · 찾기)만 실려 온 옛 주소는 기록 목록을 보려던 것이다
  if (params.get("when") || params.get("kind") || params.get("q")) return "records";
  return "";
}

/** 오늘에서 그 날까지 남은 날 — 이 PC 의 오늘 기준 (홈의 D-띠지와 같은 규칙, TODO 226) */
function daysFromToday(date: string): number {
  return Math.round((Date.parse(`${date}T00:00:00`) - Date.parse(`${todayIso()}T00:00:00`)) / 864e5);
}

/** 같은 행사끼리 묶는다 (TODO 85). 들어온 순서를 지킨다. */
function groupEvents(rows: Activity[]): Activity[][] {
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
  return events;
}

export default function Skills({ meta, query }: { meta: Meta; query: string }) {
  const readonly = isReadonly(); // 읽기 전용 공유 (191) — 면담 칸 · 면담 열을 뺀다. 설정 링크는 글자로 (208)
  const initial = useMemo(() => new URLSearchParams(query), [query]);
  const [year, setYear] = useState(initial.get("year") ?? THIS_YEAR);
  // 어디서 왔는지 (TODO 128). 조건이 아니라 돌아갈 곳이다.
  const [back] = useState(() => initial.get("back") ?? "");
  const [person, setPerson] = useState(initial.get("person") ?? ALL);
  const [kind, setKind] = useState(initial.get("kind") ?? ALL);
  const [find, setFind] = useState(initial.get("q") ?? "");
  // 예정만 · 지난 것만 (TODO 221). 비우면 모두
  const [when, setWhen] = useState(initial.get("when") ?? "");
  const [tab, setTab] = useState<SkillsTab>(() => tabFrom(initial, readonly));
  const [plannedAll, setPlannedAll] = useState(false);
  // 기록 목록은 처음에 최근 행사 몇 건만 (TODO 227) — 행사가 쌓이자 화면이 한없이 길어졌다. 조건을 바꾸면 다시 처음부터
  const [shown, setShown] = useState(EVENT_PAGE);

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
  // 찾기 칸은 글자마다 묻지 않는다 — 250ms 쉬면 묻는다 (TODO 210 ①)
  const [findQuery, setFindQuery] = useState(() => find.trim());
  useEffect(() => {
    const timer = window.setTimeout(() => setFindQuery(find.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [find]);
  // 조건을 빨리 바꾸면 앞 요청이 늦게 와 다른 해 숫자가 남을 수 있다 — 마지막 요청만 받는다 (TODO 210 ①)
  const latest = useLatest();

  const load = useCallback(() => {
    const mine = latest();
    Promise.all([
      api.activitySummary(yearParam),
      api.activities({ year: yearParam, person, kind, q: findQuery, when }),
    ])
      .then(([nextSummary, nextRows]) => {
        if (!mine()) return;
        setSummary(nextSummary);
        setRows(nextRows);
        setError(null);
      })
      .catch((err: Error) => mine() && setError(err.message));
  }, [yearParam, person, kind, findQuery, when, latest]);

  useEffect(load, [load]);
  useEffect(() => setShown(EVENT_PAGE), [yearParam, person, kind, findQuery, when]);

  useAddressBar(
    "skills",
    Object.fromEntries(
      Object.entries({ tab, year: year === THIS_YEAR ? "" : year, person, kind, q: find.trim(), when, back })
        .filter(([, value]) => value),
    ) as Record<string, string>,
    (params) => {
      setTab(tabFrom(params, readonly));
      setYear(params.get("year") ?? THIS_YEAR);
      setPerson(params.get("person") ?? ALL);
      setKind(params.get("kind") ?? ALL);
      setFind(params.get("q") ?? "");
      setWhen(params.get("when") ?? "");
    },
  );

  const kindLabel = (key: string) =>
    meta.activity_kinds.find((item) => item.key === key)?.label ?? key;

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
    // 역량이 뜸하거나 · **면담할 때가 지났거나**(TODO 182) — 까닭은 칩에 따로 적는다
    (item) => (item.quiet || item.meeting_due) && !item.left && splitPeople(item.name).length === 1,
  );
  // 쉼표로 여러 명을 적었다가 한 덩이로 굳은 이름. 지금은 서버가 나눠 주지만,
  // 그 전에 명부로 들어간 이름은 사람별 표에 **없는 사람**으로 남는다 (TODO 74).
  const glued = summary.people.filter((item) => splitPeople(item.name).length > 1);
  const peopleRows = [...summary.people].sort((a, b) => Number(Boolean(a.left)) - Number(Boolean(b.left)));
  const maxTrend = Math.max(
    1,
    ...summary.people.flatMap((item) => Object.values(item.trend)),
  );

  // 기록 목록 (TODO 232 ⑥) — **예정은 위에 따로, 가까운 것부터**. 아래 목록은 **지난 기록, 최근 것부터**.
  // 예전에는 둘을 날짜 늦은 순으로 섞어 12월 예정부터 나왔다 — 지난 기록을 보려면 예정을 다 지나야 했다.
  const plannedEvents = groupEvents(
    rows.filter((row) => row.planned).sort((a, b) => a.date.localeCompare(b.date) || a.title.localeCompare(b.title)),
  );
  const pastRows = rows.filter((row) => !row.planned);
  const events = groupEvents(pastRows);
  const allEvents = plannedEvents.length + events.length;

  // 사람별 표의 빈 열 (TODO 232 ③) — 모든 사람이 빈 열만 뺀다. 줄 안의 빈 칸은 그대로 `-`(어디가 비었는지가 요점이다)
  const shownKinds = meta.activity_kinds.filter((kindInfo) => summary.people.some((item) => item.by_kind[kindInfo.key]));
  const cols = {
    hours: summary.people.some((item) => item.hours),
    cost: summary.people.some((item) => item.cost),
    meeting: !readonly && summary.people.some((item) => item.last_meeting),
    followups: !readonly && summary.people.some((item) => item.open_followups),
  };
  const hiddenCols = [
    ...meta.activity_kinds.filter((kindInfo) => !shownKinds.includes(kindInfo)).map((kindInfo) => kindInfo.label),
    ...(cols.hours ? [] : ["시간"]),
    ...(cols.cost ? [] : ["비용"]),
    ...(!readonly && !cols.meeting ? ["마지막 면담"] : []),
    ...(!readonly && !cols.followups ? ["하기로 한 것"] : []),
  ];

  /** 사람을 고른다 — 그 사람의 기록(또는 면담)으로 넘어간다. 고른 사람은 탭을 옮겨도 남는다.
   *  이미 고른 사람을 다시 누르면 푼다(TODO 183 — 탭 위의 띠 [팀 전체로 ×] 와 같은 일) */
  const pick = (name: string, to: SkillsTab = "records") => {
    if (person === name) {
      setPerson(ALL);
      return;
    }
    setPerson(name);
    setTab(to);
  };

  /** 한 행사 한 줄 (TODO 232 E) — 주관 · 장소 · 시간 · 비용을 제목 줄 끝에 작게 붙여 한 줄로 */
  const eventRow = (group: Activity[], planned: boolean) => {
    const first = group[0];
    const shared = group.length > 1;
    const left = planned ? daysFromToday(first.date) : null;
    const details = [
      first.host,
      first.place,
      first.hours !== null ? `${first.hours}시간` : null,
      first.cost !== null ? won(first.cost) : null,
    ].filter(Boolean);
    return (
      <li key={first.event_key} className={planned ? "activity-planned" : undefined}>
        <div className="activity-head">
          {/* 예정은 남은 날 띠지 — 홈의 다가오는 팀원 일정과 같은 모양 (TODO 226) */}
          {left !== null && (
            <span
              className={`left-chip ${left <= 0 ? "left-now" : left <= 7 ? "left-soon" : "left-later"}`}
              title="시작일이 오늘보다 뒤 — 숫자에는 그날이 지나야 듭니다"
            >
              {left <= 0 ? "오늘" : `D-${left}`}
            </span>
          )}
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
          {details.length > 0 && <span className="activity-meta-inline">{details.join(" · ")}</span>}
          {first.link && (
            <span className="activity-link" title={`수료증·자료 위치 — ${first.link}`}>
              {first.link}
            </span>
          )}
          <span className="grow" />
          {/* 줄에는 [수정]만 — [삭제]는 고치는 자리 안에 있다 (TODO 232 ⑤) */}
          {!shared && (
            <button data-write
              className={editingId === first.id ? "ghost small on" : "ghost small"}
              onClick={() => {
                setAdding(false);
                setEditingId(editingId === first.id ? null : first.id);
              }}
            >
              수정
            </button>
          )}
        </div>
        {/* 고치고 지우는 일은 **사람마다** 따로다 — 한 사람만 빠졌을 수도 있다. */}
        {shared && (
          <div className="activity-people">
            {group.map((item) => (
              <span key={item.id} className="activity-person-row">
                <b>{item.person}</b>
                <button data-write
                  className={editingId === item.id ? "ghost small on" : "ghost small"}
                  onClick={() => {
                    setAdding(false);
                    setEditingId(editingId === item.id ? null : item.id);
                  }}
                >
                  수정
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
                onDeleted={(message) => { setEditingId(null); say(message); load(); }}
              />
            ),
        )}
      </li>
    );
  };

  const tabs = [
    { key: "", label: "사람별", title: "합계 · 면담에서 먼저 볼 사람 · 사람별 표" },
    { key: "records", label: "기록", title: "교육 · 행사 기록 — 예정과 지난 기록" },
    ...(readonly ? [] : [{ key: "meetings", label: "면담", title: "면담 기록 · 하기로 한 것 (팀장만)" }]),
  ];

  return (
    <section className="skills">
      {/* 홈에서 왔으면 돌아갈 길을 그린다 (TODO 128). 메뉴로 왔으면 그리지 않는다 —
          없는 길을 만들지 않는다. */}
      {back && (
        <a className="back" href={backTarget(back).href}>
          ← {backTarget(back).label}
        </a>
      )}
      <div className="home-head">
        <div>
          <h1>팀원역량</h1>
          <Explain
            id="skills-intro"
            className="page-desc skills-intro"
            lead={<>팀원 역량 이력 — 교육·세미나·박람회·학회 참여 이력을 <b>사람 기준</b>으로 쌓습니다. 숫자는 <b>지나간 것만</b> 셉니다.</>}
          >
            한 행사에 여러 명이 가면 사람 수만큼 기록합니다. 앞으로 갈 교육 · 행사도 <b>예정</b>으로 적어 둘 수 있습니다(홈에 다가오는 일정으로 보입니다).
            이 화면의 쓸모는 쌓인 이력을 놓고 <b>내년에 무엇을 하면 좋을지 면담에서 이야기하는 것</b>입니다.
          </Explain>
        </div>
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

      {adding && (
        <ActivityForm
          meta={meta}
          activity={null}
          onClose={() => setAdding(false)}
          onSaved={(message) => { setAdding(false); say(message); load(); }}
        />
      )}

      {notice && <p className="hint notice">{notice}</p>}

      {/* 화면 안 탭 (TODO 232 ②) — 사람별(통계) · 기록(입력 · 관리) · 면담(팀장 것). 팀원 PC 에는 면담 탭이 없다 (191) */}
      <ViewTabs label="팀원역량 보기" className="skills-tabs" value={tab} onChange={(key) => setTab(key as SkillsTab)} tabs={tabs} />

      {/* ── 지금 보는 사람 (TODO 183 · 185) — 기록 · 면담 탭에서. 어디서 골랐든 푸는 자리는 여기 하나다 ── */}
      {person && tab !== "" && (
        <div className="card wide skills-person-bar" role="status">
          <span>
            {tab === "meetings" ? "면담 기록" : "역량 기록"}은 <b className="skills-person-name">{person}</b> 님만 보는 중
          </span>
          <button type="button" className="ghost small" onClick={() => setPerson(ALL)} title="면담 기록 · 역량 기록을 팀 전체로">
            팀 전체로 ×
          </button>
        </div>
      )}

      <div role="tabpanel" className={`skills-panel skills-panel-${tab || "people"}`}>
      {tab === "" && (
        <>
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
          {(summary.team.planned ?? 0) > 0 && (
            <button
              className="home-stat go"
              onClick={() => { setWhen("planned"); setTab("records"); }}
              title="기록 탭에서 예정만 봅니다"
            >
              <span className="home-stat-label">예정</span>
              <strong>{summary.team.planned}건</strong>
              <span className="home-stat-note">숫자에 들지 않음</span>
            </button>
          )}
          <div className="home-stat">
            <span className="home-stat-label">참여 인원</span>
            <strong>{summary.team.people}명</strong>
          </div>
          <div className={summary.team.hours ? "home-stat" : "home-stat zero-stat"}>
            <span className="home-stat-label">교육 시간</span>
            <strong>{summary.team.hours || "—"}{summary.team.hours ? "h" : ""}</strong>
          </div>
          <div className={summary.team.cost ? "home-stat" : "home-stat zero-stat"}>
            <span className="home-stat-label">비용</span>
            <strong>{won(summary.team.cost)}</strong>
          </div>
        </div>
        <Explain id="skills-total" lead={<><b>행사</b>는 날짜·구분·제목이 같으면 한 건, <b>참여 기록</b>은 사람 수만큼 셉니다.</>}>
          그래서 두 수는 다릅니다 — 사람별 집계에서 아무도 빠지지 않게 하려는 것입니다.
          {" "}시간·비용은 <b>옵션</b>입니다. 채워 넣은 기록만 합계에 들어가므로, 이 수는
          &ldquo;쓴 돈 전부&rdquo;가 아니라 <b>적어 둔 만큼</b>입니다.
        </Explain>
      </div>

      {/* ── 면담에서 먼저 꺼낼 줄 ───────────────────────────────────── */}
      {quiet.length > 0 && (
        <div className="card skills-quiet">
          <h2>면담에서 먼저 볼 사람</h2>
          <Explain
            id="skills-quiet"
            lead={
              <>
                {year === ALL_YEARS ? "" : `${year}년에 `}역량 기록이 없거나 마지막 활동이 {summary.quiet_days}일을 넘긴 사람
                {!readonly && <>, 그리고 <b>면담할 때가 지난 사람</b></>}입니다.
              </>
            }
          >
            {!readonly && <>면담할 때는 정한 다음 면담일이 지났거나 마지막 면담에서 {summary.meeting_cycle_days}일이 지난 것입니다. </>}
            명부에서 떠난 사람은 여기 서지 않고, 사람별 표 맨 아래에 흐리게 남습니다.
            비어 있다는 사실 자체가 이야깃거리입니다. 누르면 그 사람의 {readonly ? "기록" : "면담 · 기록"}으로 갑니다.
          </Explain>
          <div className="skills-quiet-row">
            {quiet.map((item) => (
              <button
                key={item.name}
                className={person === item.name ? "skills-quiet-chip on" : "skills-quiet-chip"}
                // 면담할 때가 지났으면 면담 탭으로, 아니면 기록 탭으로 (TODO 232 ②). 다시 누르면 푼다
                onClick={() => pick(item.name, item.meeting_due && !readonly ? "meetings" : "records")}
                aria-pressed={person === item.name}
                title={person === item.name ? "다시 누르면 팀 전체로 돌아갑니다" : item.meeting_due && !readonly ? "이 사람의 면담 기록으로 갑니다" : "이 사람의 역량 기록으로 갑니다"}
              >
                {item.name}
                {item.quiet && (
                  <span className="muted">{item.last_date ? ` 마지막 활동 ${item.last_date}` : " 역량 기록 없음"}</span>
                )}
                {item.meeting_due && (
                  <span className="due due-warn"> 면담 {item.meeting_days_since !== null ? `D+${item.meeting_days_since}` : ""}</span>
                )}
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
            아직 이름이 없습니다. {readonly ? <b>설정 → 담당자 명부</b> : <a href="#/settings">설정 → 담당자 명부</a>} 에 팀원을 넣어 두면
            기록이 없는 사람도 이 표에 서고, 그 빈칸이 곧 면담에서 꺼낼 이야깃거리가 됩니다.
            {" "}명부 없이 <b>[기록 추가]</b> 로 바로 시작해도 됩니다.
          </p>
        )}
        {glued.length > 0 && (
          <p className="hint warn-text">
            <b>{glued.map((item) => item.name).join(", ")}</b> 처럼 한 칸에 여러 이름이 든 줄이 있습니다.
            실제로는 없는 사람이므로 {readonly ? <b>설정 → 담당자 명부</b> : <a href="#/settings">설정 → 담당자 명부</a>} 에서{" "}
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
                {shownKinds.map((item) => (
                  <th key={item.key}>{item.label}</th>
                ))}
                {cols.hours && <th>시간</th>}
                {cols.cost && <th>비용</th>}
                <th>최근 추이</th>
                <th>마지막 활동</th>
                {/* 면담 (TODO 182) — 역량 이력과 따로 센다 */}
                {cols.meeting && <th>마지막 면담</th>}
                {cols.followups && <th title="면담에서 하기로 하고 아직 닫지 않은 것">하기로 한 것</th>}
              </tr>
            </thead>
            <tbody>
              {peopleRows.map((item) => (
                <tr
                  key={item.name}
                  // 지금 보는 사람의 줄은 옅게 칠한다 — 표에서도 누구를 보는지 보이게 (TODO 183). 떠난 사람은 흐리게, 맨 아래 (194)
                  className={[item.quiet ? "quiet-row" : "", person === item.name ? "picked-row" : "", item.left ? "left-row" : ""].filter(Boolean).join(" ") || undefined}
                >
                  <td>
                    <button
                      className={person === item.name ? "linkish on" : "linkish"}
                      onClick={() => pick(item.name)}
                      aria-pressed={person === item.name}
                      title={person === item.name ? "다시 누르면 팀 전체로 돌아갑니다" : "이 사람의 역량 기록으로 갑니다"}
                    >
                      {item.name}
                    </button>
                    {item.left && (
                      <span className="tag left-tag" title={item.left_on ? `${item.left_on} 부터` : undefined}>
                        {leftLabel(meta, item.name) || "떠남"}
                      </span>
                    )}
                  </td>
                  <td className={item.count ? undefined : "zero"}>
                    {cellCount(item.count)}
                    {/* 예정은 건수에 들지 않는다 — 옆에 작게 (TODO 221) */}
                    {(item.planned ?? 0) > 0 && <span className="muted planned-count" title="예정 — 그날이 지나야 셉니다"> +예정 {item.planned}</span>}
                  </td>
                  {shownKinds.map((kindInfo) => (
                    // 0 은 흐린 `-` (TODO 158). 줄 안의 칸은 지우지 않는다 — 어디가 비었는지가 요점이다
                    <td key={kindInfo.key} className={item.by_kind[kindInfo.key] ? undefined : "zero"}>
                      {cellCount(item.by_kind[kindInfo.key])}
                    </td>
                  ))}
                  {cols.hours && (
                    <td title={`시간을 적어 둔 기록 ${item.with_hours}건`} className={item.hours ? undefined : "zero"}>
                      {item.hours ? `${item.hours}h` : DASH}
                    </td>
                  )}
                  {cols.cost && (
                    <td title={`비용을 적어 둔 기록 ${item.with_cost}건`} className={item.cost ? undefined : "zero"}>
                      {item.cost ? won(item.cost) : DASH}
                    </td>
                  )}
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
                    {item.last_date ?? DASH}
                    {item.days_since !== null && item.days_since >= summary.quiet_days && (
                      <span className="due due-warn"> D+{item.days_since}</span>
                    )}
                  </td>
                  {cols.meeting && (
                    <td className="muted one-line">
                      {item.last_meeting ?? DASH}
                      {item.meeting_due && item.meeting_days_since !== null && (
                        <span className="due due-warn"> D+{item.meeting_days_since}</span>
                      )}
                    </td>
                  )}
                  {cols.followups && <td className={item.open_followups ? "num" : "zero num"}>{cellCount(item.open_followups)}</td>}
                </tr>
              ))}
            </tbody>
            {/* 사람별 참여 기록을 더한다 — 한 행사에 여럿이 가면 사람마다 한 건이라 *행사* 수와는 다르다 (TODO 157) */}
            <TotalRow
              label={`합계 (${summary.people.length}명)`}
              cells={[
                cellCount(sumBy(summary.people, (item) => item.count)),
                ...shownKinds.map((kindInfo) =>
                  cellCount(sumBy(summary.people, (item) => item.by_kind[kindInfo.key] ?? 0)),
                ),
                ...(cols.hours
                  ? [(() => {
                      const hours = sumBy(summary.people, (item) => item.hours);
                      return hours ? `${Math.round(hours * 10) / 10}h` : DASH;
                    })()]
                  : []),
                ...(cols.cost
                  ? [(() => {
                      const cost = sumBy(summary.people, (item) => item.cost);
                      return cost ? won(cost) : DASH;
                    })()]
                  : []),
                null,
                null,
                ...(cols.meeting ? [null] : []),
                ...(cols.followups ? [cellCount(sumBy(summary.people, (item) => item.open_followups))] : []),
              ]}
            />
          </table>
        </div>
        )}
        {summary.people.length > 0 && (
          <>
            {hiddenCols.length > 0 && (
              <p className="hint hidden-cols">숨긴 열: {hiddenCols.join(" · ")} — 이 표에서 모두 비어 있습니다.</p>
            )}
            <Explain id="skills-people" lead={<><b>기록</b>은 참여 건수이고, 한 행사에 여럿이 가면 사람마다 한 건씩 잡힙니다. 이름을 누르면 그 사람의 기록으로 갑니다.</>}>
              추이 막대는 {summary.trend_years.join(" · ") || "—"}년이며 <b>연도 조건을 따르지 않습니다</b> —
              과거를 봐야 다음을 이야기할 수 있기 때문입니다. 시간·비용에 마우스를 올리면 그 합계가
              몇 건에서 나온 값인지 보입니다.
            </Explain>
          </>
        )}
      </div>
        </>
      )}

      {/* ── 면담 (TODO 182) — 사람을 고르면 그 사람의 면담, 아니면 팀 전체의 하기로 한 것. 읽기 전용 공유에선 탭째 없다 (191).
            떠난 사람과는 새 면담을 잡지 않는다 (194) — 지난 면담은 그 사람을 고르면 그대로 보인다 ── */}
      {tab === "meetings" && !readonly && <MeetingPanel
        meta={meta}
        person={person}
        // 떠난 날이 오늘 이후면 아직 있는 사람이다 — 전배 예정자와도 면담한다 (TODO 214 D8)
        people={summary.people
          .filter((item) => !item.left || (item.left_on ? !isDeparted({ left_on: item.left_on }) : false))
          .map((item) => item.name)
          .filter((name) => splitPeople(name).length === 1)}
        onChanged={load}
        onPickPerson={setPerson}
      />}

      {/* ── 기록 목록 ──────────────────────────────────────────────── */}
      {tab === "records" && (
      <div className="card wide skills-records">
        <div className="card-head">
          <h2>
            행사 {allEvents}건
            <span className="hint"> · 참여 기록 {rows.length}건</span>
            {person && <span className="hint"> · {person}</span>}
          </h2>
          <div className="filters">
            <select value={person} onChange={(event) => setPerson(event.target.value)} aria-label="사람">
              <option value={ALL}>사람 전체</option>
              {peopleRows.map((item) => (
                <option key={item.name} value={item.name}>
                  {item.name}{item.left ? ` · ${leftLabel(meta, item.name) || "떠남"}` : ""}
                </option>
              ))}
            </select>
            <select value={when} onChange={(event) => setWhen(event.target.value)} aria-label="예정 · 지난 것">
              <option value="">예정 · 지난 것 모두</option>
              <option value="planned">예정만</option>
              <option value="past">지난 것만</option>
            </select>
            <select value={kind} onChange={(event) => setKind(event.target.value)} aria-label="구분">
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
          <>
            {/* 예정 — 가까운 것부터, 남은 날 띠지와 함께 (TODO 232 ⑥) */}
            {plannedEvents.length > 0 && (
              <div className="activity-section activity-planned-section">
                <h3>
                  예정 {plannedEvents.length}건 <span className="hint">· 가까운 것부터 · 숫자에는 그날이 지나야 듭니다</span>
                </h3>
                <ul className="activity-list">
                  {(plannedAll ? plannedEvents : plannedEvents.slice(0, PLANNED_PAGE)).map((group) => eventRow(group, true))}
                </ul>
                {plannedEvents.length > PLANNED_PAGE && (
                  <div className="activity-more">
                    <button className="ghost small" onClick={() => setPlannedAll((on) => !on)}>
                      {plannedAll ? "예정 접기" : `예정 ${plannedEvents.length - PLANNED_PAGE}건 더 보기`}
                    </button>
                  </div>
                )}
              </div>
            )}
            {/* 지난 기록 — 최근 것부터, 달 머리줄 (TODO 227) */}
            {events.length > 0 && (
              <div className="activity-section activity-past-section">
                {plannedEvents.length > 0 && (
                  <h3>
                    지난 기록 — 행사 {events.length}건 <span className="hint">· 참여 기록 {pastRows.length}건 · 최근 것부터</span>
                  </h3>
                )}
                <ul className="activity-list">
                  {events.slice(0, shown).map((group, index, visible) => {
                    const first = group[0];
                    // 달이 바뀌는 자리에 머리줄 (TODO 227) — 길어도 어디쯤인지 보인다. 그 달의 행사 수는 자르기 전 전체에서 센다
                    const month = first.date.slice(0, 7);
                    const monthHead = index === 0 || visible[index - 1][0].date.slice(0, 7) !== month;
                    return (
                      <Fragment key={first.event_key}>
                        {monthHead && (
                          <li className="activity-month" aria-hidden="true">
                            {month.slice(0, 4)}년 {Number(month.slice(5, 7))}월
                            <span className="muted"> · 행사 {events.filter((item) => item[0].date.slice(0, 7) === month).length}건</span>
                          </li>
                        )}
                        {eventRow(group, false)}
                      </Fragment>
                    );
                  })}
                </ul>
                {events.length > shown && (
                  <div className="activity-more">
                    <button className="ghost" onClick={() => setShown((value) => value + EVENT_PAGE)}>
                      더 보기 — 남은 행사 {events.length - shown}건
                    </button>
                    <button className="ghost small" onClick={() => setShown(events.length)}>
                      모두 보기
                    </button>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
      )}
      </div>
    </section>
  );
}
