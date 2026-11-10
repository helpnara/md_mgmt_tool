import { useEffect, useRef, useState } from "react";
import { Download } from "lucide-react";
import { api } from "../api";
import { notifyError } from "../notify";
import type { BackupEstimate, BackupJob } from "../types";
import { formatBytes } from "../upload";
import CardIntro from "./CardIntro";
import IconTitle from "./IconTitle";

function seconds(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "—";
  const s = Math.round(value);
  return s >= 60 ? `${Math.floor(s / 60)}분 ${s % 60}초` : `${s}초`;
}

/**
 * 전체 백업 내려받기 — 진행을 보인다 (TODO 266).
 *
 * 예전에는 링크 하나라 서버가 zip 을 다 만들 때까지 화면이 가만히 있었다. 이제 ① 만들기(진행 막대 · 파일 n / N · 크기 · 남은 시간,
 * [그만두기]) ② 받기(다 만들면 저절로 내려받기 — 브라우저가 받기 진행을 보인다). 다른 화면에 갔다 와도 이어 보인다.
 * 시작 전에 **예상 크기**(문서 · 첨부)와 작업 자리의 남은 자리를 보인다(267 — 큰 작업 파일은 데이터 폴더 드라이브에 만든다).
 */
export default function BackupDownloadCard() {
  const [estimate, setEstimate] = useState<{ all: BackupEstimate; docs: BackupEstimate } | null>(null);
  const [job, setJob] = useState<BackupJob | null>(null);
  const [message, setMessage] = useState("");
  const fetched = useRef<string>("");

  useEffect(() => {
    Promise.all([api.backupEstimate(true), api.backupEstimate(false)])
      .then(([all, docs]) => setEstimate({ all, docs }))
      .catch(() => setEstimate(null));
    api.currentBackupJob().then(({ job: now }) => now && setJob(now)).catch(() => undefined);
  }, []);

  // 만드는 동안 1초마다
  useEffect(() => {
    if (!job || job.state !== "running") return;
    const timer = window.setInterval(() => {
      api.backupJob(job.id).then(setJob).catch((err: Error) => { setJob(null); setMessage(err.message); });
    }, 1000);
    return () => window.clearInterval(timer);
  }, [job?.id, job?.state]); // eslint-disable-line react-hooks/exhaustive-deps

  // 다 만들면 저절로 받기(한 번만)
  useEffect(() => {
    if (job?.state === "done" && fetched.current !== job.id) {
      fetched.current = job.id;
      const link = document.createElement("a");
      link.href = `/api/backup/jobs/${job.id}/file`;
      link.download = job.filename;
      link.click();
      setMessage(`다 만들었습니다(${formatBytes(job.size)}) — 내려받기를 시작했습니다. 브라우저의 내려받기 표시에서 진행을 볼 수 있습니다.`);
    }
    if (job?.state === "cancelled") setMessage("그만두었습니다 — 만들던 파일은 지웠습니다.");
    if (job?.state === "error") setMessage(job.error);
  }, [job?.state, job?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  async function start(assets: boolean) {
    setMessage("");
    try {
      setJob(await api.startBackupJob(assets));
    } catch (err) {
      notifyError((err as Error).message);
    }
  }

  async function cancel() {
    if (!job) return;
    try {
      setJob(await api.cancelBackupJob(job.id));
    } catch (err) {
      notifyError((err as Error).message);
    }
  }

  const running = job?.state === "running";
  const ratio = job && job.bytes_total ? Math.min(1, job.bytes_done / job.bytes_total) : 0;
  return (
    <div className="card backup-download" data-testid="backup-download">
      <IconTitle icon={Download}>전체 백업</IconTitle>
      <CardIntro id="full-backup">
        모든 과제의 문서와 첨부를 zip 하나로 내려받습니다. 검색 색인처럼 다시 만들 수 있는 것은 빼고 원본만 담습니다.
        누르면 서버가 먼저 zip 을 만들고(진행이 보입니다), 다 만들면 저절로 내려받습니다.
      </CardIntro>
      {estimate && (
        <p className="hint backup-estimate">
          예상 크기 — 문서 <b>{formatBytes(estimate.all.docs_bytes)}</b> · 첨부 <b>{formatBytes(estimate.all.assets_bytes)}</b>
          {" "}(파일 {estimate.all.files.toLocaleString("ko-KR")}개, 압축 전){estimate.all.free_bytes !== null && <> · 작업 자리의 남은 자리 {formatBytes(estimate.all.free_bytes)}</>}
        </p>
      )}
      {job && (running || job.state === "done") && (
        <div className="backup-progress" data-testid="backup-progress" aria-live="polite">
          <div className="backup-bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(ratio * 100)}>
            <span style={{ width: `${Math.round(ratio * 100)}%` }} />
          </div>
          <p className="muted">
            {running ? "만드는 중" : "다 만들었습니다"} — 파일 {job.files_done.toLocaleString("ko-KR")} / {job.files_total.toLocaleString("ko-KR")}
            {" "}· {formatBytes(job.bytes_done)} / {formatBytes(job.bytes_total)} · 지난 시간 {seconds(job.elapsed)}
            {running && <> · 남은 시간 약 {seconds(job.eta)}</>}
            {job.assets ? "" : " · 첨부 빼고"}
          </p>
        </div>
      )}
      {message && <p className={job?.state === "error" ? "error" : "hint notice"}>{message}</p>}
      <div className="form-actions">
        {running ? (
          <button className="ghost danger" onClick={() => void cancel()}>그만두기</button>
        ) : (
          <>
            <button onClick={() => void start(true)}>전체 백업 내려받기</button>
            <button className="ghost" onClick={() => void start(false)} title="진행일지 · 보고 · 개요 같은 문서만 — 첨부 파일은 빠집니다">
              첨부 빼고 내려받기{estimate ? ` (${formatBytes(estimate.docs.bytes)})` : ""}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
