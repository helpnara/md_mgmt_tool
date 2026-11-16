import { useEffect, useState } from "react";
import { api } from "../api";
import { getMe } from "../me";
import { notifyError } from "../notify";
import type { ModeStatus } from "../types";

/**
 * 체험 자료 · 내 자료 (TODO 295) — 머리 바로 아래에 둔다.
 *
 * * 처음 켰을 때(자료가 없고 모드를 정한 적 없음) — 서버 PC 에 **고르기** 화면: [체험 자료로 둘러보기] · [내 자료로 시작하기].
 * * 바꾸는 중 — 화면 전체에 진행 표시(체험 자료 만들기는 수십 초), 끝나면 화면을 새로 읽는다.
 * * 체험 중 — 모든 화면 위 띠: [처음 자료로 되돌리기] · [내 자료로 시작하기]. 팀원 · 팀장 PC 에는 "체험 중" 안내만(서버가 자료를 막는다).
 */
/** 바꾸기를 시작하면 알린다 — 머리 아래의 ModeLayer 가 진행 표시를 띄우고, 끝나면 화면을 새로 연다 (TODO 297) */
const MODE_EVENT = "mode-switching";

export function useMode(): [ModeStatus | null, (next: ModeStatus) => void] {
  const [mode, setMode] = useState<ModeStatus | null>(null);
  useEffect(() => {
    const load = () => api.mode().then(setMode).catch(() => setMode(null));
    void load();
    window.addEventListener(MODE_EVENT, load);
    return () => window.removeEventListener(MODE_EVENT, load);
  }, []);
  return [mode, setMode];
}

export async function switchMode(body: { mode: "demo" | "mine"; mine_dir?: string; reset?: boolean }, onStatus: (s: ModeStatus) => void) {
  try {
    onStatus(await api.switchMode(body));
    // 297 — 화면을 바로 새로 읽지 않는다(바꾸는 중에 읽으면 오류). 진행 표시가 끝을 기다렸다가 새로 연다
    window.dispatchEvent(new Event(MODE_EVENT));
  } catch (error) {
    notifyError((error as Error).message);
  }
}

