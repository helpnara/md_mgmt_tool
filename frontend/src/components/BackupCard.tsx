import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { BackupStatus } from "../types";
import { formatBytes } from "../upload";
import FolderPicker from "./FolderPicker";

/**
 * 자동 백업 — 바깥쪽 안전망.
 *
 * 이전 버전 보관(`.versions`)은 잘못 고쳤을 때를 막아 주지만 **데이터 폴더 안에 있다.**
 * PC가 고장 나면 함께 없어진다. 여기서 정한 폴더로 한 벌을 내보낸다 —
 * 그 폴더를 네트워크 드라이브나 외장 디스크로 잡으면 곧바로 "다른 곳에 한 벌"이 된다.
 */
export default function BackupCard() {
  const [status, setStatus] = useState<BackupStatus | null>(null);
  const [dir, setDir] = useState("");
  const [keep, setKeep] = useState(10);
  const [hours, setHours] = useState(24);
  const [busy, setBusy] = useState(false);
  /** 폴더 고르기를 펼쳤나 (TODO 97). 경로를 손으로 치지 않아도 되게 한다. */
  const [picking, setPicking] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .backupStatus()
      .then((data) => {
        setStatus(data);
        setDir(data.directory);
        setKeep(data.keep);
        setHours(data.every_hours);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  useEffect(load, [load]);

  async function save() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await api.saveSettings({ backup_dir: dir.trim(), backup_keep: keep, backup_every_hours: hours });
      setNotice(dir.trim() ? "저장했습니다. [지금 백업]으로 한 번 확인해 보세요." : "자동 백업을 껐습니다.");
      load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card wide">
      <h2>자동 백업</h2>
      <p className="hint">
        정한 폴더로 <b>전체 자료를 zip 한 벌</b>씩 내보냅니다. 폴더를 <b>네트워크 드라이브나
        외장 디스크</b>로 잡으면 PC가 고장 나도 자료가 남습니다.
        <br />
        프로그램이 <b>켜져 있는 동안</b> 주기마다 확인해서, 때가 되면 저절로 한 벌 남깁니다.
        폴더를 비우면 자동 백업이 꺼집니다.
      </p>

      <div className="form-row">
        <label className="grow">
          백업 폴더
          <span className="input-with-button">
            {/* placeholder 를 중괄호로 감싼 이유 — JSX 의 따옴표 문자열은 이스케이프를
                풀지 않아 "\\" 가 화면에 두 글자로 그대로 보였다. */}
            <input
              value={dir}
              onChange={(event) => setDir(event.target.value)}
              placeholder={"예: D:\\백업\\과제이력  또는  \\\\공유서버\\백업"}
              spellCheck={false}
            />
            {/* 경로를 손으로 치면 오타 한 글자에 막힌다. 눌러서 고르는 길을 연다 (TODO 97). */}
            <button className="ghost small" onClick={() => setPicking((open) => !open)}>
              {picking ? "닫기" : "폴더 고르기"}
            </button>
          </span>
        </label>
        <label>
          남겨 둘 개수
          <input
            type="number"
            min={1}
            max={999}
            value={keep}
            onChange={(event) => setKeep(Number(event.target.value))}
          />
        </label>
        <label>
          주기 (시간)
          <input
            type="number"
            min={1}
            max={999}
            value={hours}
            onChange={(event) => setHours(Number(event.target.value))}
          />
        </label>
      </div>

      {picking && (
        <FolderPicker
          value={dir}
          onClose={() => setPicking(false)}
          onPick={(path) => {
            setDir(path);
            setPicking(false);
            // 고른 것만으로는 아직 아무 일도 일어나지 않는다. 다음 걸음을 말해 준다.
            setNotice("폴더를 골랐습니다. [저장]을 눌러야 적용됩니다.");
          }}
        />
      )}

      {notice && <p className="hint notice">{notice}</p>}
      {error && <p className="form-error">{error}</p>}

      {status && status.enabled && !status.reachable && (
        <p className="form-error">
          백업 폴더에 닿지 못합니다. 네트워크 드라이브가 끊겼거나 폴더가 사라졌을 수 있습니다.
        </p>
      )}

      {status && status.last && (
        <p className="hint">
          마지막 시도 {status.last.at}{" "}
          {status.last.ok ? (
            <span className="backup-ok">성공 · {status.last.file}</span>
          ) : (
            <span className="backup-fail">실패 · {status.last.error}</span>
          )}
        </p>
      )}

      {status && status.count > 0 && (
        <>
          <p className="hint">
            보관 중인 백업 <b>{status.count}</b>개 · {formatBytes(status.total_bytes)}
          </p>
          <ul className="backup-list">
            {status.recent.map((item) => (
              <li key={item.name}>
                <span className="backup-when">{item.at}</span>
                <code>{item.name}</code>
                <span className="muted">{formatBytes(item.size_bytes)}</span>
              </li>
            ))}
          </ul>
        </>
      )}

      <p className="hint">
        <b>백업 폴더를 데이터 폴더 안에 둘 수 없습니다</b> — 백업이 다음 백업에 담겨 계속 커집니다.
      </p>

      <div className="form-actions">
        <button className="ghost" disabled={busy || !status?.enabled} onClick={async () => {
          setBusy(true);
          setError(null);
          setNotice(null);
          try {
            const result = await api.backupNow();
            setNotice(`${result.file} 를 남겼습니다 (${formatBytes(result.bytes)}).`);
            load();
          } catch (err) {
            setError((err as Error).message);
          } finally {
            setBusy(false);
          }
        }}>
          지금 백업
        </button>
        <button disabled={busy} onClick={() => void save()}>
          {busy ? "저장 중…" : "저장"}
        </button>
      </div>
    </div>
  );
}
