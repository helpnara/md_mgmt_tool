import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { Dashboard as DashboardData } from "../types";

const OPEN_KEY = "md-mgmt:dashboard";

interface Filters {
  status: string;
  type: string;
  due: string;
}

interface Props {
  /** 값이 바뀌면 다시 읽는다 (과제를 추가했거나 다시 읽기를 눌렀을 때). */
  refreshKey: number;
  filters: Filters;
  onFilter: (key: "status" | "type" | "due", value: string) => void;
}

/**
 * 메인 상단 대시보드.
 *
 * 목적은 "지금 무엇을 봐야 하는가" 하나다. 그래서 지표를 늘리지 않고,
 * 모든 숫자는 누르면 그 조건으로 걸러진 목록으로 이어진다.
 * 이미 걸려 있는 조건을 다시 누르면 해제된다.
 */
export default function Dashboard({ refreshKey, filters, onFilter }: Props) {
  const [data, setData] = useState<DashboardData | null>(null);
  const [open, setOpen] = useState(() => localStorage.getItem(OPEN_KEY) !== "off");

  const load = useCallback(() => {
    api.dashboard().then(setData).catch(() => setData(null));
  }, []);

  useEffect(load, [load, refreshKey]);

  if (!data || data.total === 0) return null;

  const toggle = (key: "status" | "type" | "due", value: string) =>
    onFilter(key, filters[key] === value ? "" : value);

  return (
    <section className={`dashboard${open ? "" : " closed"}`}>
      <div className="dash-row">
        <button
          className="dash-fold"
          onClick={() => {
            const next = !open;
            setOpen(next);
            localStorage.setItem(OPEN_KEY, next ? "on" : "off");
          }}
          title={open ? "대시보드 접기" : "대시보드 펼치기"}
        >
          {open ? "▾" : "▸"} 과제 {data.total}건
        </button>

        {open && (
          <>
            <div className="dash-chips">
              {data.statuses.map((item) => (
                <button
                  key={item.key}
                  className={`dash-chip${filters.status === item.key ? " on" : ""}`}
                  onClick={() => toggle("status", item.key)}
                >
                  {item.label} <b>{item.count}</b>
                </button>
              ))}
            </div>

            <div className="dash-warn">
              {data.due_soon > 0 && (
                <button
                  className={`dash-mini warn${filters.due === String(data.due_soon_days) ? " on" : ""}`}
                  onClick={() => toggle("due", String(data.due_soon_days))}
                >
                  마감 임박 {data.due_soon}
                </button>
              )}
              {data.overdue > 0 && (
                <button
                  className={`dash-mini danger${filters.due === "overdue" ? " on" : ""}`}
                  onClick={() => toggle("due", "overdue")}
                >
                  기한 초과 {data.overdue}
                </button>
              )}
            </div>
          </>
        )}
      </div>

      {open && (
        <>
          <div className="dash-row">
            <span className="dash-label">속성</span>
            <div className="dash-chips">
              {data.types.map((item) => (
                <button
                  key={item.key}
                  className={`dash-chip type${filters.type === item.key ? " on" : ""}`}
                  onClick={() => toggle("type", item.key)}
                >
                  {item.label} <b>{item.count}</b>
                </button>
              ))}
            </div>
          </div>

          {data.candidates.length > 0 && (
            <div className="dash-candidates">
              <div className="dash-row">
                <span className="dash-label">{data.report_date} 보고 대상</span>
                <a className="dash-more" href="#/reports">
                  전체 보기 →
                </a>
              </div>
              <ol className="dash-list">
                {data.candidates.map((item) => (
                  <li key={item.id}>
                    <a href={`#/projects/${item.id}`}>
                      <span className="project-id">{item.id}</span>
                      <span className="dash-title">{item.title}</span>
                      <span className="dash-reason">
                        {item.never_reported ? (
                          <span className="never">보고 이력 없음</span>
                        ) : (
                          `마지막 보고 D+${item.days_since_report ?? 0}`
                        )}
                        {item.unreported_entries > 0 && (
                          <span className="accent"> · 미보고 {item.unreported_entries}건</span>
                        )}
                      </span>
                    </a>
                  </li>
                ))}
              </ol>
            </div>
          )}
        </>
      )}
    </section>
  );
}
