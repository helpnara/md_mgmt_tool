import { useRef, useState } from "react";
import { api } from "../api";
import type { RestoreReport, RestoreResult } from "../types";
import { formatBytes, uploadAttachment } from "../upload";
import CardIntro from "./CardIntro";

/**
 * 전체 백업에서 되살리기 (TODO 246) — 새 서버로 옮길 때.
 * 고르면 먼저 살펴보기(무엇이 든 백업인가 · 지금 데이터는 얼마나 바뀌나), [되살리기]는 그다음에.
 * 지금 데이터는 서버가 **먼저 통째로 백업**하고 바꾼다(합치지 않는다). 공유 바깥에는 끝점이 막혀 있고 설정 화면도 열리지 않는다.
 */
export default function RestoreCard() {
  const input = useRef<HTMLInputElement>(null);
  const [report, setReport] = useState<RestoreReport | null>(null);
  const [result, setResult] = useState<RestoreResult | null>(null);
  const [progress, setProgress] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setReport(null);
    setError(null);
    if (input.current) input.current.value = "";
  };

  const pick = async (file: File | undefined) => {
    if (!file) return;
    setReport(null);
    setResult(null);
    setError(null);
    setBusy(true);
    setProgress("올리는 중…");
    try {
      const handle = uploadAttachment<RestoreReport>("/api/backup/restore/inspect", file, (loaded, total) =>
        setProgress(loaded < total ? `올리는 중… ${formatBytes(loaded)} / ${formatBytes(total)}` : "살펴보는 중…"),
      );
      setReport(await handle.promise);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
      setProgress(null);
    }
  };

  const restore = async () => {
    if (!report?.token) return;
    const now = report.current;
    const question = now.has_data
      ? `지금 데이터(과제 ${now.projects}건 · 팀원 ${now.people}명 · 접수 ${now.intakes}건)가 이 백업의 내용으로 바뀝니다.\n\n` +
        "지금 데이터는 먼저 통째로 백업해 둡니다(자동 백업 폴더 · 없으면 데이터 폴더 옆). 되살릴까요?"
      : "이 백업으로 데이터 폴더를 채웁니다. 되살릴까요?";
    if (!window.confirm(question)) return;
    setBusy(true);
    setError(null);
    setProgress("되살리는 중… (첨부가 많으면 몇 분 걸립니다)");
    try {
      setResult(await api.restoreBackup(report.token));
      setReport(null);
      if (input.current) input.current.value = "";
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
      setProgress(null);
    }
  };

  return (
    <div className="card restore-card" data-restore-card>
      <h2>백업에서 되살리기</h2>
      <CardIntro id="restore">
        [전체 백업 내려받기]로 받은 zip 을 골라 데이터를 되살립니다 — 새 서버로 옮길 때. 지금 데이터와 <b>합치지 않고 바꾸며</b>,
        바꾸기 전에 지금 데이터를 먼저 통째로 백업해 둡니다.
      </CardIntro>
      <div className="form-actions">
        <label className={busy ? "button-like ghost disabled" : "button-like ghost"}>
          백업 파일 고르기…
          <input
            ref={input}
            type="file"
            accept=".zip,application/zip"
            hidden
            disabled={busy}
            aria-label="되살릴 백업 파일"
            onChange={(event) => void pick(event.target.files?.[0])}
          />
        </label>
        {progress && <span className="muted">{progress}</span>}
      </div>
      {error && <p className="error">{error}</p>}

      {report && (
        <div className="restore-report" data-restore-report>
          <table className="restore-table">
            <tbody>
              <tr>
                <th>파일</th>
                <td>
                  {report.filename} <span className="muted">({formatBytes(report.zip_bytes)})</span>
                </td>
              </tr>
              <tr>
                <th>백업 날짜</th>
                <td>{report.date ?? "알 수 없음"}</td>
              </tr>
              <tr>
                <th>든 것</th>
                <td>
                  과제 {report.projects}건 · 팀원 {report.people}명 · 접수 {report.intakes}건 · 첨부 {report.with_assets ? `${report.assets}개` : "없음(첨부 빼고 받은 백업)"}
                  {report.settings ? " · 설정" : " · 설정 없음"}
                </td>
              </tr>
              <tr>
                <th>지금 데이터</th>
                <td>{report.current.has_data ? `과제 ${report.current.projects}건 · 팀원 ${report.current.people}명 · 접수 ${report.current.intakes}건 — 바뀝니다` : "비어 있음"}</td>
              </tr>
            </tbody>
          </table>
          {report.wrapped && <p className="hint">zip 안의 「{report.wrapped}」 폴더 한 겹은 벗기고 되살립니다.</p>}
          {report.problems.length > 0 && (
            <ul className={report.ok ? "hint restore-problems" : "error restore-problems"}>
              {report.problems.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          )}
          <div className="form-actions">
            {report.ok && (
              <button className="ghost danger" disabled={busy} onClick={() => void restore()}>
                되살리기
              </button>
            )}
            <button className="ghost" disabled={busy} onClick={reset}>
              취소
            </button>
          </div>
        </div>
      )}

      {result && (
        <div className="notice restore-done" data-restore-done>
          <p>
            <b>되살렸습니다</b> — 과제 {result.projects}건 · 팀원 {result.people}명 · 접수 {result.intakes}건 (파일 {result.files}개).
          </p>
          {result.safety_backup && (
            <p className="hint">
              바꾸기 전 데이터는 <code>{result.safety_backup}</code> 에 두었습니다.
            </p>
          )}
          {result.backup_dir_missing && (
            <p className="warn-banner">
              자동 백업 폴더 <code>{result.backup_dir_missing}</code> 가 이 PC 에 없습니다 — 아래 [자동 백업]에서 다시 정해 주세요.
            </p>
          )}
          {result.problems.length > 0 && <p className="hint">읽지 못한 파일 {result.problems.length}건 — 과제목록 위쪽 안내를 확인하세요.</p>}
          <button onClick={() => window.location.reload()}>새로 불러오기</button>
        </div>
      )}
    </div>
  );
}
