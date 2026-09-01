import type { Attachment } from "../upload";
import { formatBytes } from "../upload";

interface Props {
  attachments: Attachment[];
  onInsert?: (attachment: Attachment) => void;
  onDelete?: (attachment: Attachment) => void;
  onPreview?: (attachment: Attachment) => void;
}

export default function AttachmentList({ attachments, onInsert, onDelete, onPreview }: Props) {
  if (attachments.length === 0) return <p className="hint">첨부된 파일이 없습니다.</p>;

  return (
    <ul className="attachments">
      {attachments.map((attachment) => (
        <li key={attachment.id} className={attachment.orphan ? "orphan" : undefined}>
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
            </span>
          </div>
          <div className="attachment-actions">
            {onPreview && attachment.preview_url && (
              <button className="ghost small" onClick={() => onPreview(attachment)}>
                내용 보기
              </button>
            )}
            {onInsert && (
              <button className="ghost small" onClick={() => onInsert(attachment)}>
                본문에 삽입
              </button>
            )}
            {onDelete && (
              <button className="ghost small danger" onClick={() => onDelete(attachment)}>
                삭제
              </button>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}
