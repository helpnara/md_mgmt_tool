import { useEffect, useState } from "react";
import { api } from "../api";
import { getMe } from "../me";
import { notifyError } from "../notify";
import type { UpdateStatus } from "../types";

/**
 * 업데이트 (TODO 298) — zip 을 업데이트 폴더(기본: 설치 폴더의 updates, 설정에서 사내 공유 폴더)에 두면
 * 서버 PC 화면에 알리고, [이 판으로 업데이트]를 누르면 데이터 백업 → 스스로 끝남 → run.bat 이 새 판을 적용하고 다시 켠다.
 */
const RESTART_EVENT = "update-restarting";

/** 다시 켜질 때까지 덮개 — 서버가 꺼졌다 다시 답하면 새로 연다 */
export function UpdateCover() {
  const [on, setOn] = useState(false);
  useEffect(() => {
    const start = () => setOn(true);
    window.addEventListener(RESTART_EVENT, start);
    return () => window.removeEventListener(RESTART_EVENT, start);
  }, []);
  useEffect(() => {
    if (!on) return;
    let down = false;
    const timer = window.setInterval(() => {
      fetch("/api/meta", { cache: "no-store" }).then((r) => {
        if (r.ok && down) window.location.reload();
        if (!r.ok) down = true;
      }).catch(() => { down = true; });
    }, 1500);
    return () => window.clearInterval(timer);
  }, [on]);
  if (!on) return null;
  return (
    <div className="mode-cover" role="status" data-testid="update-cover">
      <div className="mode-box">
        <h2>업데이트를 적용하고 다시 켭니다</h2>
        <p>서버가 잠깐 꺼졌다가 새 판으로 켜집니다. 켜지면 화면이 저절로 새로 열립니다(보통 30초 안).</p>
        <p className="muted">창(run.bat)을 닫지 마세요. 오래 걸리면 run.bat 창의 글을 확인하세요.</p>
      </div>
    </div>
  );
}

function restartNow(restarting: boolean) {
  if (restarting) window.dispatchEvent(new Event(RESTART_EVENT));
  else window.alert("적용을 예약했습니다. 이 서버는 run.bat 으로 켜지지 않아 스스로 다시 켤 수 없습니다 — 창을 닫고 run.bat 으로 다시 켜면 적용됩니다.");
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
  // 켜 둔 채 폴더에 zip 을 넣어도 알아보게 — 10분마다 다시 찾는다
  useEffect(() => {
    const timer = window.setInterval(load, 10 * 60 * 1000);
    return () => window.clearInterval(timer);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
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
    if (!window.confirm(`${name} 으로 업데이트할까요?\n\n· 데이터 백업을 한 벌 만든 뒤(자동 백업 폴더가 있을 때)\n· 서버가 잠깐 꺼졌다 새 판으로 켜집니다 — 그동안 팀원 화면도 잠깐 멈춥니다.\n· 문제가 있으면 [이전 판으로] 또는 run.bat --rollback 으로 되돌릴 수 있습니다.`)) return;
    setBusy(true);
    try {
      const done = await api.applyUpdate(name);
      restartNow(done.restarting);
    } catch (error) {
      notifyError((error as Error).message);
    } finally {
      setBusy(false);
      load();
    }
  }
  async function rollback() {
    if (!window.confirm("이전 판으로 되돌릴까요? 서버가 잠깐 꺼졌다 이전 판으로 켜집니다. 데이터는 그대로입니다.")) return;
    try {
      const done = await api.rollbackUpdate();
      restartNow(done.restarting);
    } catch (error) {
      notifyError((error as Error).message);
    }
  }
  const last = data.last;
  return (
    <div className="card" data-testid="update-card">
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
