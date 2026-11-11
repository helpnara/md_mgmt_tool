import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { RunningTask } from "../types";
import { ProgressBar, progressText, seconds } from "./RunningLine";

interface Props {
  projectId: string;
}

const OPTIONS = [
  {
    key: "zip",
    label: "마크다운 + 첨부 (zip)",
    hint: "압축을 풀면 md 옆에 첨부가 함께 있어 링크가 그대로 열립니다.",
    query: "format=zip",
  },
  {
    key: "md",
    label: "마크다운 한 파일",
    hint: "이미지를 파일 안에 심어 md 하나로 완결됩니다.",
    query: "format=md&assets=inline",
  },
  {
    key: "html",
    label: "HTML 한 파일",
    hint: "메일로 보내거나 인쇄하기 좋습니다.",
    query: "format=html",
  },
  {
    key: "backup",
    label: "과제 폴더 백업 (zip)",
    hint: "원본 폴더 구조 그대로 내려받습니다.",
    query: "format=backup",
  },
];

type Making = { job: string; label: string; started: number; task: RunningTask | null; seen: boolean; finished: boolean };

/**
 * 과제 내보내기 (TODO 268 — 진행 표시). 예전에는 누르면 메뉴만 닫히고, 서버가 zip 을 다 만들 때까지 화면에 아무 변화가 없어
 * 다시 누르게 됐다. 이제 링크에 `job` 표를 붙이고 `/api/running?key=` 를 1초마다 보아 "zip 만들기 n / N · 크기 · 남은 시간" 을
 * 메뉴 안에 보이고, 다 만들면 "내려받기를 시작했습니다" 로 바꾼다. 받는 것은 지금처럼 브라우저가 한다(링크).
 */
export default function ExportMenu({ projectId }: Props) {
  const [open, setOpen] = useState(false);
  const [withReports, setWithReports] = useState(false);
  const [making, setMaking] = useState<Making | null>(null);
  const newJob = () => Math.random().toString(36).slice(2, 12);
  const [nextJob, setNextJob] = useState(newJob);
  const container = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!making || making.finished) return;
    const timer = window.setInterval(() => {
      api.running(making.job).then(({ tasks }) => {
        const task = tasks[tasks.length - 1] ?? null;
        setMaking((now) => {
          if (!now || now.job !== making.job) return now;
          const finished = Boolean(task && task.state !== "running");
          return { ...now, task: task ?? now.task, seen: now.seen || Boolean(task), finished };
        });
      }).catch(() => undefined);
    }, 1000);
    return () => window.clearInterval(timer);
  }, [making?.job, making?.finished]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!open) return;
    const onClick = (event: MouseEvent) => {
      // 만드는 동안에는 밖을 눌러도 진행을 남긴다
      if (!container.current?.contains(event.target as Node) && (!making || making.finished)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open, making]);

  return (
    <div className="export-menu" ref={container}>
      <button className="ghost" onClick={() => setOpen((value) => !value)}>
        내보내기
      </button>
      {open && (
        <div className="export-panel card">
          <label className="toggle">
            <input
              type="checkbox"
              checked={withReports}
              onChange={(event) => setWithReports(event.target.checked)}
            />
            보고 문서 전문 포함
          </label>
          <ul>
            {OPTIONS.map((option) => (
              // 과제 폴더 백업은 서버 PC 에서만 — 바깥(읽기 전용 · 팀원)에서는 서버가 403 이라 항목을 숨긴다 (TODO 238 ③)
              <li key={option.key} {...(option.key === "backup" ? { "data-write": true, "data-owner-only": true } : {})}>
                <a
                  href={`/api/projects/${projectId}/export?${option.query}${
                    withReports ? "&include_reports_full=true" : ""
                  }&job=${nextJob}`}
                  aria-disabled={making && !making.finished ? true : undefined}
                  onClick={(event) => {
                    if (making && !making.finished) {
                      event.preventDefault();   // 만드는 중에 또 누르지 않게
                      return;
                    }
                    setMaking({ job: nextJob, label: option.label, started: Date.now(), task: null, seen: false, finished: false });
                    setNextJob(newJob());
                  }}
                >
                  <strong>{option.label}</strong>
                  <span className="hint">{option.hint}</span>
                </a>
              </li>
            ))}
          </ul>
          {making && (
            <div className="export-progress" data-testid="export-progress" aria-live="polite">
              {making.finished ? (
                <p className={making.task?.state === "error" ? "error" : "hint notice"}>
                  {making.task?.state === "error"
                    ? `${making.label} — 만들지 못했습니다. 화면 아래 알림이나 설정 → 점검의 최근 오류를 보세요.`
                    : `${making.label} — 다 만들었습니다(${seconds(making.task?.elapsed)}). 내려받기를 시작했습니다 — 브라우저의 내려받기 표시를 보세요.`}
                </p>
              ) : (
                <>
                  <ProgressBar ratio={making.task?.bytes_total ? making.task.bytes_done / making.task.bytes_total : null} label={making.label} />
                  <p className="muted">
                    {making.label} 만드는 중 — {making.task ? progressText(making.task, "개 파일") : `지난 시간 ${seconds((Date.now() - making.started) / 1000)}`}
                  </p>
                </>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