export default function ModeLayer() {
  const [mode, setMode] = useMode();
  const [mine, setMine] = useState("");
  const owner = getMe().role === "owner";

  // 바꾸는 중이면 1초마다 — 끝나면 새로 읽는다(설정 · 명부 · 색인이 모두 다른 폴더의 것으로 바뀐다)
  useEffect(() => {
    if (!mode?.job.running) return;
    const timer = window.setInterval(() => {
      api.mode().then((next) => {
        setMode(next);
        if (!next.job.running) {
          if (next.job.error) notifyError(`바꾸지 못했습니다 — ${next.job.error}`);
          else { window.location.hash = "#/"; window.location.reload(); }
        }
      }).catch(() => undefined);
    }, 1000);
    return () => window.clearInterval(timer);
  }, [mode?.job.running]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!mode) return null;
  const go = (body: { mode: "demo" | "mine"; mine_dir?: string; reset?: boolean }) => void switchMode(body, setMode);

  if (mode.job.running) {
    const pct = mode.job.total ? Math.round((mode.job.done / mode.job.total) * 100) : 0;
    return (
      <div className="mode-cover" role="status" data-testid="mode-progress">
        <div className="mode-box">
          <h2>{mode.job.target === "demo" ? "체험 자료를 준비하고 있습니다" : "내 자료로 바꾸고 있습니다"}</h2>
          <p>{mode.job.stage}</p>
          <div className="mode-bar"><span style={{ width: `${pct}%` }} /></div>
          <p className="muted">끝나면 화면이 새로 열립니다. 창을 닫지 마세요.</p>
        </div>
      </div>
    );
  }

  if (mode.choose && owner) {
    return (
      <div className="mode-cover" data-testid="mode-choose">
        <div className="mode-box wide">
          <h2>느린 나이테를 어떻게 시작할까요?</h2>
          <div className="mode-choices">
            <section>
              <h3>체험 자료로 둘러보기</h3>
              <p>지어낸 팀(팀원 10명 · 퇴사자 2명 · 과제 20건)의 한 해 자료가 들어 있습니다. 마음껏 고치고 지워 보세요 — 언제든 처음 자료로 되돌릴 수 있습니다.</p>
              <button type="button" onClick={() => go({ mode: "demo" })}>체험 자료로 둘러보기</button>
            </section>
            <section>
              <h3>내 자료로 시작하기</h3>
              <p>빈 자료로 시작합니다. 자료 폴더는 기본(<code>{mode.mine_dir}</code>)이거나 직접 정할 수 있습니다(네트워크 드라이브 등).</p>
              <label>자료 폴더 <span className="muted">(비우면 기본)</span>
                <input value={mine} onChange={(e) => setMine(e.target.value)} placeholder="예: D:\과제이력" aria-label="내 자료 폴더" />
              </label>
              <button type="button" className="ghost" onClick={() => go({ mode: "mine", mine_dir: mine.trim() || undefined })}>내 자료로 시작하기</button>
            </section>
          </div>
          <p className="muted">체험 자료와 내 자료는 다른 폴더라 섞이지 않습니다. 나중에 설정 → [보관과 백업] → <b>체험 · 내 자료</b>에서 바꿀 수 있습니다.</p>
        </div>
      </div>
    );
  }

  if (mode.mode !== "demo") return null;
  if (!owner) {
    return (
      <div className="mode-cover" data-testid="mode-blocked">
        <div className="mode-box">
          <h2>서버 PC 가 체험 모드입니다</h2>
          <p>지금 서버 PC 에서 연습용 가상 자료로 사용법을 익히는 중입니다. 체험이 끝나 <b>내 자료</b>로 바꾼 뒤 다시 열어 주세요.</p>
        </div>
      </div>
    );
  }
  return (
    <div className="mode-band" role="status" data-testid="mode-band">
      <b>체험 모드</b> — 연습용 가상 자료입니다(팀원 10명 · 과제 20건, 모두 지어낸 것). 마음껏 고치고 지워 보세요. 자동 백업 · 팀원 PC 접속은 꺼져 있습니다.
      <span className="mode-band-actions">
        <a href="#/help">사용법 보기</a>
        <button type="button" className="ghost small" onClick={() => window.confirm("체험 자료를 처음 상태로 되돌릴까요? 체험에서 고친 것은 모두 사라집니다.") && go({ mode: "demo", reset: true })}>처음 자료로 되돌리기</button>
        <button type="button" className="small" onClick={() => window.confirm("내 자료로 바꿀까요? 체험 자료는 그대로 남아 나중에 다시 볼 수 있고, 내 자료에는 섞이지 않습니다.") && go({ mode: "mine" })}>내 자료로 시작하기</button>
      </span>
    </div>
  );
}

/** 설정 → [보관과 백업]의 카드 — 지금 모드 · 폴더 · 바꾸기 */
export function ModeCard() {
  const [mode, setMode] = useMode();
  if (!mode) return null;
  const go = (body: { mode: "demo" | "mine"; reset?: boolean }) => void switchMode(body, setMode);
  return (
    <div className="card" data-testid="mode-card">
      <div className="card-head"><h3>체험 · 내 자료</h3></div>
      <p className="hint">
        지금 <b>{mode.mode === "demo" ? "체험 자료" : "내 자료"}</b> — <code>{mode.vault}</code>
        {mode.fixed && " · 이 서버는 데이터 폴더를 정해 켰습니다(run.bat --vault) — 여기서 바꿀 수 없습니다."}
      </p>
      {!mode.fixed && (
        <div className="form-actions">
          {mode.mode === "mine" ? (
            <button type="button" className="ghost" onClick={() => window.confirm("체험 자료로 바꿀까요? 내 자료는 그대로 남고, 체험 중에는 자동 백업 · 팀원 PC 접속이 꺼집니다.") && go({ mode: "demo" })}>
              체험 자료로 둘러보기{mode.demo_ready ? "" : " (처음이면 만듭니다)"}
            </button>
          ) : (
            <>
              <button type="button" className="ghost" onClick={() => window.confirm("체험 자료를 처음 상태로 되돌릴까요?") && go({ mode: "demo", reset: true })}>처음 자료로 되돌리기</button>
              <button type="button" onClick={() => window.confirm("내 자료로 바꿀까요?") && go({ mode: "mine" })}>내 자료로 시작하기</button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
