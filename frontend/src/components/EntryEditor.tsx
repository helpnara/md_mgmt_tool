import { storageGet, storageSet } from "../storage";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import { attempt, notifyError } from "../notify";
import { clockNow, discardQuestion, dropDraft, loadDraft, useDraftKeeper, useEditLedger, useUnsaved } from "../unsaved";
import { filesBase, renderMarkdown } from "../markdown";
import VersionPanel from "./VersionPanel";
import type { Entry } from "../types";
import type { Attachment } from "../upload";
import { formatBytes, formatRate, uploadAttachment } from "../upload";
import PasteOfferBar from "./PasteOffer";
import { type PasteOffer, handleEditorPaste } from "../table";
import { scrollEditorIntoView, todayIso } from "../util";
import AttachmentList from "./AttachmentList";
import PreviewToggle, { usePreview } from "./PreviewToggle";
import TagSuggestions from "./TagSuggestions";
import { DATE_MIN, LIMITS, dateProblem, lengthHint, titleProblem, today, warningList } from "../inputRules";

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
  /** 이미 쓰고 있는 태그 — 눌러서 덧붙일 수 있게 보여 준다 */
  knownTags?: string[];
  dirName?: string;
  initial?: Partial<Entry>;
  onSaved: (entry: Entry, options: { close: boolean }) => void;
  onCancel: () => void;
  /** 이 문서의 vault 기준 경로. 있으면 [이전 버전]을 열 수 있다 (TODO 37-1). */
  docPath?: string;
  /** 되돌린 뒤 화면을 다시 읽는다. */
  onRestored?: () => void;
  /** 과제 기간 — 기록 날짜가 밖이면 알린다(막지는 않는다) (TODO 214 D5) */
  period?: { start?: string | null; due?: string | null };
}

/** 임시 보관 열쇠 (TODO 170) — 새 기록은 과제로, 고치는 기록은 그 번호로. 데이터 폴더의 `.drafts/` 에 남는다. */
function draftKey(projectId: string, entryId: number | null): string {
  return `entry:${entryId ?? `new-${projectId}`}`;
}

/**
 * 열쇠들을 **한 번씩만** 지운다 (TODO 215). 있는 기록을 고칠 때는 "처음 연 열쇠" 와 "이 기록의 열쇠" 가 똑같이
 * `entry:186` 이라 DELETE 가 같은 파일에 동시에 두 번 갔다 — 윈도우에서 뒤의 것이 WinError 5 로 최근 오류에 쌓였다.
 */
function dropDrafts(...keys: string[]): void {
  for (const key of new Set(keys)) dropDraft(key);
}

interface EntryDraft {
  date: string;
  title: string;
  body: string;
  tags: string;
}

