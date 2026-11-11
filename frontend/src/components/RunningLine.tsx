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
