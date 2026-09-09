import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { api } from "../api";
import type { Home as HomeData, HomeSlice, Meta } from "../types";
import { projectLink } from "../nav";
import { effectNumber } from "../util";
import LoadError from "./LoadError";

/**
 * 홈(첫 화면) — TODO 56 · ROADMAP R1.
 *
 * 대시보드가 "지금 무엇을 봐야 하는가"라면 홈은 **"우리 팀이 올해 무엇을 했는가"**다.
 *
 * 지키는 것 셋.
 *  1. **모든 수는 눌러서 그 조건의 목록으로 이어진다** (DESIGN 5.8). 이어지지 않는 수는 넣지 않는다.
 *  2. **기대효과와 실증효과를 절대 합치지 않는다.** 합쳐 놓으면 "그거 확정된 숫자입니까"에 답할 수 없다.
 *  3. **담당 중복을 숨기지 않는다.** 사람별로 더하면 팀 합계를 넘는다. 그 사실을 글자로 적는다.
 */

const ALL_YEARS = "all";
/** 억원/년. 목록·과제 상세와 **같은 규칙**으로 적는다 (util.ts effectNumber, TODO 76). */
function money(value: number): string {
  return value ? effectNumber(value) : "—";
}

/**
 * 상태 여섯 칸 (예정·검토중·진행중·보류·완료·중단).
 *
 * **순서는 `meta.statuses` 를 그대로 따른다.** 화면에 순서를 다시 적으면 나중에 상태를
 * 하나 더할 때 두 곳이 어긋난다. 팀원별·속성별 두 표가 이 부품을 나눠 쓰므로,
 * 한 화면에서 같은 것을 다르게 세는 일이 생기지 않는다 (TODO 75).
 */
function StatusHead({ meta }: { meta: Meta }) {
  return (
    <>
      {meta.statuses.map((status) => (
        <th key={status.key}>{status.label}</th>
      ))}
    </>
  );
}

function StatusCells({
  meta,
  counts,
  link,
}: {
  meta: Meta;
  counts: Record<string, number>;
  /** 그 칸이 가리킬 목록 주소. 0 인 칸은 갈 곳이 없으므로 링크를 걸지 않는다. */
  link: (statusKey: string) => string;
}) {
  return (
    <>
      {meta.statuses.map((status) => {
        const count = counts?.[status.key] ?? 0;
        return (
          // 0 은 흐리게. 어디가 비었는지가 이 표의 요점이다.
          <td key={status.key} className={count ? undefined : "zero"}>
            {count ? <a href={link(status.key)}>{count}</a> : 0}
          </td>
        );
      })}
    </>
  );
}

function listLink(params: Record<string, string>): string {
  const query = new URLSearchParams(Object.entries(params).filter(([, v]) => v));
  const text = query.toString();
  return `#/projects${text ? `?${text}` : ""}`;
}

/** 그룹 표는 자유 입력이라 길어질 수 있다. 이만큼만 세우고 나머지는 접는다. */
const SLICE_LIMIT = 8;

/**
 * 속성별·그룹별 표 (TODO 90).
 *
 * 두 표가 **같은 부품**을 쓴다. 따로 짜면 언젠가 한쪽만 고치게 되고,
 * 같은 화면의 두 표가 다르게 세기 시작한다 (팀원별·속성별에서 배운 것, TODO 75).
 */
