import { useEffect } from "react";
import type { PasteOffer as Offer } from "../table";

/**
 * 엑셀 표를 표로 넣은 직후의 한 줄 — [그림으로 바꾸기] (TODO 149).
 *
 * 누르면 방금 넣은 표를 지우고, 그 자리에 붙여넣기와 함께 왔던 그림을 첨부로 올려 넣는다.
 * 편집기마다 올리는 길(`onFiles`)이 달라 그것만 받는다 — 표를 지우고 커서를 그 자리에 두는 일은 여기서 한다.
 * 20초가 지나거나 [×] 를 누르면 사라진다.
 */
export default function PasteOffer({
  offer,
  area,
  setValue,
  onFiles,
  onClose,
}: {
  offer: Offer | null;
  area: HTMLTextAreaElement | null;
  setValue: (next: string) => void;
  onFiles: (files: File[]) => void;
  onClose: () => void;
}) {
  useEffect(() => {
    if (!offer) return;
    const timer = window.setTimeout(onClose, 20000);
    return () => window.clearTimeout(timer);
  }, [offer, onClose]);

  if (!offer) return null;
  return (
    <div className="paste-offer" role="status">
      <span>엑셀 표를 <b>표로</b> 넣었습니다.</span>
      <button
        type="button"
        className="ghost small"
        onClick={() => {
          const value = area?.value ?? "";
          const at = value.indexOf(offer.table);
          onClose();
          if (at < 0 || !area) {
            onFiles([offer.image]);
            return;
          }
          setValue(value.slice(0, at) + value.slice(at + offer.table.length));
          // 값이 바뀐 뒤 커서를 표가 있던 자리에 두고 올린다 — 그림 링크가 그 자리에 들어간다
          window.requestAnimationFrame(() => {
            area.focus();
            area.setSelectionRange(at, at);
            onFiles([offer.image]);
          });
        }}
      >
        그림으로 바꾸기
      </button>
      <button type="button" className="ghost small" onClick={onClose} aria-label="닫기">
        ×
      </button>
    </div>
  );
}
