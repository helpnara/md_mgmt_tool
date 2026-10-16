import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { Meta, ReportHistoryItem } from "../types";
import { backTarget, projectLink, useAddressBar } from "../nav";
import LoadError from "./LoadError";
import MonthGrid from "./MonthGrid";
import { useLatest } from "../util";
import { DATE_MAX, DATE_MIN, orderProblem } from "../inputRules";

/**
 * 보고 이력 찾기.
 *
 * 보고 문서는 과제 폴더마다 흩어져 쌓인다. 그래서 "그 회의체에 마지막으로 뭘 보고했더라"를
 * 확인하려면 과제를 하나씩 열어 봐야 했다. 여기서는 과제를 가로질러 한 번에 훑는다.
 *
 * 거르는 기준은 실제로 찾을 때 쓰는 셋뿐이다 — **피보고자·기간·검색어**.
 * 기준을 늘리면 화면만 복잡해지고, 정작 쓰는 것은 이 셋이다.
 */
interface Props {
  meta: Meta;
  /** 주소에 실려 온 거른 조건. 보고를 열어 보고 돌아와도 그대로 살아 있다. */
  query: string;
}

export default function ReportHistory({ meta, query }: Props) {
  const initial = new URLSearchParams(query);
  const [audience, setAudience] = useState(() => initial.get("audience") ?? "");
  const [from, setFrom] = useState(() => initial.get("from") ?? "");
  const [to, setTo] = useState(() => initial.get("to") ?? "");
  const [q, setQ] = useState(() => initial.get("q") ?? "");
  const [state, setState] = useState(() => initial.get("state") ?? "");
  // 답하지 않은 지시가 적힌 보고만 (TODO 107). 주소에는 feedback=open 으로 실린다.
  const [feedback, setFeedback] = useState(() => initial.get("feedback") ?? "");
  // 어디서 왔는지 (TODO 128). 거르는 조건이 아니라 **돌아갈 곳**이라 서버로 보내지 않고,
  // 조건을 바꿔도 주소에 남아 있어야 한다.
  const [back] = useState(() => initial.get("back") ?? "");
  const [items, setItems] = useState<ReportHistoryItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  // 조건 · 검색어를 빨리 바꾸면 앞 요청이 늦게 올 수 있다 — 마지막 것만 (TODO 210 ①)
  const latest = useLatest();
  const load = useCallback(() => {
    const mine = latest();
    api
      .searchReports({ audience, from, to, q, state, feedback })
      .then((rows) => {
        if (!mine()) return;
        setItems(rows);
        setError(null);
      })
      .catch((err: Error) => mine() && setError(err.message));
  }, [audience, from, to, q, state, feedback, latest]);

  // 조건을 고르는 대로 바로 반영한다. 다만 검색어는 타자를 멈춘 뒤에 — 글자마다 부르면 낭비다.
  useEffect(() => {
    const timer = window.setTimeout(load, q ? 250 : 0);
    return () => window.clearTimeout(timer);
  }, [load, q]);

  // 고른 조건과 주소를 맞춘다. 자주 보는 조건은 즐겨찾기해 두어도 된다.
  useAddressBar("history", { audience, from, to, q, state, feedback, back }, (params) => {
    setAudience(params.get("audience") ?? "");
    setFrom(params.get("from") ?? "");
    setTo(params.get("to") ?? "");
    setQ(params.get("q") ?? "");
    setState(params.get("state") ?? "");
    setFeedback(params.get("feedback") ?? "");
  });

  const filtered = Boolean(audience || from || to || q || state || feedback);
  // 기간이 거꾸로면 말없이 0건을 보이지 않고 칸 옆에 알린다 (TODO 214 U3)
  const periodProblem = orderProblem(from, to, "기간 끝이 시작보다 앞섭니다 — 끝을 시작 뒤로 옮겨 주세요.");
  // 과제 × 월 표가 볼 연도. **기간 조건에서 받아 온다** — 화면 하나에 연도 고르는 곳이
  // 둘이면 어느 쪽이 이기는지 매번 헷갈린다 (TODO 79).
  const gridYear = (from || to || "").slice(0, 4) || String(new Date().getFullYear());

  return (
    <section className="report-history">
      {/* 홈에서 왔으면 돌아갈 길을 그린다 (TODO 128). 메뉴로 왔으면 그리지 않는다 —
          없는 길을 만들지 않는다. */}
      {back && (
        <a className="back" href={backTarget(back).href}>
          ← {backTarget(back).label}
        </a>
      )}
      <div className="page-head">
        <h1>보고이력</h1>
        <p className="hint page-desc">과제를 가로질러 지난 보고를 찾습니다 — 피보고자·기간·검색어. 과제 × 월 표에서 기간에 든 보고가 붉게 섭니다.</p>
      </div>
      <div className="card">
        <div className="card-head">
          <h2>찾을 조건</h2>
          {items && (
            <span className="hint">
              {filtered ? `조건에 맞는 보고 ${items.length}건` : `보고 ${items.length}건`}
            </span>
          )}
        </div>

        <div className="history-filters">
          <label>
            피보고자 · 회의체
            <input
              list="history-audiences"
              value={audience}
              onChange={(event) => setAudience(event.target.value)}
              placeholder="일부만 쳐도 됩니다"
            />
            <datalist id="history-audiences">
              {meta.audiences.map((name) => (
                <option key={name} value={name} />
              ))}
            </datalist>
          </label>
          <label>
            기간 시작
            <input
              type="date"
              value={from}
              min={DATE_MIN}
              max={to || DATE_MAX}
              onChange={(event) => setFrom(event.target.value)}
            />
          </label>
          <label>
            기간 끝
            <input
              type="date"
              value={to}
              min={from || DATE_MIN}
              max={DATE_MAX}
              onChange={(event) => setTo(event.target.value)}
              aria-invalid={periodProblem ? true : undefined}
            />
            {periodProblem && <span className="field-error history-period-error">{periodProblem}</span>}
          </label>
          <label>
            검색어
            <input
              type="search"
              value={q}
              onChange={(event) => setQ(event.target.value)}
              placeholder="과제명·제목·본문"
            />
          </label>
          <label>
            상태
            <select value={state} onChange={(event) => setState(event.target.value)}>
              <option value="">전체</option>
              <option value="frozen">확정된 보고</option>
              <option value="draft">작성 중인 초안</option>
            </select>
          </label>
          <label className="check-label">
            <input
              type="checkbox"
              checked={feedback === "open"}
              onChange={(event) => setFeedback(event.target.checked ? "open" : "")}
            />
            답하지 않은 지시만
          </label>
          {filtered && (
            <button
              className="ghost small"
              onClick={() => {
                setAudience("");
                setFrom("");
                setTo("");
                setQ("");
                setState("");
                setFeedback("");
              }}
            >
              조건 지우기
            </button>
          )}
        </div>
      </div>

      {/* 기간을 걸었으면 표에서도 그 보고들을 붉게 세운다 (TODO 93) — 배너의
          "오늘 보고한 N건 보기"도 결국 from=to=오늘인 기간 조건이라 같은 길로 풀린다. */}
      <MonthGrid year={gridYear} from={from} to={to} />

      {error && <LoadError message={error} onRetry={load} />}
      {items === null && <p className="hint">불러오는 중…</p>}
      {items && items.length === 0 && (
        <p className="empty">
          {periodProblem
            ? "기간이 거꾸로라 찾을 수 없습니다 — 위의 기간 끝을 고쳐 주세요."
            : filtered
              ? "조건에 맞는 보고가 없습니다."
              : "아직 만든 보고가 없습니다."}
        </p>
      )}

      <ol className="history-list">
        {items?.map((item) => (
          <li key={item.id} className={item.frozen ? "frozen" : "draft"}>
            {/* 보고 문서를 바로 열어 준다 — 찾는 이유가 대개 "그때 뭐라고 썼더라" 이기 때문 */}
            <a href={projectLink(item.project_id, { report: item.id })}>
              <span className="history-date">{item.report_date}</span>
              <span className="history-main">
                <span className="history-project">
                  <span className="project-id">{item.project_id}</span> {item.project_title}
                </span>
                <span className="history-excerpt">{item.excerpt || "(본문 없음)"}</span>
              </span>
              <span className="history-side">
                {item.audience && <span className="history-audience">{item.audience}</span>}
                {item.feedback_open && <span className="tag feedback-tag">지시 답 안 함</span>}
                <span className="muted">
                  {item.frozen ? "보고 완료" : "작성 중"} · 진행일지 {item.entry_count}건
                </span>
              </span>
            </a>
          </li>
        ))}
      </ol>
    </section>
  );
}
