import { useCallback, useEffect, useState } from "react";
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

export default function MonthGrid({ year }: { year: string }) {
  const [grid, setGrid] = useState<GridData | null>(null);
  const [gridOpen, setGridOpen] = useState(() => localStorage.getItem(OPEN_KEY) !== "off");

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

  if (!grid || grid.projects.length === 0) return null;

  // 과제 → 달 → 그 달의 보고들. 열두 칸으로 나누는 일은 화면 몫이다 (서버는 목록만 준다).
  type Report = GridData["reports"][number];
  type Months = Map<number, Report[]>;
  const noReports: Months = new Map();
  const byProject = new Map<string, Months>();
  const monthTotals: Record<number, number> = {};
  for (const report of grid.reports) {
    const month = Number(report.date.slice(5, 7));
    monthTotals[month] = (monthTotals[month] ?? 0) + 1;
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
          </h2>
          <button className="ghost small" onClick={() => setGridOpen((prev) => !prev)}>
            {gridOpen ? "접기" : "펼치기"}
          </button>
        </div>
        {gridOpen && (
          <>
            <div className="table-scroll">
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
                          const cell = mine.get(month) ?? [];
                          return (
                            <td key={month} className={cell.length ? "month-cell" : "month-cell zero"}>
                              {cell.slice(0, CELL_LIMIT).map((report) => (
                                <a
                                  key={report.id}
                                  className="month-hit"
                                  href={projectLink(project.id, { report: report.id })}
                                  title={`${report.date}${report.audience ? ` · ${report.audience}` : ""} — 그때 보고한 내용 열기`}
                                >
                                  <span className="month-date">{report.date.slice(5)}</span>
                                  {report.audience && (
                                    <span className="month-audience">{report.audience}</span>
                                  )}
                                </a>
                              ))}
                              {cell.length > CELL_LIMIT && (
                                <a
                                  className="month-more"
                                  href={monthLink(year, month)}
                                  title="이 달의 보고 이력을 모두 봅니다"
                                >
                                  +{cell.length - CELL_LIMIT}
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
