import type { Attachment } from "../upload";
import { formatBytes } from "../upload";

interface Props {
  attachments: Attachment[];
  onInsert?: (attachment: Attachment) => void;
  onDelete?: (attachment: Attachment) => void;
  onPreview?: (attachment: Attachment) => void;
  /**
   * 편집기 안의 목록 (TODO 213 ③) — [삭제] 를 누르면 바로 지우지 않고 "지울 예정" 으로 남긴다. 실제 삭제는 [저장] 때,
   * 버리면 아무 일도 없다. 이 둘이 있으면 지울 예정인 줄에 [되살리기] 가 선다. 편집기 밖의 목록은 넘기지 않는다(바로 지운다).
   */
  pending?: (attachment: Attachment) => boolean;
  onRestore?: (attachment: Attachment) => void;
}

export default function AttachmentList({ attachments, onInsert, onDelete, onPreview, pending, onRestore }: Props) {
  if (attachments.length === 0) return <p className="hint">첨부된 파일이 없습니다.</p>;

  return (
    <ul className="attachments">
      {attachments.map((attachment) => {
        const doomed = pending?.(attachment) ?? false;
        return (
        <li
          key={attachment.id}
          className={[attachment.orphan ? "orphan" : "", doomed ? "pending-delete" : ""].filter(Boolean).join(" ") || undefined}
        >
          {attachment.is_image ? (
            <a href={attachment.url} target="_blank" rel="noreferrer">
              <img src={attachment.thumb_url ?? attachment.url} alt={attachment.orig_name} />
            </a>
          ) : (
            <span className="file-icon">{attachment.orig_name.split(".").pop()?.toUpperCase()}</span>
          )}
          <div className="attachment-info">
            <a href={attachment.url} target="_blank" rel="noreferrer" title={attachment.rel_path}>
              {attachment.orig_name}
            </a>
            <span className="muted">
              {formatBytes(attachment.size_bytes)}
              {attachment.orphan && <span className="orphan-tag">본문 미사용</span>}
              {doomed && (
                <span className="pending-tag" title="[저장] 할 때 삭제 보관함으로 옮깁니다. 저장하지 않고 닫으면 그대로 남습니다.">
                  지울 예정
                </span>
              )}
            </span>
          </div>
          <div className="attachment-actions">
            {/* GET 미리보기라 읽기 전용 공유에서도 보인다 — data-write 를 붙이지 않는다 (TODO 208) */}
            {onPreview && attachment.preview_url && (
              <button className="ghost small" onClick={() => onPreview(attachment)}>
                내용 보기
              </button>
            )}
            {onInsert && !doomed && (
              <button className="ghost small" onClick={() => onInsert(attachment)}>
                본문에 삽입
              </button>
            )}
            {doomed && onRestore ? (
              <button className="ghost small" onClick={() => onRestore(attachment)}>
                되살리기
              </button>
            ) : (
              onDelete && (
                <button className="ghost small danger" onClick={() => onDelete(attachment)}>
                  삭제
                </button>
              )
            )}
          </div>
        </li>
        );
      })}
    </ul>
  );
}