function SliceTable({
  meta,
  title,
  column,
  rows,
  param,
  yearParam,
  note,
}: {
  meta: Meta;
  title: string;
  /** 첫 열의 이름 — "속성" 또는 "그룹" */
  column: string;
  rows: HomeSlice[];
  /** 목록을 거를 때 쓸 질의 이름 */
  param: "type" | "group";
  yearParam: string;
  note: ReactNode;
}) {
  const [all, setAll] = useState(false);
  if (rows.length === 0) return null;
  const shown = all ? rows : rows.slice(0, SLICE_LIMIT);
  const link = (item: HomeSlice, status?: string) =>
    listLink({ [param]: item.key, ...(status ? { status } : {}), year: yearParam });

  return (
    // 속성별과 그룹별을 이름으로 가려낼 수 있어야 한다 — 시험이 둘을 헷갈리면
    // 어느 표를 보고 있는지 모른 채 통과할 수 있다.
    <div className={`card home-types home-slice-${param}`}>
      <h2>{title}</h2>
      <div className="table-scroll">
        <table className="grid home-member-table">
          <thead>
            <tr>
              <th>{column}</th>
              <th>과제</th>
              <StatusHead meta={meta} />
              <th>
                기대효과<span className="th-unit">억원/년</span>
              </th>
              <th>
                실증효과<span className="th-unit">억원/년</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {shown.map((item) => (
              <tr key={item.key}>
                <td>
                  <a href={link(item)}>{item.label}</a>
                </td>
                <td>{item.count}</td>
                <StatusCells
                  meta={meta}
                  counts={item.by_status}
                  link={(status) => link(item, status)}
                />
                <td>{money(item.effect_expected)}</td>
                <td>{money(item.effect_verified)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length > SLICE_LIMIT && (
        <button type="button" className="ghost small" onClick={() => setAll((on) => !on)}>
          {all ? "접기" : `나머지 ${rows.length - SLICE_LIMIT}개 더 보기`}
        </button>
      )}
      <p className="hint">{note}</p>
    </div>
  );
}

export default function Home({ meta }: { meta: Meta }) {
  const thisYear = String(new Date().getFullYear());
  const [year, setYear] = useState(thisYear);
  const [data, setData] = useState<HomeData | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .home(year === ALL_YEARS ? "" : year)
      .then((next) => {
        setData(next);
        setError(null);
      })
      .catch((err: Error) => setError(err.message));
  }, [year]);

  useEffect(load, [load]);

  if (error) return <LoadError message={error} onRetry={load} />;
  if (!data) return <p className="hint">불러오는 중…</p>;

  const yearParam = year === ALL_YEARS ? "" : year;
  const { team, this_week: week } = data;

  // ── 아직 아무것도 없을 때 ──────────────────────────────────────────
  // 0 이 여덟 개 늘어선 대시보드는 처음 켠 사람에게 아무것도 알려 주지 않는다.
  // 이 도구는 다른 팀장에게 배포해 쓰는 것이 목표라, **첫 5분이 곧 채택 여부**다.
  // 과제가 하나도 없는 동안에는 지표 대신 **다음에 할 일**을 세운다 (TODO 84).
  if (data.years.length === 0 && team.total === 0) {
    return (
      <section className="home">
        <div className="card home-start">
          <h1>과제 이력 관리를 시작합니다</h1>
          <p className="hint">
            과제 하나가 폴더 하나입니다. 진행일지와 첨부가 그 안에 함께 쌓이고,
            모두 <b>보통의 마크다운 파일</b>이라 이 도구 없이도 탐색기에서 그대로 읽힙니다.
          </p>
          <ol className="home-steps">
            <li>
              <b>작성자와 담당자 명부를 정합니다</b>
              <span className="hint">
                진행일지·보고에 누가 썼는지 남고, 담당자 칸에서 이름을 눌러 넣게 됩니다.
              </span>
              <a className="home-step-go" href="#/settings">
                설정 열기 →
              </a>
            </li>
            <li>
              <b>첫 과제를 만듭니다</b>
              <span className="hint">
                제목만 있으면 됩니다. 상태·담당자·마감은 나중에 채워도 됩니다.
              </span>
              <a className="home-step-go primary" href="#/projects?new=1">
                과제 만들기 →
              </a>
            </li>
            <li>
              <b>진행일지를 씁니다</b>
              <span className="hint">
                과제 상세에서 [기록 추가]. 그림은 Ctrl+V, 엑셀 표는 붙여넣으면 표로 바뀝니다.
                기록이 쌓이면 보고 초안이 자동으로 만들어집니다.
              </span>
            </li>
          </ol>
          <p className="hint">
            과제가 하나라도 생기면 이 자리에 <b>그 해 팀 현황과 팀원별 성과</b>가 들어섭니다.
          </p>
        </div>
      </section>
    );
  }

  const memberSum = data.members.reduce((sum, item) => sum + item.total, 0);
  const maxCompare = Math.max(1, ...data.compare.map((item) => item.total));
  return (
    <section className="home">
      <div className="home-head">
        <h1>과제 수행 현황</h1>
        <label className="home-year">
          기준 연도
          <select value={year} onChange={(event) => setYear(event.target.value)}>
            {!data.years.includes(thisYear) && <option value={thisYear}>{thisYear}년</option>}
            {data.years.map((item) => (
              <option key={item} value={item}>
                {item}년
              </option>
            ))}
            <option value={ALL_YEARS}>전체</option>
          </select>
        </label>
      </div>

      {/* ── 이번 주 할 일 · 팀 현황 ───────────────────────────────────────
          홈을 매일 여는 이유는 지표가 아니라 "이번 주 할 일" 이다. 그래서 맨 위에 둔다.
          둘을 **나란히** 놓는다 — 세로로 쌓으면 오른쪽이 통째로 비고, 정작 중요한 것을
          보려고 스크롤해야 한다 (TODO 78). 좁은 화면에서는 다시 한 줄씩 선다. */}
      <div className="home-top">
      <div className="card home-week">
        <h2>
          이번 주 할 일
          <span className="hint"> · 보고 예정일 {week.report_date}</span>
        </h2>
        <div className="home-week-row">
          <a className="home-stat go" href="#/reports">
            <span className="home-stat-label">보고 대상</span>
            <strong>{week.candidates}건</strong>
          </a>
          <a
            className={week.overdue ? "home-stat go danger" : "home-stat go"}
            href={listLink({ due: "overdue", year: yearParam })}
          >
            <span className="home-stat-label">기한 초과</span>
            <strong>{week.overdue}건</strong>
          </a>
          <a
            className={week.due_soon ? "home-stat go warn" : "home-stat go"}
            href={listLink({ due: "7", year: yearParam })}
          >
            <span className="home-stat-label">마감 임박 (7일)</span>
            <strong>{week.due_soon}건</strong>
          </a>
          {/* 쓰다 만 보고 (TODO 101). 배너는 보고하는 날에만 뜨므로, 지난주에 쓰다 만
              것은 다음 보고일까지 아무 데도 보이지 않았다. 여기서 계속 들고 있는다. */}
          <a
            className={week.drafts_overdue ? "home-stat go danger" : "home-stat go"}
            href="#/reports"
            title="보고 대상 화면 맨 위의 [확정을 기다리는 초안] 으로 갑니다"
          >
            <span className="home-stat-label">작성 중인 보고</span>
            <strong>{week.drafts}건</strong>
          </a>
        </div>

        {week.drafts > 0 && (
          <>
            <p className="hint">
              <b>아직 확정하지 않은 보고</b> — 확정해야 보고 이력에 남고, 그 진행일지가
              미보고에서 빠집니다.
              {week.drafts_overdue > 0 && (
                <>
                  {" "}그중 <b className="warn-text">{week.drafts_overdue}건</b>은 보고일이
                  이미 지났습니다.
                </>
              )}
            </p>
            <ul className="home-drafts">
              {week.draft_items.map((item) => (
                <li key={item.id}>
                  {/* 이름을 적어 놓고 목록으로 보내면 그 한 건을 다시 찾아야 한다 (TODO 91) */}
                  <a href={projectLink(item.project_id, { report: item.id })}>
                    {item.project_title}
                  </a>
                  <span className={item.overdue_days > 0 ? "due due-danger" : "due"}>
                    {item.report_date}
                    {item.overdue_days > 0 && ` · D+${item.overdue_days}`}
                  </span>
                  {item.audience && <span className="muted">{item.audience}</span>}
                </li>
              ))}
            </ul>
            {week.drafts > week.draft_items.length && (
              <p className="hint">
                <a href="#/reports">
                  나머지 {week.drafts - week.draft_items.length}건도 보고 대상 화면에서 보기 →
                </a>
              </p>
            )}
          </>
        )}
        {week.stale.length > 0 && (
          <>
            <p className="hint">
              <b>오래 보고되지 않은 과제</b> — 이번 주에 할 일이라기보다, 이미 새어 나간 것입니다.
            </p>
            <ul className="home-stale">
              {week.stale.map((item) => (
                <li key={item.id}>
                  <a href={projectLink(item.id)}>{item.title}</a>
                  <span className="due due-danger">D+{item.days_since_report}</span>
                  <span className="muted">
                    {item.never_reported ? "보고 이력 없음" : `마지막 보고 ${item.last_reported_at}`}
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>

      {/* ── 팀 현황 ──────────────────────────────────────────────────── */}
      <div className="card home-team">
        <h2>{year === ALL_YEARS ? "전체" : `${year}년`} 팀 현황</h2>
        <div className="home-stats">
          <a className="home-stat" href={listLink({ year: yearParam })}>
            <span className="home-stat-label">과제</span>
            <strong>{team.total}건</strong>
          </a>
          <a className="home-stat" href={listLink({ status: "in_progress", year: yearParam })}>
            <span className="home-stat-label">진행중</span>
            <strong>{team.in_progress}건</strong>
          </a>
          <a className="home-stat" href={listLink({ status: "done", year: yearParam })}>
            <span className="home-stat-label">완료</span>
            <strong>{team.done}건</strong>
          </a>
          <a className="home-stat" href={`#/history${yearParam ? `?from=${yearParam}-01-01&to=${yearParam}-12-31` : ""}`}>
            <span className="home-stat-label">보고 횟수</span>
            <strong>{team.reports}회</strong>
          </a>
          {/* 화살표만 놓으면 "42.9 중 10.5 달성 = 24%" 로 읽힌다. 실증은 끝난 과제에서만
              나오므로 그 비율은 성립하지 않는다. **몇 건에서 나온 값인지**를 함께 적어
              분모를 드러낸다 (TODO 86). */}
          <div className="home-stat effect">
            <span className="home-stat-label">효과 금액 (억원/년)</span>
            <strong>
              기대 {money(team.effect_expected)}
              <span className="home-arrow"> → </span>
              실증 {money(team.effect_verified)}
            </strong>
            <span className="home-stat-note">
              기대 {team.effect_expected_projects ?? 0}건 · 실증 {team.effect_verified_projects ?? 0}건에
              입력됨 (전체 {team.total}건)
            </span>
          </div>
        </div>
        <p className="hint">
          과제 수·완료·효과 금액은 <b>과제 번호의 연도</b>로, 보고 횟수는 <b>보고한 날의 연도</b>로 셉니다.
          {" "}보고 횟수는 <b>확정된 보고</b>만 셉니다 — 초안은 아직 보고한 것이 아닙니다.
          {" "}<b>실증효과는 끝난 과제에서만 나오므로 기대 대비 달성률이 아닙니다.</b>
        </p>
      </div>
      </div>

      {/* ── 연도 비교 ────────────────────────────────────────────────
          한 해만 보면 늘고 있는지 줄고 있는지 알 수 없다. */}
      {data.compare.length > 1 && (
        <div className="card home-compare">
          <h2>연도별 추이</h2>
          <div className="bar-row">
            {data.compare.map((item) => (
              <a
                key={item.year}
                className={item.year === year ? "bar-col on" : "bar-col"}
                href={listLink({ year: item.year })}
                title={`${item.year}년 과제 ${item.total}건 · 완료 ${item.done}건 · 보고 ${item.reports}회`}
              >
                <span className="bar-value">{item.total}</span>
                <span className="bar" style={{ height: `${(item.total / maxCompare) * 100}%` }}>
                  <span
                    className="bar-done"
                    style={{ height: `${item.total ? (item.done / item.total) * 100 : 0}%` }}
                  />
                </span>
                <span className="bar-label">{item.year}</span>
              </a>
            ))}
          </div>
          <p className="hint">
            막대는 과제 수, 진한 부분이 <b>완료</b>입니다. 누르면 그 해 과제 목록으로 갑니다.
          </p>
        </div>
      )}

      {/* ── 팀원별 성과 (ROADMAP R1 의 실체) ───────────────────────── */}
      <div className="card home-members wide">
        <h2>팀원별 성과</h2>
        {data.members.length === 0 ? (
          <p className="hint">담당자가 지정된 과제가 없습니다.</p>
        ) : (
          <>
            <div className="table-scroll">
              <table className="grid home-member-table">
                <thead>
                  <tr>
                    <th>담당자</th>
                    <th>담당 과제</th>
                    <StatusHead meta={meta} />
                    <th>
                      기대효과
                      <span className="th-unit">억원/년</span>
                    </th>
                    <th>
                      실증효과
                      <span className="th-unit">억원/년</span>
                    </th>
                    <th>보고 횟수</th>
                    {/* 과제가 아니라 사람에게 쌓인 것. 면담 준비를 한 화면에서
                        끝내기 위해 여기 세운다 (TODO 89). */}
                    <th>역량 이력</th>
                    <th>마지막 보고</th>
                  </tr>
                </thead>
                <tbody>
                  {data.members.map((member) => (
                    <tr key={member.name}>
                      <td>
                        <a href={listLink({ owner: member.name, year: yearParam })}>{member.name}</a>
                      </td>
                      <td>{member.total}</td>
                      <StatusCells
                        meta={meta}
                        counts={member.by_status}
                        link={(status) => listLink({ owner: member.name, status, year: yearParam })}
                      />
                      <td>{money(member.effect_expected)}</td>
                      <td>{money(member.effect_verified)}</td>
                      <td>{member.reports}</td>
                      <td className={member.activities ? undefined : "zero"}>
                        {member.activities ? (
                          <a href={`#/skills?person=${encodeURIComponent(member.name)}${yearParam ? `&year=${yearParam}` : ""}`}>
                            {member.activities}
                          </a>
                        ) : (
                          0
                        )}
                      </td>
                      <td className="muted">{member.last_reported_at ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {/* 이 문구는 수가 어긋날 때만 띄우면 안 된다. 담당자 없는 과제가 중복분을
                상쇄해 **우연히 합이 맞는 순간**이 가장 위험하기 때문이다 — 그때야말로
                합계가 맞는 줄 알고 그대로 보고하게 된다. 그래서 늘 밝힌다. */}
            <p className="hint">
              <b>담당 중복 포함</b> — 한 과제에 담당자가 여럿이면 양쪽에 잡힙니다.
              {memberSum !== team.total && (
                <>
                  {" "}그래서 이 표의 합({memberSum}건)은 팀 과제 수({team.total}건)와 다릅니다.
                </>
              )}{" "}
              <b>효과 금액도 마찬가지로 중복 합산</b>되므로, 팀 합계는 위의 &ldquo;팀 현황&rdquo;에 있는
              과제 기준 숫자를 쓰십시오. <b>역량 이력</b>은 과제와 무관한 그 해 교육·세미나
              참여 건수입니다 — 눌러서 그 사람의 이력을 봅니다.
            </p>
          </>
        )}
      </div>

      {/* ── 속성별 · 그룹별 ─────────────────────────────────────────
          속성은 과제의 *성격*(R&D·투자…), 그룹은 *주제*(차세대전지·소재…)다.
          목록에는 두 필터가 다 있는데 홈에는 그룹 축만 없었다 (TODO 90).
          표 모양은 하나로 맞춘다 — 같은 화면에서 같은 것을 다르게 세지 않기 위해서다. */}
      <SliceTable
        meta={meta}
        title="속성별"
        column="속성"
        rows={data.types}
        param="type"
        yearParam={yearParam}
        note={
          <>
            과제마다 속성은 하나뿐이라 이 표의 합은 <b>팀 과제 수와 정확히 맞습니다.</b>
            (담당 중복이 있는 위쪽 팀원별 표와 다른 점입니다)
          </>
        }
      />

      <SliceTable
        meta={meta}
        title="그룹별"
        column="그룹"
        rows={data.groups}
        param="group"
        yearParam={yearParam}
        note={
          <>
            그룹은 <b>자유 입력</b>이라 표기가 흔들리면 줄이 갈라집니다. 과제마다 그룹은
            하나뿐이므로 이 표의 합도 <b>팀 과제 수와 맞습니다.</b>
          </>
        }
      />

    </section>
  );
}
