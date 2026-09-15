import { useState } from "react";
import { api } from "../api";
import { projectLink } from "../nav";
import type { LinkFixReport } from "../types";

const KIND_LABEL = { overview: "개요", entry: "진행일지", report: "보고" } as const;

/**
 * 깨진 첨부 링크 정리 (TODO 116).
 *
 * 114 이전에 넣은 `![이름](../assets/…/001-측정 결과.png)` 은 공백에서 끊겨 그림이 안 뜬다.
 * **먼저 세어 보여 주고**, 사용자가 누르면 한 번에 고친다. 확정된 보고는 기본으로 빼고,
 * 포함하겠다고 체크하면 함께 고친다. 저장 전 내용은 이전 버전에 남는다.
 */
export default function LinkFixCard() {
  const [includeFrozen, setIncludeFrozen] = useState(false);
  const [report, setReport] = useState<LinkFixReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function scan(withFrozen = includeFrozen) {
    setBusy(true);
    setError(null);
    try {
      setReport(await api.linkFixScan(withFrozen));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function apply() {
    if (!report || report.document_count === 0) return;
    const what = `문서 ${report.document_count}건의 링크 ${report.link_count}개를 고칩니다.${
      includeFrozen ? " 확정된 보고도 포함됩니다." : ""
    }\n저장 전 내용은 이전 버전에 남습니다. 진행할까요?`;
    if (!window.confirm(what)) return;
    setBusy(true);
    setError(null);
    try {
      setReport(await api.linkFixApply(includeFrozen));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card link-fix" data-testid="link-fix">
      <div className="card-head">
        <h2>첨부 링크 정리</h2>
        <div className="form-actions" style={{ margin: 0 }}>
          <button className="ghost small" disabled={busy} onClick={() => void scan()}>
            {report ? "다시 세기" : "점검하기"}
          </button>
          {report && !report.applied && report.document_count > 0 && (
            <button className="small" disabled={busy} onClick={() => void apply()}>
              고치기
            </button>
          )}
        </div>
      </div>

      <p className="hint">
        이름에 <b>공백이나 괄호</b>가 있는 첨부는 예전에 넣은 링크가 그 자리에서 끊겨 그림이
        안 뜹니다. 지금은 넣을 때 <code>&lt;…&gt;</code> 로 감싸므로 새 문서는 괜찮고, 이미 쌓인
        문서만 여기서 한 번에 고칩니다. 고치는 것은 <b>이 과제의 실제 첨부를 가리키는 링크뿐</b>이고,
        본문의 다른 글은 건드리지 않습니다.
      </p>

      <label className="check-label">
        <input
          type="checkbox"
          checked={includeFrozen}
          disabled={busy}
          onChange={(event) => {
            setIncludeFrozen(event.target.checked);
            if (report) void scan(event.target.checked);
          }}
        />
        확정된 보고도 포함
        <span className="hint">확정된 보고는 "그때 무엇을 보고했는가"라 기본으로 두지 않습니다.</span>
      </label>

      {error && <p className="form-error">{error}</p>}

      {report && (
        <div className="link-fix-result">
          {report.applied ? (
            <p className="hint notice">
              문서 {report.document_count}건의 링크 {report.link_count}개를 고쳤습니다.
              {report.document_count > 0 && " 이전 내용은 설정 → 이전 버전에 있습니다."}
            </p>
          ) : report.document_count === 0 ? (
            <p className="hint">
              고칠 링크가 없습니다.
              {report.skipped_frozen > 0 && ` (확정된 보고 ${report.skipped_frozen}건은 제외했습니다)`}
            </p>
          ) : (
            <p className="hint">
              <b>문서 {report.document_count}건 · 링크 {report.link_count}개</b>가 고쳐질 대상입니다.
              {report.skipped_frozen > 0 && ` 확정된 보고 ${report.skipped_frozen}건은 제외했습니다.`}
            </p>
          )}
          {report.documents.length > 0 && (
            <ul className="link-fix-list">
              {report.documents.map((doc) => (
                <li key={`${doc.project_id}/${doc.rel_path}`}>
                  <a href={projectLink(doc.project_id)}>
                    <span className="project-id">{doc.project_id}</span> {doc.project_title}
                  </a>
                  <span className="muted">
                    {KIND_LABEL[doc.kind]} · {doc.rel_path} · 링크 {doc.links}개
                    {doc.frozen && " · 확정됨"}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
