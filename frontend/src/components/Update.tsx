import { useEffect, useState } from "react";
import { api } from "../api";
import { getMe } from "../me";
import { notifyError } from "../notify";
import type { RunningTask, UpdateCheck, UpdateStatus } from "../types";
import { formatBytes } from "../upload";
import { ProgressBar, progressText } from "./RunningLine";

/**
 * 업데이트 (TODO 298) — zip 을 업데이트 폴더(기본: 설치 폴더의 updates, 설정에서 사내 공유 폴더)에 두면
 * 서버 PC 화면에 알리고, [이 판으로 업데이트]를 누르면 데이터 백업 → 스스로 끝남 → run.bat 이 새 판을 적용하고 다시 켠다.
 */
const RESTART_EVENT = "update-restarting";
const FINISHED_KEY = "update-finished";

type Action = "apply" | "rollback";
/** skip — 백업을 건너뛴 까닭(있으면 백업 단계 옆에 적는다, TODO 301) */
type Phase = { action: Action; to: string; stage: "backup" | "stop" | "cancel"; skip?: string };
type Remote = { phase: string; action: Action; to: string; stage: string; done: number; total: number; error?: string };

/** 단계 (TODO 300) — 앞 둘은 화면이 아는 것, 가운데는 run.py 의 진행 창구가 알려 주는 것, 끝은 새 서버가 답할 때 */
const STEPS: Record<Action, { key: string; label: string }[]> = {
  apply: [
    { key: "backup", label: "데이터 백업" },
    { key: "stop", label: "서버 끄기" },
    { key: "verify", label: "새 판 검사" },
    { key: "extract", label: "압축 풀기" },
    { key: "keep", label: "지금 판 보관 (되돌리기용)" },
    { key: "copy", label: "새 파일 덮어쓰기" },
    { key: "clean", label: "쓰지 않는 파일 정리" },
    { key: "start", label: "새 판으로 켜기" },
  ],
  rollback: [
    { key: "stop", label: "서버 끄기" },
    { key: "restore", label: "이전 판 파일 되살리기" },
    { key: "clean", label: "새 판에만 있던 파일 정리" },
    { key: "start", label: "이전 판으로 켜기" },
  ],
};

function announce(detail: Phase) {
  window.dispatchEvent(new CustomEvent<Phase>(RESTART_EVENT, { detail }));
}

