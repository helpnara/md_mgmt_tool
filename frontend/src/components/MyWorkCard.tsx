import { useEffect, useState } from "react";
import { api } from "../api";
import { listLink, personLink, projectLink } from "../nav";
import type { Meta, MyWork } from "../types";
import StatusBadge from "./StatusBadge";

/**
 * 팀원의 내 할 일 (TODO 242 C1 · C2 · C3) — 팀원 PC 의 홈 [할 일] 자리. 팀장 PC 는 지금처럼 팀 중심(242-3).
 *
 * * 내 진행 과제 — 일지가 필요한 것 먼저, 그다음 마감이 가까운 것. 줄마다 [일지 쓰기] 로 새 일지 편집기가 열린 채 간다.
 * * **일지 쓸 때가 됐어요** — 진행중 · 검토중인데 마지막 일지가 2주를 넘었으면 흐린 안내(빨간 경고가 아니다).
 * * 팀장의 인정 한 줄 — 이 사람과 팀장에게만 보인다. 2주 안의 것은 "새" 딱지.
 * * 순위 · 다른 팀원과의 비교는 만들지 않는다(242 지키는 선).
 */
export default function MyWorkCard({ meta }: { meta: Meta }) {
  const [work, setWork] = useState<MyWork | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api.myWork().then(setWork).catch((err: Error) => setError(err.message));
  }, []);

  if (error) return <div className="card my-work"><p className="error">{error}</p></div>;
  if (!work) return <div className="card my-work"><p className="muted">불러오는 중…</p></div>;

  const stale = work.projects.filter((item) => item.stale).length;
  const dueText = (days: number | null) =>
    days === null ? null : days < 0 ? `마감 ${-days}일 지남` : days === 0 ? "오늘 마감" : `D-${days}`;

  return (
    <div className="card my-work" data-my-work>
      <h2>
        {work.name} 님의 할 일
        {stale > 0 && <span className="hint"> · 일지를 쓸 때가 된 과제 {stale}건</span>}
      </h2>

      {work.praises.length > 0 && (
        <div className="my-praise">
          <p className="hint">
            <b>팀장이 남긴 한 줄</b> — 나와 팀장에게만 보입니다.
          </p>
          <ul>
            {work.praises.map((item) => (
              <li key={`${item.project_id}-${item.praise_at}`}>
                {item.new && <span className="tag new-tag">새</span>}
                <span className="praise-text">“{item.praise}”</span>
                <a href={projectLink(item.project_id)} className="muted">{item.title}</a>
                {item.praise_at && <span className="muted"> · {item.praise_at}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      <p className="hint">
        <b>내 진행 과제 {work.projects.length}건</b> — 지금 담당인 끝나지 않은 과제. 진행중인데 일지가 {work.stale_days}일 넘게 없으면 알려 드립니다.
      </p>
      {work.projects.length === 0 ? (
        <p className="muted">지금 맡은 진행 과제가 없습니다.</p>
      ) : (
        <ul className="my-projects">
          {work.projects.map((item) => (
            <li key={item.id} className={item.stale ? "my-project stale" : "my-project"} data-project={item.id}>
              <StatusBadge status={item.status} meta={meta} />
              <a href={projectLink(item.id)} className="my-project-title">{item.title}</a>
              {item.role && <span className="muted">{item.role}</span>}
              <span className="grow" />
              <span className="muted my-last-entry">
                {item.last_entry ? `마지막 일지 ${item.days_since_entry === 0 ? "오늘" : `${item.days_since_entry}일 전`}` : "일지 없음"}
              </span>
              {dueText(item.days_left) && (
                <span className={item.days_left !== null && item.days_left < 0 ? "due due-danger" : item.days_left !== null && item.days_left <= 7 ? "due due-warn" : "due"}>
                  {dueText(item.days_left)}
                </span>
              )}
              <a className="button-link ghost small" href={projectLink(item.id, { draft: "entry-new" })}>
                일지 쓰기
              </a>
              {item.stale && (
                <span className="my-stale-note">
                  일지를 쓸 때가 됐어요 —{" "}
                  {item.last_entry ? `마지막 일지가 ${item.days_since_entry}일 전입니다` : `시작한 지 ${item.days_since_entry}일, 아직 일지가 없습니다`}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}

      {work.retro_due.length > 0 && (
        <>
          <p className="hint">
            <b>회고를 적을 과제 {work.retro_due.length}건</b> — 끝난 내 과제(1년 안) 가운데 회고(내가 한 일 · 결과)가 빈 것.
          </p>
          <ul className="home-stale home-retro">
            {work.retro_due.slice(0, 5).map((item) => (
              <li key={item.id}>
                <span className="due">완료 {item.completed_at}</span>
                <a href={projectLink(item.id, { retro: "me" })}>{item.title}</a>
              </li>
            ))}
          </ul>
        </>
      )}

      <p className="my-work-links">
        <a href={personLink(work.name)}>내 이력 →</a>
        <a href={listLink({ owner: work.name, year: "all" })}>내 과제 목록 →</a>
      </p>
    </div>
  );
}
