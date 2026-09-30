import { useState } from "react";
import { api } from "../api";
import { attempt } from "../notify";

/**
 * 읽지 못한 파일 · 값 (TODO 164) — 홈 · 과제목록 위쪽에 **늘** 선다.
 *
 * 전에는 켤 때의 검은 창과 과제목록 [다시 읽기] 를 눌렀을 때만 보였다. 탐색기로 날짜 하나를 잘못
 * 고치면 과제가 목록에서 사라지는데, 사용자는 왜인지 알 길이 없었다. 이제 값 하나가 틀리면 그 값만
 * 비우고(과제는 선다) 여기에 적는다. 파일을 고치고 [다시 읽기] 를 누르면 사라진다.
 */
export default function ProblemsBanner({
  problems,
  onReindexed,
}: {
  problems: { path: string; reason: string }[];
  onReindexed: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  if (problems.length === 0) return null;
  const unreadable = problems.filter((item) => !item.reason.includes("날짜로 읽지 못해")).length;
  return (
    <div className="card problems problems-banner">
      <div className="card-head">
        <h2>
          읽지 못한 파일 · 값 {problems.length}건
          {unreadable > 0 && <span className="hint"> · 그중 파일 째로 못 읽은 것 {unreadable}건</span>}
        </h2>
        <div className="card-head-actions">
          <button className="ghost small" onClick={() => setOpen((value) => !value)}>
            {open ? "접기" : "무엇인지 보기"}
          </button>
          <button
            className="ghost small"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              if (await attempt(() => api.reindex())) onReindexed();
              setBusy(false);
            }}
          >
            {busy ? "읽는 중…" : "다시 읽기"}
          </button>
        </div>
      </div>
      {open && (
        <>
          <p className="hint">
            탐색기 · 다른 편집기로 고친 파일입니다. 값 하나가 틀리면 <b>그 값만 비우고</b> 나머지는 그대로 보입니다.
            파일 맨 위의 설정(front matter)을 고친 뒤 [다시 읽기] 를 누르세요.
          </p>
          <ul className="problem-list">
            {problems.map((problem, index) => (
              <li key={`${problem.path}-${index}`}>
                <code>{problem.path}</code>
                <span className="muted">{problem.reason}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