/** 업데이트 · 되돌리기 동안 덮개 — 단계마다 ✓ · 진행 중 · 기다림, 파일 수, 걸린 시간 (TODO 298 · 300) */
export function UpdateCover() {
  const [job, setJob] = useState<Phase | null>(null);
  const [remote, setRemote] = useState<Remote | null>(null);
  const [stage, setStage] = useState("");
  const [finished, setFinished] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [backupTask, setBackupTask] = useState<RunningTask | null>(null);
  useEffect(() => {
    const on = (event: Event) => {
      const detail = (event as CustomEvent<Phase>).detail;
      if (detail.stage === "cancel") { setJob(null); return; }
      setJob(detail);
      setStage(detail.stage);
    };
    window.addEventListener(RESTART_EVENT, on);
    return () => window.removeEventListener(RESTART_EVENT, on);
  }, []);
  // 걸린 시간
  useEffect(() => {
    if (!job) return;
    setSeconds(0);
    const timer = window.setInterval(() => setSeconds((n) => n + 1), 1000);
    return () => window.clearInterval(timer);
  }, [job?.action, job?.to]); // eslint-disable-line react-hooks/exhaustive-deps
  // 301 — 백업(또는 건너뛰기) 동안: 뒤에서 도는 준비를 1초마다 본다. 끝나면 서버 끄기로
  useEffect(() => {
    if (!job || job.stage !== "backup") return;
    const timer = window.setInterval(() => {
      api.updateJob().then((state) => {
        if (state.name && state.name !== job.to) return;   // 앞서 한 다른 판의 기록
        setBackupTask(state.progress ?? null);
        if (state.state === "restarting") setJob({ ...job, stage: "stop" });
        else if (state.state === "scheduled") restartNow(false, job.action, job.to);
        else if (state.state === "error") {
          setJob(null);
          notifyError(state.error || "업데이트를 준비하지 못했습니다.");
        }
      }).catch(() => undefined);
    }, 1000);
    return () => window.clearInterval(timer);
  }, [job]);
  // 진행 묻기 — 서버 끄기부터
  useEffect(() => {
    if (!job || job.stage === "backup") return;
    let seen = false;
    let down = false;
    let done = false;
    const finish = (error?: string) => {
      if (done) return;
      done = true;
      setStage("done");
      setFinished(true);
      try { window.sessionStorage.setItem(FINISHED_KEY, JSON.stringify({ action: job.action, to: job.to, error: error ?? "" })); } catch { /* 없어도 된다 */ }
      window.setTimeout(() => window.location.reload(), 1500);
    };
    let lastError = "";
    const tick = () => {
      fetch("/api/update/progress", { cache: "no-store" }).then(async (response) => {
        const kind = response.headers.get("content-type") ?? "";
        if (response.ok && kind.includes("json")) {
          const body = (await response.json()) as Remote;
          if (body.phase === "applying") {
            seen = true;
            if (body.error) lastError = body.error;
            setRemote(body);
            setStage(body.stage === "start" && !body.error ? "start" : body.stage);
            return;
          }
        }
        // 진행 창구가 아닌 서버가 답한다 — 끄기 전(아직 옛 서버)이거나, 새 판이 켜졌거나
        if (seen || down) {
          const meta = await fetch("/api/meta", { cache: "no-store" });
          if (meta.ok) finish(lastError);
        }
      }).catch(() => {
        down = true;
        if (seen) setStage("start");
      });
    };
    const timer = window.setInterval(tick, 700);
    return () => window.clearInterval(timer);
  }, [job]);
  if (!job) return null;
  const steps = STEPS[job.action];
  const at = finished ? steps.length : Math.max(0, steps.findIndex((step) => step.key === stage));
  const title = job.action === "rollback" ? "이전 판으로 되돌리고 있습니다" : `${job.to} (으)로 업데이트하고 있습니다`;
  const minutes = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
  return (
    <div className="mode-cover" role="status" data-testid="update-cover">
      <div className="mode-box">
        <h2>{title}</h2>
        <ol className="update-steps" data-testid="update-steps">
          {steps.map((step, index) => {
            const state = index < at ? "done" : index === at ? "now" : "wait";
            const count = state === "now" && remote && remote.stage === step.key && remote.total > 0 ? ` ${remote.done}/${remote.total}` : "";
            const skipped = step.key === "backup" && job.skip;
            const showBackup = step.key === "backup" && state === "now" && !job.skip;
            return (
              <li key={step.key} className={`${state}${skipped ? " skipped" : ""}`} data-step={step.key}>
                <div className="update-step-line">
                  <span className="mark" aria-hidden>{state === "done" ? (skipped ? "–" : "✓") : state === "now" ? "" : "·"}</span>
                  {step.label}<span className="muted">{skipped ? ` — 건너뜀 (${job.skip})` : count}</span>
                </div>
                {showBackup && (
                  <div className="update-step-detail" data-testid="update-backup-progress">
                    <ProgressBar ratio={backupTask?.bytes_total ? backupTask.bytes_done / backupTask.bytes_total : null} label="데이터 백업" />
                    <span className="muted">{backupTask ? progressText({ ...backupTask, phase: "" }, "개 파일") : "백업할 파일을 세는 중…"}</span>
                  </div>
                )}
              </li>
            );
          })}
        </ol>
        {remote?.error && <p className="form-error">새 판을 적용하지 못해 지금 판으로 다시 켭니다 — {remote.error}</p>}
        <p className="muted">
          {finished ? "끝났습니다 — 화면을 새로 엽니다." : `걸린 시간 ${minutes} · 창(run.bat)을 닫지 마세요.`}
          {!finished && seconds > 120 && " 오래 걸리면 run.bat 창의 글을 확인하세요."}
        </p>
      </div>
    </div>
  );
}

