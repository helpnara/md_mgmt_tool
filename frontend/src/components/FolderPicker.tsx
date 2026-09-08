import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { FolderListing } from "../types";

/**
 * 폴더 고르기 (TODO 97).
 *
 * 자동 백업 폴더는 지금까지 `D:\백업\과제이력` 처럼 **전체 경로를 손으로 치는** 칸이었다.
 * 오타 한 글자면 "그런 폴더가 없습니다" 가 뜨고, 공유 폴더 주소(`\\서버\백업`)는 길어서
 * 더 자주 틀린다.
 *
 * **브라우저의 폴더 선택 창은 쓸 수 없다.** 웹 페이지는 고른 폴더의 *실제 경로*를 받지
 * 못한다 — `<input webkitdirectory>` 도 File System Access API 도 상대 이름이나 손잡이만
 * 줄 뿐이다. 그래서 **서버가 폴더 목록을 주고 여기서 눌러 들어간다.**
 * 이 도구는 본인 PC에서 도는 프로그램이라 서버가 곧 그 PC다.
 */
export default function FolderPicker({
  value,
  onPick,
  onClose,
}: {
  /** 지금 정해져 있는 경로. 있으면 그 자리에서 시작한다. */
  value: string;
  onPick: (path: string) => void;
  onClose: () => void;
}) {
  const [at, setAt] = useState(value.trim());
  const [data, setData] = useState<FolderListing | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [find, setFind] = useState("");
  const [newName, setNewName] = useState("");
  const [making, setMaking] = useState(false);

  const load = useCallback(
    (path: string) => {
      setError(null);
      api
        .listFolders(path)
        .then((next) => {
          setData(next);
          setAt(next.path);
          setFind("");
          setMaking(false);
          setNewName("");
        })
        // 정해 둔 폴더가 없어졌을 수 있다 (네트워크 드라이브가 안 잡혔다든지).
        // 그때는 처음 자리로 물러난다 — 빈 화면을 주지 않는다.
        .catch((err: Error) => {
          setError(err.message);
          if (path) api.listFolders("").then(setData).catch(() => setData(null));
        });
    },
    [],
  );

  useEffect(() => load(value.trim()), [load, value]);

  const folders = (data?.folders ?? []).filter((item) =>
    find ? item.name.toLowerCase().includes(find.toLowerCase()) : true,
  );

  async function makeFolder() {
    try {
      const made = await api.createFolder(at, newName);
      load(made.path);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div className="folder-picker">
      <div className="folder-head">
        <button
          className="ghost small"
          disabled={data?.parent === null}
          onClick={() => load(data?.parent ?? "")}
          title={at ? "한 단계 위로" : "여기가 처음 자리입니다"}
        >
          ↑ 위로
        </button>
        <code className="folder-at">{at || "내 PC"}</code>
        <input
          type="search"
          className="folder-find"
          value={find}
          onChange={(event) => setFind(event.target.value)}
          placeholder="이 안에서 이름으로 찾기"
        />
      </div>

      {error && <p className="form-error">{error}</p>}

      <ul className="folder-list">
        {folders.map((item) => (
          <li key={item.path}>
            <button className="folder-row" onClick={() => load(item.path)} title={item.path}>
              <span className="folder-icon" aria-hidden="true">
                📁
              </span>
              {item.name}
            </button>
          </li>
        ))}
        {folders.length === 0 && (
          <li className="folder-empty">
            {find ? "그 이름의 폴더가 없습니다." : "이 안에는 폴더가 없습니다."}
          </li>
        )}
      </ul>

      {data?.truncated && (
        <p className="hint">
          폴더가 너무 많아 앞의 것만 보여 줍니다. 위의 <b>찾기</b> 칸으로 좁혀 보세요.
        </p>
      )}

      <div className="folder-actions">
        {making ? (
          <span className="folder-new">
            <input
              value={newName}
              onChange={(event) => setNewName(event.target.value)}
              placeholder="새 폴더 이름"
              autoFocus
              onKeyDown={(event) => {
                if (event.key === "Enter") void makeFolder();
                if (event.key === "Escape") setMaking(false);
              }}
            />
            <button className="ghost small" onClick={() => void makeFolder()}>
              만들기
            </button>
            <button className="ghost small" onClick={() => setMaking(false)}>
              취소
            </button>
          </span>
        ) : (
          <button className="ghost small" disabled={!at} onClick={() => setMaking(true)}>
            + 새 폴더
          </button>
        )}
        <span className="grow" />
        <button className="ghost small" onClick={onClose}>
          닫기
        </button>
        {/* 쓸 수 없는 폴더를 고르면 저장할 때 튕긴다. 고르기 전에 알려 주는 편이 낫다. */}
        <button disabled={!at || !data?.writable} onClick={() => onPick(at)}>
          {at && data && !data.writable ? "쓸 수 없는 폴더입니다" : "이 폴더로 정하기"}
        </button>
      </div>
    </div>
  );
}
