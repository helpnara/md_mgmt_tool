import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import { filesBase, renderMarkdown } from "../markdown";
import type { Entry } from "../types";
import type { Attachment } from "../upload";
import { formatBytes, formatRate, uploadAttachment } from "../upload";
import { todayIso } from "../util";
import AttachmentList from "./AttachmentList";

const AUTOSAVE_DELAY_MS = 10_000;
const AUTOSAVE_PREF_KEY = "md-mgmt:autosave";

interface UploadState {
  key: string;
  name: string;
  loaded: number;
  total: number;
  startedAt: number;
  abort: () => void;
  error?: string;
}

interface Props {
  projectId: string;
  dirName?: string;
  initial?: Partial<Entry>;
  onSaved: (entry: Entry, options: { close: boolean }) => void;
  onCancel: () => void;
}

function draftKey(projectId: string, entryId: number | null): string {
  return `md-mgmt:draft:${entryId ?? `new-${projectId}`}`;
}

export default function EntryEditor({ projectId, dirName, initial, onSaved, onCancel }: Props) {
  const [entryId, setEntryId] = useState<number | null>(initial?.id ?? null);
  const [date, setDate] = useState(initial?.date ?? todayIso());
  const [title, setTitle] = useState(initial?.title ?? "");
  const [body, setBody] = useState(initial?.body ?? "");
  const [tags, setTags] = useState((initial?.tags ?? []).join(", "));
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [uploads, setUploads] = useState<UploadState[]>([]);
  const [autosave, setAutosave] = useState(
    () => localStorage.getItem(AUTOSAVE_PREF_KEY) === "on",
  );
  const [dirty, setDirty] = useState(false);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [restored, setRestored] = useState(false);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  // 자동 저장 타이머가 항상 최신 값을 보게 한다.
  const stateRef = useRef({ entryId, date, title, body, tags });
  stateRef.current = { entryId, date, title, body, tags };

  // 진행일지는 logs/ 안에 있으므로 첨부 링크(../assets/…)의 기준도 logs/ 다.
  const base = filesBase(dirName, "logs");

  const refreshAttachments = useCallback((id: number) => {
    api.listEntryAttachments(id).then(setAttachments).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (entryId) refreshAttachments(entryId);
  }, [entryId, refreshAttachments]);

  // 저장 전에 창을 닫아도 작성 중이던 내용을 잃지 않도록 브라우저에 초안을 남긴다.
  useEffect(() => {
    const key = draftKey(projectId, initial?.id ?? null);
    const stored = localStorage.getItem(key);
    if (!stored) return;
    try {
      const draft = JSON.parse(stored);
      if (draft.body !== (initial?.body ?? "") || draft.title !== (initial?.title ?? "")) {
        setDate(draft.date ?? date);
        setTitle(draft.title ?? "");
        setBody(draft.body ?? "");
        setTags(draft.tags ?? "");
        setRestored(true);
        setDirty(true);
      }
    } catch {
      localStorage.removeItem(key);
    }
    // 최초 1회만 복구한다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!dirty) return;
    localStorage.setItem(
      draftKey(projectId, initial?.id ?? null),
      JSON.stringify({ date, title, body, tags }),
    );
  }, [dirty, projectId, initial?.id, date, title, body, tags]);

  const save = useCallback(
    async (options: { close: boolean }): Promise<Entry> => {
      const current = stateRef.current;
      const payload = {
        date: current.date,
        title: current.title.trim() || "진행 기록",
        body: current.body,
        tags: current.tags
          .split(",")
          .map((tag) => tag.trim())
          .filter(Boolean),
      };
      const entry = current.entryId
        ? await api.updateEntry(current.entryId, payload)
        : await api.createEntry(projectId, payload);
      setEntryId(entry.id);
      setDirty(false);
      setRestored(false);
      setSavedAt(new Date().toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" }));
      localStorage.removeItem(draftKey(projectId, initial?.id ?? null));
      onSaved(entry, options);
      return entry;
    },
    [projectId, initial?.id, onSaved],
  );

  // 자동 저장: 입력이 멈추고 10초 뒤에 저장한다.
  useEffect(() => {
    if (!autosave || !dirty) return;
    const timer = window.setTimeout(() => {
      save({ close: false }).catch((err: Error) => setError(err.message));
    }, AUTOSAVE_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [autosave, dirty, date, title, body, tags, save]);

  function markDirty() {
    setDirty(true);
    setError(null);
  }

  /** 첨부 링크가 앞뒤 문장과 붙지 않도록 줄바꿈을 보충해 삽입한다. */
  function insertAtCursor(snippet: string) {
    const textarea = textareaRef.current;
    const start = textarea ? textarea.selectionStart : body.length;
    const end = textarea ? textarea.selectionEnd : body.length;

    let inserted = snippet;
    setBody((prev) => {
      const before = prev.slice(0, start);
      const after = prev.slice(end);
      const lead = before.length > 0 && !before.endsWith("\n") ? "\n\n" : "";
      const trail = after.startsWith("\n") || after.length === 0 ? "\n" : "\n\n";
      inserted = `${lead}${snippet}${trail}`;
      return `${before}${inserted}${after}`;
    });

    if (textarea) {
      window.requestAnimationFrame(() => {
        textarea.focus();
        const caret = start + inserted.length;
        textarea.setSelectionRange(caret, caret);
      });
    }
    markDirty();
  }

  /** 첨부는 진행일지에 붙으므로, 아직 저장 전이면 먼저 기록을 만든다. */
  async function ensureEntryId(): Promise<number> {
    if (stateRef.current.entryId) return stateRef.current.entryId;
    const entry = await save({ close: false });
    return entry.id;
  }

  async function handleFiles(files: File[]) {
    if (files.length === 0) return;
    let targetId: number;
    try {
      targetId = await ensureEntryId();
    } catch (err) {
      setError((err as Error).message);
      return;
    }

    for (const file of files) {
      const key = `${file.name}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
      // 이미지 문법으로 두면 미리보기에 깨진 이미지가 보이므로 평문으로 표시한다.
      const placeholder = `⏳ 업로드 중: ${file.name}`;
      insertAtCursor(placeholder);

      const handle = uploadAttachment(`/api/entries/${targetId}/attachments`, file, (loaded, total) => {
        setUploads((prev) =>
          prev.map((item) => (item.key === key ? { ...item, loaded, total } : item)),
        );
      });
      setUploads((prev) => [
        ...prev,
        {
          key,
          name: file.name,
          loaded: 0,
          total: file.size,
          startedAt: Date.now(),
          abort: handle.abort,
        },
      ]);

      try {
        const saved = await handle.promise;
        setBody((prev) => prev.replace(placeholder, saved.markdown));
        setUploads((prev) => prev.filter((item) => item.key !== key));
        refreshAttachments(targetId);
        markDirty();
      } catch (err) {
        setBody((prev) => prev.replace(`${placeholder}\n`, "").replace(placeholder, ""));
        setUploads((prev) =>
          prev.map((item) =>
            item.key === key ? { ...item, error: (err as Error).message } : item,
          ),
        );
      }
    }
  }

  return (
    <div
      className="entry-editor card"
      onDragOver={(event) => event.preventDefault()}
      onDrop={(event) => {
        event.preventDefault();
        void handleFiles(Array.from(event.dataTransfer.files));
      }}
    >
      <div className="form-row">
        <label>
          날짜
          <input
            type="date"
            value={date}
            onChange={(event) => {
              setDate(event.target.value);
              markDirty();
            }}
          />
        </label>
        <label className="grow">
          제목
          <input
            value={title}
            onChange={(event) => {
              setTitle(event.target.value);
              markDirty();
            }}
            placeholder="예: 1차 측정 결과"
          />
        </label>
        <label>
          태그
          <input
            value={tags}
            onChange={(event) => {
              setTags(event.target.value);
              markDirty();
            }}
            placeholder="측정, 분석"
          />
        </label>
      </div>

      <div className="split">
        <textarea
          ref={textareaRef}
          value={body}
          onChange={(event) => {
            setBody(event.target.value);
            markDirty();
          }}
          onPaste={(event) => {
            const files = Array.from(event.clipboardData.files);
            if (files.length > 0) {
              event.preventDefault();
              void handleFiles(files);
            }
          }}
          placeholder="진행 내용을 마크다운으로 작성합니다. 이미지는 Ctrl+V로 바로 붙여넣을 수 있습니다."
          spellCheck={false}
        />
        <div
          className="preview markdown"
          dangerouslySetInnerHTML={{ __html: renderMarkdown(body, base) }}
        />
      </div>

      {uploads.length > 0 && (
        <ul className="uploads">
          {uploads.map((upload) => {
            const percent = upload.total ? Math.round((upload.loaded / upload.total) * 100) : 0;
            const elapsed = (Date.now() - upload.startedAt) / 1000;
            const rate = elapsed > 0 ? upload.loaded / elapsed : 0;
            return (
              <li key={upload.key} className={upload.error ? "upload-error" : undefined}>
                <div className="upload-head">
                  <span className="upload-name">{upload.name}</span>
                  <span className="muted">
                    {upload.error
                      ? upload.error
                      : `${formatBytes(upload.loaded)} / ${formatBytes(upload.total)} · ${formatRate(rate)}`}
                  </span>
                  {upload.error ? (
                    <button
                      className="ghost small"
                      onClick={() => setUploads((prev) => prev.filter((item) => item.key !== upload.key))}
                    >
                      닫기
                    </button>
                  ) : (
                    <button className="ghost small" onClick={upload.abort}>
                      취소
                    </button>
                  )}
                </div>
                <div className="progress">
                  <div className="progress-bar" style={{ width: `${percent}%` }} />
                </div>
              </li>
            );
          })}
        </ul>
      )}

      <div className="attachment-panel">
        <div className="card-head">
          <h3>첨부 ({attachments.length})</h3>
          <span className="hint">이미지는 Ctrl+V, 그 밖의 파일은 끌어다 놓으면 첨부됩니다.</span>
        </div>
        <AttachmentList
          attachments={attachments}
          onInsert={(attachment) => insertAtCursor(`\n${attachment.markdown}\n`)}
          onDelete={async (attachment) => {
            if (!window.confirm(`${attachment.orig_name} 을(를) 보관함으로 옮길까요?`)) return;
            await api.deleteAttachment(attachment.id);
            if (entryId) refreshAttachments(entryId);
          }}
        />
      </div>

      {restored && <p className="hint restored">저장하지 않은 작성 중 내용을 복구했습니다.</p>}
      {error && (
        <p className="form-error">
          {error}
          {error.includes("다시 읽기") && (
            <button
              className="ghost small"
              onClick={async () => {
                await api.reindex();
                window.location.reload();
              }}
            >
              지금 다시 읽기
            </button>
          )}
        </p>
      )}

      <div className="editor-footer">
        <label className="toggle">
          <input
            type="checkbox"
            checked={autosave}
            onChange={(event) => {
              setAutosave(event.target.checked);
              localStorage.setItem(AUTOSAVE_PREF_KEY, event.target.checked ? "on" : "off");
            }}
          />
          자동 저장 (입력이 멈추면 10초 뒤)
        </label>
        <span className="muted save-state">
          {dirty ? "저장 안 됨" : savedAt ? `${savedAt} 저장됨` : ""}
        </span>
        <div className="form-actions">
          <button type="button" className="ghost" onClick={onCancel}>
            닫기
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                await save({ close: true });
              } catch (err) {
                setError((err as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            {busy ? "저장 중…" : "저장"}
          </button>
        </div>
      </div>
    </div>
  );
}