/** 새로 열린 화면에 한 번 — "업데이트했습니다" (TODO 300) */
function takeFinished(): { action: Action; to: string; error: string } | null {
  try {
    const raw = window.sessionStorage.getItem(FINISHED_KEY);
    if (!raw) return null;
    window.sessionStorage.removeItem(FINISHED_KEY);
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function restartNow(restarting: boolean, action: Action, to: string) {
  if (restarting) { announce({ action, to, stage: "stop" }); return; }
  announce({ action, to, stage: "cancel" });
  window.alert("적용을 예약했습니다. 이 서버는 run.bat 으로 켜지지 않아 스스로 다시 켤 수 없습니다 — 창을 닫고 run.bat 으로 다시 켜면 적용됩니다.");
}

export function useUpdate(): [UpdateStatus | null, () => void] {
  const [data, setData] = useState<UpdateStatus | null>(null);
  const load = () => { if (getMe().role === "owner") api.updateStatus().then(setData).catch(() => setData(null)); };
  useEffect(load, []);
  return [data, load];
}

/** 서버 PC 화면 위의 띠 — 새 판이 있을 때만 */
export function UpdateBand() {
  const [data, load] = useUpdate();
  const [finished, setFinished] = useState(takeFinished);
  // 켜 둔 채 폴더에 zip 을 넣어도 알아보게 — 10분마다 다시 찾는다
  useEffect(() => {
    const timer = window.setInterval(load, 10 * 60 * 1000);
    return () => window.clearInterval(timer);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  if (finished) {
    const failed = !!finished.error || (data?.last && !data.last.ok);
    return (
      <div className={`update-band ${failed ? "failed" : "finished"}`} role="status" data-testid="update-finished">
        {failed
          ? <>새 판을 적용하지 못해 <b>{data?.current || "지금 판"}</b> 그대로 켰습니다 — {finished.error || data?.last?.error}</>
          : finished.action === "rollback"
            ? <>이전 판 <b>{data?.current || finished.to}</b> (으)로 되돌렸습니다. 데이터는 그대로입니다.</>
            : <><b>{data?.current || finished.to}</b> (으)로 업데이트했습니다. 데이터는 그대로입니다.</>}
        <button type="button" className="ghost small" onClick={() => setFinished(null)}>닫기</button>
      </div>
    );
  }
  if (!data?.newest) return null;
  return (
    <div className="update-band" role="status" data-testid="update-band">
      새 판 <b>{data.newest}</b> 이(가) 업데이트 폴더에 있습니다 (지금 {data.current || "개발판"}).
      <a href="#/settings?tab=backup">설정에서 업데이트 →</a>
    </div>
  );
}

/** 설정 → [보관과 백업] → 업데이트 카드 */
export function UpdateCard() {
  const [data, load] = useUpdate();
  const [busy, setBusy] = useState(false);
  const [folder, setFolder] = useState<string | null>(null);
  const [asking, setAsking] = useState<{ name: string; check: UpdateCheck } | null>(null);
  if (!data) return null;
  async function saveFolder() {
    try {
      await api.saveSettings({ update_dir: (folder ?? "").trim() });
      setFolder(null);
      load();
    } catch (error) {
      notifyError((error as Error).message);
    }
  }
  async function apply(name: string) {
    setBusy(true);
    try {
      setAsking({ name, check: await api.updateCheck() });   // 301 — 백업할지 · 예상 크기 · 남은 공간을 먼저 보인다
    } catch (error) {
      notifyError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function go(name: string, backup: boolean, skip: string) {
    setAsking(null);
    announce({ action: "apply", to: name, stage: "backup", skip: backup ? undefined : skip });
    try {
      await api.applyUpdate(name, backup);
    } catch (error) {
      announce({ action: "apply", to: name, stage: "cancel" });
      notifyError((error as Error).message);
      load();
    }
  }
  async function rollback() {
    if (!window.confirm("이전 판으로 되돌릴까요? 서버가 잠깐 꺼졌다 이전 판으로 켜집니다. 데이터는 그대로입니다.")) return;
    try {
      const done = await api.rollbackUpdate();
      restartNow(done.restarting, "rollback", "");
    } catch (error) {
      notifyError((error as Error).message);
    }
  }
  const last = data.last;
  return (
    <div className="card" data-testid="update-card">
      {asking && <UpdateConfirm name={asking.name} check={asking.check} onCancel={() => setAsking(null)} onGo={(backup, skip) => void go(asking.name, backup, skip)} />}
      <div className="card-head"><h3>업데이트</h3></div>
      <p className="hint">
        지금 판 <b>{data.current || "개발판(배포본 정보 없음)"}</b> · 업데이트 폴더 <code>{data.folder}</code>
        {!data.reachable && <span className="warn-text"> — 폴더에 닿지 않습니다</span>}
        <br />새 배포본 zip(과 같은 이름의 .sha256)을 이 폴더에 넣으면 여기와 화면 위에 알림이 뜹니다.
      </p>
      <div className="update-folder">
        <input aria-label="업데이트 폴더" value={folder ?? data.configured} placeholder="비우면 설치 폴더의 updates — 예: \\파일서버\느린나이테\updates"
          onChange={(e) => setFolder(e.target.value)} />
        <button type="button" className="ghost" disabled={folder === null || folder === data.configured} onClick={() => void saveFolder()}>폴더 저장</button>
      </div>
      {data.items.length === 0 ? <p className="muted">폴더에 배포본 zip 이 없습니다.</p> : (
        <ul className="update-list">
          {data.items.map((item) => (
            <li key={item.file} className={item.newer ? "newer" : undefined}>
              <span><b>{item.name}</b> <span className="muted">{(item.size / 1024 / 1024).toFixed(1)}MB{item.has_sha ? " · 검사값 있음" : ""}{item.current ? " · 지금 판" : ""}</span></span>
              {item.problem ? <span className="warn-text">{item.problem}</span> : (
                <button type="button" className={item.newer ? "small" : "ghost small"} disabled={busy || item.current} onClick={() => void apply(item.name)}>
                  {item.newer ? "이 판으로 업데이트" : "이 판으로 바꾸기"}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {last && (
        <p className={last.ok ? "hint" : "form-error"}>
          마지막 {last.action === "rollback" ? "되돌리기" : "업데이트"} {last.at.replace("T", " ").slice(0, 16)} — {last.from ?? ""} → {last.to ?? ""}
          {last.ok ? " · 성공" : ` · 실패: ${last.error ?? ""}`}{last.data_backup ? ` · 데이터 백업 ${last.data_backup}` : ""}
        </p>
      )}
      {!data.supervised && <p className="muted">이 서버는 run.bat 으로 켜지지 않아 스스로 다시 켤 수 없습니다 — 업데이트를 누른 뒤 창을 닫고 run.bat 으로 다시 켜면 적용됩니다.</p>}
      <div className="form-actions">
        <button type="button" className="ghost" disabled={!data.rollback} onClick={() => void rollback()} title={data.rollback ? "" : "되돌릴 이전 판이 없습니다"}>이전 판으로</button>
        <button type="button" className="ghost" onClick={load}>다시 찾기</button>
      </div>
    </div>
  );
}

/** 업데이트 전 확인 (TODO 301) — 데이터 백업을 새로 할지 · 건너뛸지, 예상 크기 · 남은 공간 */
function UpdateConfirm({ name, check, onCancel, onGo }: { name: string; check: UpdateCheck; onCancel: () => void; onGo: (backup: boolean, skip: string) => void }) {
  const todayAt = check.today ? check.today.at.slice(11, 16) : "";
  const canBackup = check.enabled && check.reachable && check.enough !== false;
  const [choice, setChoice] = useState<"backup" | "skip">(check.today || !canBackup ? "skip" : "backup");
  const skipWhy = check.today ? `오늘 ${todayAt} 백업 있음` : !check.enabled ? "백업 폴더가 정해져 있지 않음" : "백업 없이";
  const minutes = Math.max(1, Math.round(check.expected_bytes / (15 * 1024 * 1024) / 60));   // 대략 15MB/s
  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="업데이트 확인" data-testid="update-confirm">
      <div className="modal update-confirm">
        <h3><b>{name}</b> (으)로 업데이트할까요?</h3>
        <p className="hint">서버가 잠깐 꺼졌다가 새 판으로 켜집니다. 그동안 팀원 화면도 잠깐 멈춥니다. 문제가 있으면 [이전 판으로] 또는 <code>run.bat --rollback</code> 으로 되돌릴 수 있습니다.</p>
        <fieldset className="update-choice">
          <legend>업데이트 전 데이터 백업</legend>
          <label className={canBackup ? undefined : "disabled"}>
            <input type="radio" name="update-backup" checked={choice === "backup"} disabled={!canBackup} onChange={() => setChoice("backup")} />
            <span>
              <b>새로 백업하고 업데이트</b>
              {check.enabled
                ? <span className="muted"> — 예상 약 {formatBytes(check.expected_bytes)} · 약 {minutes}분{check.free_bytes !== null ? ` · 백업 폴더 남은 공간 ${formatBytes(check.free_bytes)}` : ""}</span>
                : <span className="muted"> — 백업 폴더가 정해져 있지 않습니다(설정 → [보관과 백업])</span>}
              {check.enabled && !check.reachable && <span className="warn-text"> 백업 폴더에 닿지 않습니다: {check.directory}</span>}
              {check.enough === false && <span className="warn-text"> 남은 공간이 모자랍니다 — 오래된 백업을 정리하거나 백업 폴더를 바꿔 주세요.</span>}
            </span>
          </label>
          <label>
            <input type="radio" name="update-backup" checked={choice === "skip"} onChange={() => setChoice("skip")} />
            <span>
              <b>백업 건너뛰고 업데이트</b>
              {check.today
                ? <span className="muted"> — 오늘 {todayAt} 에 만든 백업이 있습니다({check.today.file}) <b>권함</b></span>
                : <span className="muted"> — 오늘 만든 백업이 없습니다. 프로그램 파일만 바뀌고 데이터는 손대지 않지만, 만일을 위해 백업을 권합니다.</span>}
            </span>
          </label>
        </fieldset>
        <div className="form-actions">
          <button type="button" className="ghost" onClick={onCancel}>취소</button>
          <button type="button" data-testid="update-go" onClick={() => onGo(choice === "backup", skipWhy)}>{choice === "backup" ? "백업하고 업데이트" : "업데이트"}</button>
        </div>
      </div>
    </div>
  );
}
