import { useEffect, useState } from "react";
import { api } from "../api";
import type { Attachment } from "../upload";
import type { SpreadsheetPreview } from "../types";

/** 보고에 쓴 엑셀을 그 자리에서 훑어본다. 서식은 재현하지 않는다. */
export default function XlsxPreview({
  attachment,
  onClose,
}: {
  attachment: Attachment;
  onClose: () => void;
}) {
  const [preview, setPreview] = useState<SpreadsheetPreview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.spreadsheetPreview(attachment.id).then(setPreview).catch((err: Error) => setError(err.message));
  }, [attachment.id]);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(event) => event.stopPropagation()}>
        <div className="card-head">
          <h2>{attachment.orig_name}</h2>
          <div className="form-actions" style={{ margin: 0 }}>
            <a className="ghost button-like" href={attachment.url} target="_blank" rel="noreferrer">
              원본 열기
            </a>
            <button className="ghost" onClick={onClose}>
              닫기
            </button>
          </div>
        </div>

        {error && <p className="form-error">{error}</p>}
        {!preview && !error && <p className="app-loading">불러오는 중…</p>}

        {preview?.sheets.map((sheet) => (
          <section key={sheet.name} className="sheet">
            <h3>{sheet.name}</h3>
            <div className="sheet-scroll">
              <table className="grid">
                <tbody>
                  {sheet.rows.map((row, rowIndex) => (
                    <tr key={rowIndex}>
                      {row.map((cell, cellIndex) => (
                        // 셀 안의 줄바꿈을 그대로 보여 준다 (한 칸에 여러 줄로 쓰는 양식이다).
                        <td key={cellIndex} className="sheet-cell">
                          {cell}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {sheet.images.map((source, index) => (
              <img key={index} className="sheet-image" src={source} alt={`${sheet.name} 이미지`} />
            ))}
          </section>
        ))}

        {preview && preview.sheets.length === 0 && <p className="hint">표시할 내용이 없습니다.</p>}
        {preview?.truncated && <p className="hint">긴 표는 일부만 표시합니다. 전체는 원본을 열어 확인하세요.</p>}
        <p className="hint">서식·수식은 재현하지 않습니다. 값과 삽입 이미지만 보여 줍니다.</p>
      </div>
    </div>
  );
}
