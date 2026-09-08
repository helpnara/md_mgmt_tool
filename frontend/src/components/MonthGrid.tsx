import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { MonthGrid as GridData } from "../types";
import { projectLink } from "../nav";

/**
 * 과제 × 월 보고 표 (TODO 77).
 *
 * 처음에는 홈에 있었는데 **보고 이력 화면으로 옮겼다** (TODO 79).
 * 줄이 과제 수만큼 늘어나므로, 팀이 크면 홈의 "한눈에" 성격과 어긋난다 —
 * 50명 팀이면 과제가 수백 건이다. 여기서는 이 표가 주인공이라 길어도 괜찮다.
 *
 * 연도는 **위쪽 기간 조건에서 받아 온다.** 화면 하나에 연도 고르는 곳이 둘이면
 * 어느 쪽이 이기는지 매번 헷갈린다.
 */
const MONTHS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];
/** 한 칸에 세우는 보고 수. 넘치면 +N 으로 접는다 — 한 칸이 길어지면 그 줄만 키가 커진다. */
const CELL_LIMIT = 2;
const OPEN_KEY = "md-mgmt:month-grid";

/** 그 달의 보고 이력으로 가는 주소. 마지막 날은 달마다 다르므로 계산해서 쓴다. */
function monthLink(year: string, month: number): string {
  const mm = String(month).padStart(2, "0");
  const last = new Date(Number(year), month, 0).getDate();
  return `#/history?from=${year}-${mm}-01&to=${year}-${mm}-${last}`;
}

interface Props {
  year: string;
  /** 위쪽 기간 조건. 여기 든 보고는 표에서 **붉게** 세운다 (TODO 93). */
  from?: string;
  to?: string;
}

