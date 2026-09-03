import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { Meta, ReportHistoryItem } from "../types";

/**
 * 보고 이력 찾기.
 *
 * 보고 문서는 과제 폴더마다 흩어져 쌓인다. 그래서 "그 회의체에 마지막으로 뭘 보고했더라"를
 * 확인하려면 과제를 하나씩 열어 봐야 했다. 여기서는 과제를 가로질러 한 번에 훑는다.
 *
 * 거르는 기준은 실제로 찾을 때 쓰는 셋뿐이다 — **피보고자·기간·검색어**.
 * 기준을 늘리면 화면만 복잡해지고, 정작 쓰는 것은 이 셋이다.
 */
export default function ReportHistory({ meta }: { meta: Meta }) {
  const [audience, setAudience] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [q, setQ] = useState("");
  const [state, setState] = useState("");
  const [items, setItems] = useState<ReportHistoryItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .searchReports({ audience, from, to, q, state })
      .then(setItems)
      .catch((err: Error) => setError(err.message));
  }, [audience, from, to, q, state]);

  // 조건을 고르는 대로 바로 반영한다. 다만 검색어는 타자를 멈춘 뒤에 — 글자마다 부르면 낭비다.
  useEffect(() => {
    const timer = window.setTimeout(load, q ? 250 : 0);
    return () => window.clearTimeout(timer);
  }, [load, q]);

  const filtered = Boolean(audience || from || to || q || state);

  return (
    <section className="report-history">
      <div className="card">
        <div className="card-head">
          <h2>보고 이력</h2>
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
            <input type="date" value={from} onChange={(event) => setFrom(event.target.value)} />
          </label>
          <label>
            기간 끝
            <input type="date" value={to} onChange={(event) => setTo(event.target.value)} />
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
          {filtered && (
            <button
              className="ghost small"
              onClick={() => {
                setAudience("");
                setFrom("");
                setTo("");
                setQ("");
                setState("");
              }}
            >
              조건 지우기
            </button>
          )}
        </div>
      </div>

      {error && <p className="form-error">{error}</p>}
      {items === null && <p className="hint">불러오는 중…</p>}
      {items && items.length === 0 && (
        <p className="empty">
          {filtered ? "조건에 맞는 보고가 없습니다." : "아직 만든 보고가 없습니다."}
        </p>
      )}

      <ol className="history-list">
        {items?.map((item) => (
          <li key={item.id} className={item.frozen ? "frozen" : "draft"}>
            {/* 보고 문서를 바로 열어 준다 — 찾는 이유가 대개 "그때 뭐라고 썼더라" 이기 때문 */}
            <a href={`#/projects/${item.project_id}?report=${item.id}`}>
              <span className="history-date">{item.report_date}</span>
              <span className="history-main">
                <span className="history-project">
                  <span className="project-id">{item.project_id}</span> {item.project_title}
                </span>
                <span className="history-excerpt">{item.excerpt || "(본문 없음)"}</span>
              </span>
              <span className="history-side">
                {item.audience && <span className="history-audience">{item.audience}</span>}
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