export default function EntryEditor({ projectId, knownTags = [], dirName, initial, onSaved, onCancel, docPath, onRestored, period }: Props) {
  const [showVersions, setShowVersions] = useState(false);
  const [entryId, setEntryId] = useState<number | null>(initial?.id ?? null);
  const [date, setDate] = useState(initial?.date ?? todayIso());
  const [title, setTitle] = useState(initial?.title ?? "");
  const [body, setBody] = useState(initial?.body ?? "");
  const [tags, setTags] = useState((initial?.tags ?? []).join(", "));
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [uploads, setUploads] = useState<UploadState[]>([]);
  const [autosave, setAutosave] = useState(
    () => storageGet(AUTOSAVE_PREF_KEY) === "on", // 사이트 데이터가 막힌 PC 에서도 (TODO 212)
  );
  const [dirty, setDirty] = useState(false);
  // 편집 한 번의 장부 (TODO 213) — 이번에 올린 첨부 · 지우기로 한 첨부(첨부 번호)
  const ledger = useEditLedger<number>();
  // 첨부를 올리느라 먼저 만든 새 기록 — [저장](또는 켜 둔 자동 저장)이 한 번 돌기 전까지는 **임시**다.
  // [닫기] → 버리기면 이 기록도 지운다(삭제 보관함으로). ref 는 비동기 저장 · 버리기가 최신 값을 보게.
  const [provisionalId, setProvisionalId] = useState<number | null>(null);
  const provisionalRef = useRef<number | null>(null);
  const setProvisional = (id: number | null) => {
    provisionalRef.current = id;
    setProvisionalId(id);
  };
  // 떠날 때 묻는다 (TODO 162) — 임시 보관은 이 편집기가 처음부터 해 왔다.
  // 장부가 비어 있지 않아도 묻는다. 다만 떠날 때는 **지우지 않는다** — 임시 보관이 남아 다시 이어 쓰므로(TODO 213 의 남는 것).
  useUnsaved(`entry:${initial?.id ?? `new-${projectId}`}`, dirty || !ledger.empty || provisionalId !== null);
  // 이 편집에서 마지막으로 저장한 때 — 버릴 때 "마지막 (자동) 저장 이후" 로 묻는다 (TODO 213 ④)
  const [lastSave, setLastSave] = useState<{ at: string; auto: boolean } | null>(null);
  const [discarding, setDiscarding] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // 저장은 했지만 서버가 알린 것 — 과제 기간 밖 등 (TODO 214 D5)
  const [notice, setNotice] = useState<string | null>(null);
  const [restored, setRestored] = useState(false);
  const [preview, togglePreview] = usePreview();
  // 날짜 · 제목 검사 (TODO 214 D5 · D14) — 미래 날짜는 막고, 과제 기간 밖은 알린다
  const todayDay = today();
  const dateError =
    dateProblem(date, "날짜") ??
    (date && date > todayDay ? `진행일지는 오늘(${todayDay}) 이후 날짜로 적을 수 없습니다 — 계획은 본문의 「계획」에 적습니다.` : null);
  const outsidePeriod =
    !dateError && date && ((period?.start && date < period.start) || (period?.due && date > period.due))
      ? `과제 기간(${period?.start ?? "…"} ~ ${period?.due ?? "…"}) 밖의 날짜입니다 — 맞는지 확인해 주세요.`
      : null;
  const titleError = titleProblem(title, "제목");
  const titleLeft = lengthHint(title, LIMITS.title);
  const blocker = dateError ?? titleError;
  const blockerRef = useRef(blocker);
  blockerRef.current = blocker;
  // 기간 밖 안내를 이미 칸 옆에 보였으면 저장 뒤 같은 말을 다시 띄우지 않는다
  const outsideRef = useRef(Boolean(outsidePeriod));
  outsideRef.current = Boolean(outsidePeriod);

  const rootRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  // 엑셀 표를 넣은 직후의 [그림으로 바꾸기] (TODO 149)
  const [pasteOffer, setPasteOffer] = useState<PasteOffer | null>(null);
  const closeOffer = useCallback(() => setPasteOffer(null), []);

  // 열리자마자 그 자리로 데려간다 (1단으로 바뀌며 위치가 달라지기 때문).
  useEffect(() => scrollEditorIntoView(rootRef.current), []);

  const fileInputRef = useRef<HTMLInputElement>(null);
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

  // 저장 전에 창을 닫아도 작성 중이던 내용을 잃지 않도록 **데이터 폴더에** 초안을 남긴다 (TODO 170).
  // 전에는 브라우저 안에 남겨, 창 하나만 닫고 다른 창에서 열면 "작성 중이던 기록 있음" 이 안 뜨기도 했다(v7 B-6).
  useEffect(() => {
    let alive = true;
    const original = { body: initial?.body ?? "", title: initial?.title ?? "" };
    void loadDraft<EntryDraft>(
      draftKey(projectId, initial?.id ?? null),
      (draft) => draft?.body === original.body && draft?.title === original.title,
    ).then((draft) => {
      if (!alive || !draft || typeof draft !== "object") return;
      setDate(draft.date ?? todayIso());
      setTitle(draft.title ?? "");
      setBody(draft.body ?? "");
      setTags(draft.tags ?? "");
      setRestored(true);
      setDirty(true);
    });
    return () => {
      alive = false;
    };
    // 최초 1회만 복구한다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 자동 저장으로 새 기록이 생긴 뒤에는 그 번호로 남긴다 — 다시 열 때 새 기록으로 한 번 더 생기지 않게
  useDraftKeeper(draftKey(projectId, entryId), { date, title, body, tags }, !dirty);

  /**
   * 저장. `origin` — "user"([저장] · Ctrl+S) · "auto"(켜 둔 자동 저장) · "attach"(첨부를 올리려고 기록 번호가 필요할 때).
   * "attach" 로 새 기록이 생기면 그 기록은 임시다 — 장부를 확정하지 않는다 (TODO 213 ①).
   */
  const save = useCallback(
    async (options: { close: boolean }, origin: "user" | "auto" | "attach" = "user"): Promise<Entry> => {
      // 서버가 거절할 값이면 보내지 않는다 — 칸 옆에 이유가 이미 있다 (TODO 214 U2)
      if (blockerRef.current) throw new Error(blockerRef.current);
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
      const created = !current.entryId;
      const entry = current.entryId
        ? await api.updateEntry(current.entryId, payload)
        : await api.createEntry(projectId, payload);
      stateRef.current = { ...stateRef.current, entryId: entry.id };
      setEntryId(entry.id);
      if (origin === "attach") {
        if (created) setProvisional(entry.id);
      } else {
        // 사용자가 저장했다 — 임시 기록은 이제 진짜 기록이고, 이번에 올린 첨부도 저장된 것이다.
        // 지우기로 한 첨부는 **지금** 지운다 (TODO 213 ③).
        setProvisional(null);
        await ledger.commit((id) => api.deleteAttachment(id));
        setLastSave({ at: clockNow(), auto: origin === "auto" });
      }
      setDirty(false);
      setRestored(false);
      dropDrafts(draftKey(projectId, initial?.id ?? null), draftKey(projectId, entry.id));
      // 서버가 막지 않고 알린 것 (D5) — 닫으면 아래 알림으로, 열어 두면 편집기 안에
      const warnings = warningList(entry, outsideRef.current ? /기간/ : undefined);
      if (warnings.length > 0 && origin !== "attach") {
        if (options.close) for (const warning of warnings) notifyError(`저장했습니다 — ${warning}`);
        else setNotice(warnings.join(" · "));
      } else if (origin !== "attach") setNotice(null);
      onSaved(entry, options);
      if (origin !== "attach" && entry.id) refreshAttachments(entry.id);
      return entry;
    },
    // ledger 의 함수는 ref 를 보므로 렌더마다 바뀌어도 같다
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [projectId, initial?.id, onSaved, refreshAttachments],
  );

  // 자동 저장: 입력이 멈추고 10초 뒤에 저장한다. 고칠 칸이 있으면 기다린다 (TODO 214)
  useEffect(() => {
    if (!autosave || !dirty || blocker) return;
    const timer = window.setTimeout(() => {
      save({ close: false }, "auto").catch((err: Error) => setError(err.message));
    }, AUTOSAVE_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [autosave, dirty, date, title, body, tags, save, blocker]);

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

  /**
   * 첨부는 진행일지에 붙으므로, 아직 저장 전이면 먼저 기록을 만든다.
   * 그 기록은 [저장] 전까지 임시다 — [닫기] 로 버리면 지운다 (TODO 213 ①).
   */
  async function ensureEntryId(): Promise<number> {
    if (stateRef.current.entryId) return stateRef.current.entryId;
    const entry = await save({ close: false }, "attach");
    return entry.id;
  }

  /**
   * [닫기] — "닫으면 아무것도 바뀌지 않는다" (TODO 213). 쓴 것이 있거나 이 편집에서 서버에 먼저 쓴 것이 있으면
   * 사실대로 묻고, 버리기로 하면 이번에 올린 첨부와 임시 기록을 지운다(삭제 보관함으로). 지우기로 한 첨부는 그대로 둔다.
   */
  async function discard() {
    const provisional = provisionalRef.current;
    const ask = dirty || !ledger.empty || provisional !== null;
    if (
      ask &&
      !window.confirm(
        discardQuestion({
          what: "기록을",
          savedAt: lastSave?.at,
          auto: lastSave?.auto,
          createdEntry: provisional !== null,
          uploaded: ledger.uploaded.length,
          doomed: ledger.doomedExisting.length,
        }),
      )
    )
      return;
    setDiscarding(true);
    // 올리는 중인 것은 멈춘다 — 다 올라온 뒤에 남지 않게
    for (const upload of uploads) if (!upload.error) upload.abort();
    await ledger.rollback((id) => api.deleteAttachment(id));
    if (provisional !== null) {
      try {
        await api.deleteEntry(provisional);
      } catch (err) {
        notifyError(`먼저 만든 기록을 지우지 못했습니다 — ${(err as Error).message}`);
      }
      setProvisional(null);
    }
    dropDrafts(draftKey(projectId, entryId), draftKey(projectId, initial?.id ?? null));
    setDiscarding(false);
    onCancel();
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

    // 자리표시자는 한 번에 넣는다. 파일마다 커서 위치를 다시 읽으면, 앞 파일이
    // 업로드되는 동안 본문이 길어져 두 번째 첨부가 첫 번째 링크 한가운데 끼어든다.
    const placeholders = files.map((file, index) =>
      files.length > 1 ? `⏳ 업로드 중: ${file.name} (${index + 1})` : `⏳ 업로드 중: ${file.name}`,
    );
    insertAtCursor(placeholders.join("\n"));

    for (const [index, file] of files.entries()) {
      const key = `${file.name}-${Date.now()}-${index}`;
      const placeholder = placeholders[index];

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
        // 이번 편집에서 올린 것 — 버리면 지운다. 같은 파일이 이미 있어 그것을 돌려받았으면(deduplicated) 남의 것이라 적지 않는다
        if (!saved.deduplicated) ledger.addUploaded(saved.id);
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
      ref={rootRef}
      className="entry-editor card"
      onKeyDown={(event) => {
        // 문서 편집기 습관대로 Ctrl+S 로 저장한다 (브라우저 저장 창은 막는다).
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
          event.preventDefault();
          if (!busy && !discarding) void save({ close: false }).catch((err: Error) => setError(err.message));
        }
      }}
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
            min={DATE_MIN}
            max={todayDay}
            onChange={(event) => {
              setDate(event.target.value);
              markDirty();
            }}
            aria-invalid={dateError ? true : undefined}
          />
          {/* 비우면 서버가 오늘로 남긴다 — 말없이 바뀌지 않게 (TODO 214 U10) */}
          {!date && <span className="hint">비우면 오늘</span>}
          {dateError && <span className="form-warn date-warn">{dateError}</span>}
          {outsidePeriod && <span className="hint warn-text">{outsidePeriod}</span>}
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
            aria-invalid={titleError ? true : undefined}
          />
          {titleError ? (
            <span className="form-warn">{titleError}</span>
          ) : (
            titleLeft && <span className="hint length-count">{titleLeft}</span>
          )}
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
          <TagSuggestions
            known={knownTags}
            value={tags}
            onPick={(next) => {
              setTags(next);
              markDirty();
            }}
          />
        </label>
      </div>

      <PreviewToggle on={preview} onToggle={togglePreview} />

      <div className={preview ? "split" : "split solo"}>
        <textarea
          ref={textareaRef}
          value={body}
          onChange={(event) => {
            setBody(event.target.value);
            markDirty();
          }}
          onPaste={(event) =>
            // 엑셀 표는 표로, 캡처는 첨부로 — 판단은 한 곳(table.ts)에서 (TODO 137)
            handleEditorPaste(event, {
              onInsert: (text) => {
                insertAtCursor(text);
                markDirty();
              },
              onFiles: (files) => void handleFiles(files),
              onOffer: setPasteOffer,
            })
          }
          placeholder="진행 내용을 마크다운으로 작성합니다. 이미지는 Ctrl+V로 바로 붙여넣을 수 있습니다."
          spellCheck={false}
        />
        {preview && (
          <div
            className="preview markdown"
            dangerouslySetInnerHTML={{ __html: renderMarkdown(body, base) }}
          />
        )}
      </div>

      <PasteOfferBar
        offer={pasteOffer}
        area={textareaRef.current}
        setValue={(next) => {
          setBody(next);
          markDirty();
        }}
        onFiles={(files) => void handleFiles(files)}
        onClose={closeOffer}
      />

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
          <div className="attach-actions">
            <span className="hint">이미지는 Ctrl+V, 파일은 끌어다 놓아도 됩니다.</span>
            <button className="attach-button" onClick={() => fileInputRef.current?.click()}>
              📎 파일 첨부
            </button>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              hidden
              onChange={(event) => {
                void handleFiles(Array.from(event.target.files ?? []));
                event.target.value = "";  // 같은 파일을 다시 골라도 반응하도록 비운다
              }}
            />
          </div>
        </div>
        {/* 편집기 안의 [삭제] 는 "지울 예정" 으로만 — 실제 삭제는 [저장] 때, 버리면 아무 일도 없다 (TODO 213 ③) */}
        <AttachmentList
          attachments={attachments}
          onInsert={(attachment) => insertAtCursor(`\n${attachment.markdown}\n`)}
          pending={(attachment) => ledger.isDoomed(attachment.id)}
          onDelete={(attachment) => ledger.toggleDoomed(attachment.id)}
          onRestore={(attachment) => ledger.toggleDoomed(attachment.id)}
        />
        {ledger.doomed.length > 0 && (
          <p className="hint pending-note">지울 예정인 첨부 {ledger.doomed.length}건은 [저장] 할 때 삭제 보관함으로 옮깁니다.</p>
        )}
      </div>

      {restored && <p className="hint restored">저장하지 않은 작성 중 내용을 복구했습니다.</p>}
      {provisionalId !== null && (
        <p className="hint provisional-note">
          첨부를 올리려고 기록을 먼저 만들었습니다 — [저장] 하지 않고 닫으면 이 기록과 이번에 올린 첨부를 지웁니다.
        </p>
      )}
      <div className="editor-footer">
        {/* 오류 · 알림은 단추 바로 위에 — 첨부 목록 아래에서는 놓쳤다 (TODO 214 U5) */}
        {notice && <p className="hint warn-text entry-notice">{notice}</p>}
        {(error || blocker) && (
          <p className="form-error entry-error" role="alert">
            {error ?? `저장하려면 — ${blocker}`}
            {error?.includes("다시 읽기") && (
              <button
                className="ghost small"
                onClick={async () => {
                  if (await attempt(() => api.reindex())) window.location.reload();
                }}
              >
                지금 다시 읽기
              </button>
            )}
          </p>
        )}
        <label className="toggle">
          <input
            type="checkbox"
            checked={autosave}
            onChange={(event) => {
              setAutosave(event.target.checked);
              storageSet(AUTOSAVE_PREF_KEY, event.target.checked ? "on" : "off");
            }}
          />
          자동 저장 (입력이 멈추면 10초 뒤)
        </label>
        <span className="muted save-state">
          {dirty || !ledger.empty || provisionalId !== null
            ? "저장 안 됨"
            : lastSave
              ? `${lastSave.at} ${lastSave.auto ? "자동 저장됨" : "저장됨"}`
              : ""}
        </span>
        <div className="form-actions">
          {docPath && (
            <button data-write
              type="button"
              className={showVersions ? "ghost on" : "ghost"}
              onClick={() => setShowVersions((prev) => !prev)}
              title="이 진행일지의 이전 내용으로 되돌립니다."
            >
              이전 버전
            </button>
          )}
          <button
            type="button"
            className="ghost"
            disabled={discarding}
            onClick={() => void discard()}
          >
            {discarding ? "지우는 중…" : "닫기"}
          </button>
          <button
            type="button"
            disabled={busy || discarding || Boolean(blocker)}
            title={blocker ?? undefined}
            onClick={async () => {
              setBusy(true);
              try {
                await save({ close: true }, "user");
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

      {docPath && showVersions && (
        <VersionPanel path={docPath} onRestored={() => onRestored?.()} />
      )}
    </div>
  );
}
