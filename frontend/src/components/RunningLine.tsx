import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { RunningTask } from "../types";
import { formatBytes } from "../upload";

/** 초를 "1분 5초" · "12초" 로 — 진행 줄들이 함께 쓴다 */
export function seconds(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  const s = Math.round(value);
  return s >= 60 ? `${Math.floor(s / 60)}분 ${s % 60}초` : `${s}초`;
}

/** 진행 막대 하나 — 비율을 모르면(0) 흐르는 막대 */
export function ProgressBar({ ratio, label }: { ratio: number | null; label?: string }) {
  const known = ratio !== null && Number.isFinite(ratio);
  const percent = known ? Math.round(Math.min(1, Math.max(0, ratio as number)) * 100) : 0;
  return (
    <div className={known ? "backup-bar" : "backup-bar indeterminate"} role="progressbar" aria-label={label}
      aria-valuemin={0} aria-valuemax={100} aria-valuenow={known ? percent : undefined}>
      <span style={known ? { width: `${percent}%` } : undefined} />
    </div>
  );
}

/** 진행 한 줄의 글 — "과제 읽기 12 / 80 · 3.1 MB / 9 MB · 지난 시간 4초 · 남은 시간 약 9초" */
export function progressText(task: Pick<RunningTask, "phase" | "done" | "total" | "bytes_done" | "bytes_total" | "elapsed" | "eta">,
  unit = ""): string {
  const parts: string[] = [];
  if (task.total) parts.push(`${task.phase ? `${task.phase} ` : ""}${task.done.toLocaleString("ko-KR")} / ${task.total.toLocaleString("ko-KR")}${unit}`);
  else if (task.phase) parts.push(task.phase);
  if (task.bytes_total) parts.push(`${formatBytes(task.bytes_done)} / ${formatBytes(task.bytes_total)}`);
  parts.push(`지난 시간 ${seconds(task.elapsed)}`);
  if (task.eta !== null && task.eta !== undefined) parts.push(`남은 시간 약 ${seconds(task.eta)}`);
  return parts.join(" · ");
}

function ratioOf(task: RunningTask | null): number | null {
  if (!task) return null;
  if (task.bytes_total) return task.bytes_done / task.bytes_total;
  if (task.total) return task.done / task.total;
  return null;
}

/**
 * 오래 걸리는 요청 하나의 진행 (TODO 268) — 요청을 보낸 동안(`active`) 1초마다 `/api/running?key=` 를 보아
 * 막대와 "단계 n / N · 크기 · 지난 시간 · 남은 시간" 을 보인다. 서버가 아직 진행을 적지 않았으면 흐르는 막대와 지난 시간만.
 * [다시 읽기] · [지금 백업] · [되돌리기] · [바꾸기] · 첨부 링크 [점검하기 · 고치기] 가 함께 쓴다.
 */
export default function RunningLine({ active, runKey, label }: { active: boolean; runKey: string; label: string }) {
  const [task, setTask] = useState<RunningTask | null>(null);
  const [since, setSince] = useState(0);
  const startedAt = useRef(0);

  useEffect(() => {
    if (!active) {
      setTask(null);
      return;
    }
    startedAt.current = Date.now();
    setSince(0);
    let stop = false;
    const tick = () => {
      setSince((Date.now() - startedAt.current) / 1000);
      api.running(runKey)
        .then(({ tasks }) => {
          if (stop) return;
          const live = tasks.filter((t) => t.state === "running");
          setTask(live[live.length - 1] ?? null);
        })
        .catch(() => undefined);
    };
    const first = window.setTimeout(tick, 300);
    const timer = window.setInterval(tick, 1000);
    return () => {
      stop = true;
      window.clearTimeout(first);
      window.clearInterval(timer);
    };
  }, [active, runKey]);

  if (!active) return null;
  return (
    <div className="running-line" data-testid="running-line" aria-live="polite">
      <ProgressBar ratio={ratioOf(task)} label={label} />
      <p className="muted">
        {label} — {task ? progressText(task) : `지난 시간 ${seconds(since)}`}
      </p>
    </div>
  );
}

type Meter = { name: string; loaded: number; total: number; started: number };

/**
 * 파일 올리기의 진행 (TODO 268) — 과제 개요 · 접수의 [📎 파일 첨부] 도 진행일지 편집기처럼 크기 · % · 속도 · 남은 시간을 보인다.
 * `progress(file)` 를 `uploadAttachment` 의 onProgress 로 넘기고, 다 올리면 `clear()`.
 */
export function useUploadMeter() {
  const [meter, setMeter] = useState<Meter | null>(null);
  const progress = (file: File) => {
    const started = Date.now();
    setMeter({ name: file.name, loaded: 0, total: file.size, started });
    return (loaded: number, total: number) => setMeter({ name: file.name, loaded, total, started });
  };
  return { meter, progress, clear: () => setMeter(null) };
}

export function UploadMeter({ meter }: { meter: Meter | null }) {
  if (!meter) return null;
  const spent = (Date.now() - meter.started) / 1000;
  const rate = spent > 0 ? meter.loaded / spent : 0;
  const eta = rate > 0 && meter.loaded < meter.total ? (meter.total - meter.loaded) / rate : null;
  const ratio = meter.total ? meter.loaded / meter.total : null;
  return (
    <div className="running-line" data-testid="upload-meter" aria-live="polite">
      <ProgressBar ratio={meter.loaded >= meter.total ? null : ratio} label="올리기" />
      <p className="muted">
        {meter.loaded >= meter.total
          ? `${meter.name} — 다 올렸습니다, 서버가 저장하는 중…`
          : `올리는 중 — ${meter.name} · ${formatBytes(meter.loaded)} / ${formatBytes(meter.total)} (${ratio !== null ? Math.floor(ratio * 100) : 0}%)` +
            `${rate ? ` · ${formatBytes(rate)}/초` : ""}${eta !== null ? ` · 남은 시간 약 ${seconds(eta)}` : ""}`}
      </p>
    </div>
  );
}
