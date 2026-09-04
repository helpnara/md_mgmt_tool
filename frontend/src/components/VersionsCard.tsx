import { useEffect, useState } from "react";
import { api } from "../api";
import { formatBytes } from "../upload";

/**
 * 이전 버전 보관 현황.
 *
 * 되돌리기는 문서를 보고 있는 자리에서 한다([이전 버전] 단추). 여기서는
 * **얼마나 쌓여 있고 자리를 얼마나 쓰는지**만 알려 준다 — 안전망이 조용히
 * 커지고 있지 않은지 확인할 자리가 하나는 있어야 한다.
 */
export default function VersionsCard() {
  const [data, setData] = useState<{
    versions: number;
    documents: number;
    total_bytes: number;
    keep_days: number;
  } | null>(null);

  useEffect(() => {
    api.versionsOverview().then(setData).catch(() => setData(null));
  }, []);

  return (
    <div className="card">
      <h2>이전 버전 보관</h2>
      <p className="hint">
        문서를 <b>고쳐 저장할 때마다 직전 내용</b>을 한 벌 남깁니다. 잘못 고쳤을 때
        진행일지·개요·보고 화면의 <b>[이전 버전]</b>에서 되돌릴 수 있습니다.
        <br />
        삭제 보관함이 <i>지웠을 때</i>를 막아 준다면, 이쪽은 <i>잘못 고쳤을 때</i>를 막습니다.
      </p>
      {data === null ? (
        <p className="hint">불러오는 중…</p>
      ) : data.versions === 0 ? (
        <p className="hint">아직 보관된 이전 버전이 없습니다.</p>
      ) : (
        <p className="hint">
          문서 <b>{data.documents}</b>건 · 보관본 <b>{data.versions}</b>벌 ·{" "}
          {formatBytes(data.total_bytes)} · {data.keep_days}일 보관
        </p>
      )}
      <p className="hint">
        보관 위치는 <code>vault/.versions</code> 이며, 전부 텍스트라 자리를 거의 쓰지 않습니다.
        vault 폴더를 옮기면 안전망도 함께 갑니다.
      </p>
    </div>
  );
}
