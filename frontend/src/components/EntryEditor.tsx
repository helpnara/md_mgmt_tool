import { useState } from "react";
import { renderMarkdown } from "../markdown";
import type { Entry } from "../types";
import { todayIso } from "../util";

interface Props {
  initial?: Partial<Entry>;
  onSave: (payload: Partial<Entry>) => Promise<void>;
  onCancel: () => void;
}

export default function EntryEditor({ initial, onSave, onCancel }: Props) {
  const [date, setDate] = useState(initial?.date ?? todayIso());
  const [title, setTitle] = useState(initial?.title ?? "");
  const [body, setBody] = useState(initial?.body ?? "");
  const [tags, setTags] = useState((initial?.tags ?? []).join(", "));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSave() {
    setBusy(true);
    setError(null);
    try {
      await onSave({
        date,
        title: title.trim() || "진행 기록",
        body,
        tags: tags
          .split(",")
          .map((tag) => tag.trim())
          .filter(Boolean),
      });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="entry-editor card">
      <div className="form-row">
        <label>
          날짜
          <input type="date" value={date} onChange={(event) => setDate(event.target.value)} />
        </label>
        <label className="grow">
          제목
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="예: 1차 측정 결과"
          />
        </label>
        <label>
          태그
          <input value={tags} onChange={(event) => setTags(event.target.value)} placeholder="측정, 분석" />
        </label>
      </div>

      <div className="split">
        <textarea
          value={body}
          onChange={(event) => setBody(event.target.value)}
          placeholder="진행 내용을 마크다운으로 작성합니다."
          spellCheck={false}
        />
        <div className="preview markdown" dangerouslySetInnerHTML={{ __html: renderMarkdown(body) }} />
      </div>

      <p className="hint">첨부·이미지 붙여넣기는 다음 단계(M2)에서 추가됩니다.</p>
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button type="button" className="ghost" onClick={onCancel}>
          취소
        </button>
        <button type="button" onClick={handleSave} disabled={busy}>
          {busy ? "저장 중…" : "저장"}
        </button>
      </div>
    </div>
  );
}
