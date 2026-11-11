import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { RestoreJob, RestoreReport, RestoreResult, RestoreStage } from "../types";
import { formatBytes, uploadRaw } from "../upload";
import CardIntro from "./CardIntro";
import { ArchiveRestore } from "lucide-react";
import IconTitle from "./IconTitle";
import { ProgressBar, progressText, seconds } from "./RunningLine";

const STAGE_LABEL: Record<RestoreStage, string> = {
  check: "백업 살펴보기",
  safety: "지금 데이터 먼저 백업",
  extract: "백업 풀기",
  swap: "데이터 폴더 바꾸기",
  index: "색인 다시 만들기",
};
const STAGE_UNIT: Record<RestoreStage, string> = { check: "", safety: "개 파일", extract: "개 파일", swap: "", index: "개 과제 폴더" };

type Upload = { name: string; loaded: number; total: number; started: number; abort: () => void };

/**
 * 전체 백업에서 되살리기 (TODO 246) — 새 서버로 옮길 때.
 * 고르면 먼저 살펴보기(무엇이 든 백업인가 · 지금 데이터는 얼마나 바뀌나), [되살리기]는 그다음에.
 * 지금 데이터는 서버가 **먼저 통째로 백업**하고 바꾼다(합치지 않는다). 공유 바깥에는 끝점이 막혀 있고 설정 화면도 열리지 않는다.
 *
 * 268 — 백업이 크면 몇 분 걸려 화면이 멈춘 듯했다(사용자 2026-11-11). 이제 ① 올리기: 막대 · % · 속도 · 남은 시간 · [올리기 그만두기]
 * ② 되살리기: 서버가 뒤에서 하고 단계(먼저 백업 → 풀기 → 바꾸기 → 색인)마다 n / N · 크기 · 남은 시간, 바꾸기 전에는 [그만두기].
 * 다른 화면에 갔다 와도 이어 보인다.
 */
export default function RestoreCard() {
  const input = useRef<HTMLInputElement>(null);
  const [report, setReport] = useState<RestoreReport | null>(null);
  const [result, setResult] = useState<RestoreResult | null>(null);
  const [upload, setUpload] = useState<Upload | null>(null);
  const [inspecting, setInspecting] = useState(false);
  const [job, setJob] = useState<RestoreJob | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const running = job?.state === "running";
  const busy = Boolean(upload) || inspecting || running;

  // 다른 화면에 갔다 와도 — 도는 되살리기를 이어 본다
  useEffect(() => {
    api.currentRestoreJob().then(({ job: now }) => now && now.state === "running" && setJob(now)).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!job || job.state !== "running") return;
    const timer = window.setInterval(() => {
      api.restoreJob(job.id).then(setJob).catch((err: Error) => { setJob(null); setError(err.message); });
    }, 1000);
    return () => window.clearInterval(timer);
  }, [job?.id, job?.state]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!job) return;
    if (job.state === "done" && job.result) {
      setResult(job.result);
      setReport(null);
      setNotice(null);
      if (input.current) input.current.value = "";
    }
    if (job.state === "cancelled") setNotice("되살리기를 그만두었습니다 — 지금 데이터는 그대로이고, 만들던 파일은 지웠습니다.");
    if (job.state === "error") setError(job.error);
  }, [job?.state]); // eslint-disable-line react-hooks/exhaustive-deps

  const reset = () => {
    setReport(null);
    setError(null);
    setNotice(null);
    if (input.current) input.current.value = "";
  };

  const pick = async (file: File | undefined) => {
    if (!file) return;
    setReport(null);
    setResult(null);
    setError(null);
    setNotice(null);
    setJob(null);
    const handle = uploadRaw<RestoreReport>("/api/backup/restore/inspect", file, (loaded, total) => {
      setUpload((now) => (now ? { ...now, loaded, total } : now));
      if (loaded >= total) setInspecting(true);
    });
    setUpload({ name: file.name, loaded: 0, total: file.size, started: Date.now(), abort: handle.abort });
    try {
      setReport(await handle.promise);
    } catch (err) {
      const message = (err as Error).message;
      if (message.includes("취소")) setNotice("올리기를 그만두었습니다.");
      else setError(message);
      if (input.current) input.current.value = "";
    } finally {
      setUpload(null);
      setInspecting(false);
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
    setError(null);
    setNotice(null);
    try {
      setJob(await api.startRestoreJob(report.token));
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const cancel = async () => {
    if (!job) return;
    try {
      setJob(await api.cancelRestoreJob(job.id));
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const spent = upload ? (Date.now() - upload.started) / 1000 : 0;
  const rate = upload && spent > 0 ? upload.loaded / spent : 0;
  const uploadEta = upload && rate > 0 && upload.loaded < upload.total ? (upload.total - upload.loaded) / rate : null;
  const jobRatio = job ? (job.bytes_total ? job.bytes_done / job.bytes_total : job.files_total ? job.files_done / job.files_total : null) : null;

  return (
    <div className="card restore-card" data-restore-card>
      <IconTitle icon={ArchiveRestore}>백업에서 되살리기</IconTitle>
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
      </div>
      {upload && (
        <div className="backup-progress" data-testid="restore-upload" aria-live="polite">
          <ProgressBar ratio={inspecting ? null : upload.total ? upload.loaded / upload.total : null} label="올리기" />
          <p className="muted">
            {inspecting
              ? `올렸습니다 — 무엇이 든 백업인지 살펴보는 중… (${formatBytes(upload.total)})`
              : `올리는 중 — ${upload.name} · ${formatBytes(upload.loaded)} / ${formatBytes(upload.total)} (${upload.total ? Math.floor((upload.loaded / upload.total) * 100) : 0}%)` +
                `${rate ? ` · ${formatBytes(rate)}/초` : ""} · 지난 시간 ${seconds(spent)}${uploadEta !== null ? ` · 남은 시간 약 ${seconds(uploadEta)}` : ""}`}
          </p>
          {!inspecting && (
            <div className="form-actions">
              <button className="ghost" onClick={() => upload.abort()}>올리기 그만두기</button>
            </div>
          )}
        </div>
      )}
      {job && job.state === "running" && (
        <div className="backup-progress" data-testid="restore-progress" aria-live="polite">
          <ol className="restore-stages">
            {job.stages.map((stage) => {
              const done = job.stages_done.includes(stage);
              const now = stage === job.stage;
              return (
                <li key={stage} className={now ? "now" : done ? "done" : ""}>
                  <span className="mark" aria-hidden>{done ? "✓" : now ? "▶" : "·"}</span>
                  {STAGE_LABEL[stage]}
                </li>
              );
            })}
          </ol>
          <ProgressBar ratio={jobRatio} label={STAGE_LABEL[job.stage]} />
          <p className="muted">
            {STAGE_LABEL[job.stage]} — {progressText({ ...job, phase: "", done: job.files_done, total: job.files_total }, STAGE_UNIT[job.stage])}
            {" "}(전체 지난 시간 {seconds(job.elapsed)})
          </p>
          <div className="form-actions">
            {job.cancellable ? (
              <button className="ghost danger" onClick={() => void cancel()}>그만두기</button>
            ) : (
              <span className="hint">데이터 폴더를 바꾸는 중이라 멈출 수 없습니다 — 곧 끝납니다.</span>
            )}
          </div>
        </div>
      )}
      {notice && <p className="hint notice">{notice}</p>}
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