export default function MonthGrid({ year, from = "", to = "" }: Props) {
  const [grid, setGrid] = useState<GridData | null>(null);
  const [gridOpen, setGridOpen] = useState(() => localStorage.getItem(OPEN_KEY) !== "off");
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => {
    try {
      localStorage.setItem(OPEN_KEY, gridOpen ? "on" : "off");
    } catch {
      /* 사생활 보호 모드 등 — 접힘 상태를 기억 못 할 뿐이다 */
    }
  }, [gridOpen]);

  const load = useCallback(() => {
    api.monthGrid(year).then(setGrid).catch(() => setGrid(null));
  }, [year]);

  useEffect(load, [load]);

  /**
   * 표시한 칸이 화면 밖에 있으면 가로로 밀어 준다 (TODO 93).
   *
   * 열두 달이 좁은 화면(1366×768, 125%)에는 다 안 들어간다. 9월 것을 붉게 칠해 놓아도
   * 그 열이 오른쪽 밖이면 여전히 찾아야 한다. **세로는 건드리지 않는다** —
   * 화면을 옮기면 맨 위에서 시작한다는 규칙과 부딪친다.
   */
  useEffect(() => {
    const box = scroller.current;
    if (!box || (!from && !to)) return;
    const cell = box.querySelector(".month-cell.marked");
    if (!cell) return;
    const target = cell.getBoundingClientRect();
    const view = box.getBoundingClientRect();
    if (target.left >= view.left && target.right <= view.right) return;
    box.scrollLeft += target.left - view.left - (view.width - target.width) / 2;
  }, [from, to, grid, gridOpen]);

  /**
   * 위쪽 기간 조건에 든 보고인가 (TODO 93).
   *
   * 기간을 안 걸었으면 아무것도 표시하지 않는다 — 온통 붉으면 표시가 아니다.
   * 한쪽만 걸어도 (그날 이후 / 그날까지) 그대로 통한다.
   */
  function inRange(date: string): boolean {
    if (!from && !to) return false;
    return (!from || date >= from) && (!to || date <= to);
  }

  /** 기간에 든 것을 앞으로. 나머지 순서는 그대로 둔다 (날짜순). */
  function order<T extends { date: string }>(reports: T[]): T[] {
    if (!from && !to) return reports;
    return [...reports.filter((r) => inRange(r.date)), ...reports.filter((r) => !inRange(r.date))];
  }

  if (!grid || grid.projects.length === 0) return null;

  // 과제 → 달 → 그 달의 보고들. 열두 칸으로 나누는 일은 화면 몫이다 (서버는 목록만 준다).
  type Report = GridData["reports"][number];
  type Months = Map<number, Report[]>;
  const noReports: Months = new Map();
  const byProject = new Map<string, Months>();
  const monthTotals: Record<number, number> = {};
  let marked = 0;
  for (const report of grid.reports) {
    const month = Number(report.date.slice(5, 7));
    monthTotals[month] = (monthTotals[month] ?? 0) + 1;
    if (inRange(report.date)) marked += 1;
    if (!byProject.has(report.project_id)) byProject.set(report.project_id, new Map());
    const months = byProject.get(report.project_id)!;
    months.set(month, [...(months.get(month) ?? []), report]);
  }

  return (
    <div className="card month-card wide">
        <div className="card-head">
          <h2>
            과제별 보고 — {year}년
            <span className="hint"> · 확정된 보고 {grid.reports.length}건</span>
            {(from || to) && (
              <span className="month-marked-count">
                기간에 든 보고 {marked}건
              </span>
            )}
          </h2>
          <button className="ghost small" onClick={() => setGridOpen((prev) => !prev)}>
            {gridOpen ? "접기" : "펼치기"}
          </button>
        </div>
        {gridOpen && (
          <>
            <div className="table-scroll" ref={scroller}>
              <table className="grid month-grid">
                <thead>
                  <tr>
                    <th className="month-name">과제</th>
                    {MONTHS.map((month) => (
                      <th key={month}>
                        {month}월
                        {monthTotals[month] > 0 && (
                          <span className="th-unit">{monthTotals[month]}건</span>
                        )}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {grid.projects.map((project) => {
                    const mine = byProject.get(project.id) ?? noReports;
                    return (
                      <tr key={project.id} className={mine.size ? undefined : "quiet-row"}>
                        <td className="month-name">
                          <a href={projectLink(project.id)} title={project.title}>
                            {project.title}
                          </a>
                          <span className="project-id">{project.id}</span>
                        </td>
                        {MONTHS.map((month) => {
                          // 기간에 든 것을 **앞으로 당긴다.** 한 칸에 두 건까지만 세우므로,
                          // 그대로 두면 정작 찾는 그 한 건이 +N 밑에 숨는 일이 생긴다.
                          const cell = order(mine.get(month) ?? []);
                          const hitCount = cell.filter((report) => inRange(report.date)).length;
                          const hidden = cell.slice(CELL_LIMIT);
                          return (
                            <td
                              key={month}
                              className={
                                (cell.length ? "month-cell" : "month-cell zero") +
                                (hitCount ? " marked" : "")
                              }
                            >
                              {cell.slice(0, CELL_LIMIT).map((report) => {
                                const hit = inRange(report.date);
                                return (
                                  <a
                                    key={report.id}
                                    className={hit ? "month-hit marked" : "month-hit"}
                                    href={projectLink(project.id, { report: report.id })}
                                    title={`${report.date}${report.audience ? ` · ${report.audience}` : ""} — 그때 보고한 내용 열기${hit ? " (지금 거른 기간에 든 보고입니다)" : ""}`}
                                  >
                                    <span className="month-date">
                                      {/* 색만으로 알리지 않는다 — 흑백으로 뽑아도 표가 남는다 */}
                                      {hit && <span className="month-flag" aria-hidden="true">●</span>}
                                      {report.date.slice(5)}
                                    </span>
                                    {report.audience && (
                                      <span className="month-audience">{report.audience}</span>
                                    )}
                                  </a>
                                );
                              })}
                              {hidden.length > 0 && (
                                <a
                                  className={
                                    hidden.some((report) => inRange(report.date))
                                      ? "month-more marked"
                                      : "month-more"
                                  }
                                  href={monthLink(year, month)}
                                  title="이 달의 보고 이력을 모두 봅니다"
                                >
                                  +{hidden.length}
                                </a>
                              )}
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="hint">
              <b>확정된 보고만</b> 셉니다 — 초안은 아직 보고한 것이 아닙니다. 칸을 누르면 그 과제의
              그 보고가 열립니다. 줄은 <b>{year}년 번호의 과제</b>와 <b>{year}년에 보고가 있었던 과제</b>를
              합친 것이라, 지난해 번호 과제라도 그해 보고했다면 함께 섭니다.
              한 줄이 통째로 비어 있으면 <b>그해 한 번도 보고하지 않은 과제</b>입니다.
              {(from || to) && (
                <>
                  {" "}위에서 거른 <b>기간에 든 보고</b>는 <span className="month-legend">●&nbsp;붉게</span>{" "}
                  칠하고 칸 맨 앞으로 당겨 두었습니다 — 나머지 파란 칸은 같은 해의 다른 보고입니다.
                </>
              )}
              {grid.skipped > 0 && (
                <>
                  {" "}<b>별도 보고 불필요</b>로 표시한 과제 {grid.skipped}건은 이 표에서 빠져 있습니다 —
                  빈 줄로 세우면 관리 공백처럼 읽히기 때문입니다.
                </>
              )}
            </p>
          </>
        )}
    </div>
  );
}
