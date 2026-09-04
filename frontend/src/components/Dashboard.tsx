import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { Dashboard as DashboardData } from "../types";

const OPEN_KEY = "md-mgmt:dashboard";
/** 리마인더를 닫은 날. 같은 날 다시 띄우지 않는다. */
const REMINDER_KEY = "md-mgmt:reminder-closed";
/** 담당 줄에 처음 세우는 사람 수. 넘치면 [+N명]으로 접어 둔다. */
const OWNER_CHIPS = 8;

interface Filters {
  status: string;
  type: string;
  owner: string;
  due: string;
  /** 목록과 같은 연도를 봐야 수와 목록이 어긋나지 않는다 (DESIGN 5.8). */
  year: string;
}

interface Props {
  /** 값이 바뀌면 다시 읽는다 (과제를 추가했거나 다시 읽기를 눌렀을 때). */
  refreshKey: number;
  filters: Filters;
  onFilter: (key: "status" | "type" | "owner" | "due" | "year", value: string) => void;
}

/**
 * 메인 상단 대시보드.
 *
 * 목적은 "지금 무엇을 봐야 하는가" 하나다. 그래서 지표를 늘리지 않고,
 * 모든 숫자는 누르면 그 조건으로 걸러진 목록으로 이어진다.
 * 이미 걸려 있는 조건을 다시 누르면 해제된다.
 */
/** 오늘 날짜 (YYYY-MM-DD). 리마인더를 "오늘 하루만" 닫아 두는 데 쓴다. */
function today(): string {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

export default function Dashboard({ refreshKey, filters, onFilter }: Props) {
  const [data, setData] = useState<DashboardData | null>(null);
  const [open, setOpen] = useState(() => localStorage.getItem(OPEN_KEY) !== "off");
  const [allOwners, setAllOwners] = useState(false);
  const [reminderClosed, setReminderClosed] = useState(() => localStorage.getItem(REMINDER_KEY));

  const load = useCallback(() => {
    // "all" 은 조건이 없는 것이다 (ProjectList 의 ALL_YEARS 와 같은 규칙).
    api.dashboard(filters.year === "all" ? "" : filters.year).then(setData).catch(() => setData(null));
  }, [filters.year]);

  useEffect(load, [load, refreshKey]);

  if (!data || data.total === 0) return null;

  const toggle = (key: "status" | "type" | "owner" | "due", value: string) =>
    onFilter(key, filters[key] === value ? "" : value);

  // 한 과제에 담당자가 여러 명일 수 있어 담당 칩의 합은 전체보다 클 수 있다.
  // 상태·속성 줄은 합이 딱 맞으므로, 다를 때만 그 사실을 밝혀 둔다.
  const ownerSum = data.owners.reduce((sum, item) => sum + item.count, 0);
  const shownOwners = allOwners ? data.owners : data.owners.slice(0, OWNER_CHIPS);
  const hiddenOwners = data.owners.length - shownOwners.length;

  // 오늘이 선정일·보고일이 아니면 reminder 는 null 이라 배너 자체가 없다.
  const reminder = data.reminder && reminderClosed !== today() ? data.reminder : null;

  return (
    <section className={`dashboard${open ? "" : " closed"}`}>
      {reminder && (
        <div className={`report-reminder ${reminder.phase}`}>
          <span className="reminder-mark">{reminder.phase === "report" ? "오늘 보고" : "오늘 선정"}</span>
          <span className="reminder-text">
            {reminder.phase === "report" ? (
              <>
                <b>{reminder.report_date} 보고하는 날</b>입니다.
                {reminder.drafts > 0
                  ? ` 초안 ${reminder.drafts}건이 확정을 기다리고 있습니다.`
                  : reminder.done > 0
                    ? ` ${reminder.done}건을 보고했습니다.`
                    : " 아직 만든 초안이 없습니다."}
              </>
            ) : (
              <>
                <b>내일({reminder.report_date}) 보고</b>입니다. 오늘 보고 대상을 고르세요.
                {reminder.pending > 0
                  ? ` 보고할 진행이 쌓인 과제 ${reminder.pending}건.`
                  : " 아직 새로 쌓인 진행일지가 없습니다."}
              </>
            )}
          </span>
          <a className="reminder-go" href="#/reports">
            보고 대상 보기 →
          </a>
          <button
            className="ghost small"
            title="오늘은 다시 띄우지 않습니다."
            onClick={() => {
              localStorage.setItem(REMINDER_KEY, today());
              setReminderClosed(today());
            }}
          >
            닫기
          </button>
        </div>
      )}
      {/* 연도로 걸러 두면 "작년에 시작해 아직 하고 있는 과제" 가 숨는다.
          흔한 일이라, 숨었다는 사실과 함께 보는 길을 준다 (TODO 67). */}
      {data.other_year_active > 0 && (
        <div className="dash-row hidden-note">
          <span className="dash-note">
            {data.year}년 밖에 있지만 <b>아직 진행 중인 과제 {data.other_year_active}건</b>이
            이 화면에서 빠져 있습니다.
          </span>
          <button className="dash-mini go" onClick={() => onFilter("year", "")}>
            연도 전체로 보기 →
          </button>
        </div>
      )}

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

          {data.owners.length > 0 && (
            <div className="dash-row">
              <span className="dash-label">
                담당
                {ownerSum > data.total && <span className="dash-note"> 중복 포함</span>}
              </span>
              <div className="dash-chips">
                {shownOwners.map((item) => (
                  <button
                    key={item.key}
                    className={`dash-chip type${filters.owner === item.key ? " on" : ""}`}
                    onClick={() => toggle("owner", item.key)}
                  >
                    {item.label} <b>{item.count}</b>
                  </button>
                ))}
                {hiddenOwners > 0 && (
                  <button className="dash-chip more" onClick={() => setAllOwners(true)}>
                    +{hiddenOwners}명
                  </button>
                )}
                {allOwners && data.owners.length > OWNER_CHIPS && (
                  <button className="dash-chip more" onClick={() => setAllOwners(false)}>
                    접기
                  </button>
                )}
              </div>
            </div>
          )}

          {data.candidates.length > 0 && (
            /* 목록 자체는 [보고 대상] 화면에 있다. 같은 자료를 두 곳에 세우면
               한쪽만 고쳐져 어긋나기 쉽다. 여기서는 길만 열어 둔다 (TODO 52). */
            <div className="dash-row dash-candidates">
              <span className="dash-label">{data.report_date} 보고</span>
              <a className="dash-mini go" href="#/reports">
                보고 대상 {data.candidates.length}건 보기 →
              </a>
            </div>
          )}

        </>
      )}
    </section>
  );
}
