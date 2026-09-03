import { useEffect, useState } from "react";
import { api } from "../api";
import type { ReportDiff as DiffData } from "../types";

/**
 * 지난 보고 대비 변경분.
 *
 * 보고 자리에서 가장 많이 받는 질문이 "지난주와 뭐가 달라졌나"다.
 * 확정된 보고는 그 시점 그대로 굳어 있으므로, 비교 상대는 **직전에 확정한 보고**다.
 * 초안끼리 비교하면 기준이 흔들린다.
 *
 * 안 바뀐 줄은 바뀐 줄 둘레만 남기고 접는다 — 전부 보여 주면 정작 달라진 곳이 묻힌다.
 */
export default function ReportDiff({ reportId }: { reportId: number }) {
  const [data, setData] = useState<DiffData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    setError(null);
    api.reportDiff(reportId).then(setData).catch((err: Error) => setError(err.message));
  }, [reportId]);

  if (error) return <p className="form-error">{error}</p>;
  if (!data) return <p className="hint">비교하는 중…</p>;
  if (!data.previous) {
    return <p className="hint">이 과제에서 이번이 첫 보고입니다. 비교할 지난 보고가 없습니다.</p>;
  }
  if (data.lines.length === 0) {
    return (
      <p className="hint">
        {data.previous.report_date} 보고와 <b>내용이 같습니다.</b>
      </p>
    );
  }

  return (
    <div className="report-diff">
      <p className="hint">
        <b>{data.previous.report_date}</b> 보고와 비교 · 추가 {data.added}줄 · 삭제 {data.removed}줄
      </p>
      <ol className="diff-lines">
        {data.lines.map((line, index) => (
          <li key={index} className={`diff-${line.kind}`}>
            <span className="diff-mark" aria-hidden="true">
              {line.kind === "add" ? "+" : line.kind === "del" ? "−" : ""}
            </span>
            {/* 빈 줄도 자리를 차지해야 앞뒤 관계가 보인다 */}
            <span className="diff-text">{line.text || " "}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
