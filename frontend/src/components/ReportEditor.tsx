import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import { filesBase, renderMarkdown } from "../markdown";
import { copyAsExcelCell, copyAsPlainText, toPlainText } from "../plaintext";
import type { Report } from "../types";
import type { Attachment } from "../upload";
import { formatBytes, formatRate, uploadAttachment } from "../upload";
import { pasteAsTable } from "../table";
import { scrollEditorIntoView } from "../util";
import AttachmentList from "./AttachmentList";
import XlsxPreview from "./XlsxPreview";
import PreviewToggle, { usePreview } from "./PreviewToggle";
import ReportDiff from "./ReportDiff";

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
  report: Report;
  dirName?: string;
  /** 피보고자 자동완성 목록 */
  audiences: string[];
  onChanged: () => void;
  onClose: () => void;
}

export default function ReportEditor({ report, dirName, audiences, onChanged, onClose }: Props) {
  const [body, setBody] = useState(report.body ?? "");
  const [audience, setAudience] = useState(report.audience ?? "");
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [uploads, setUploads] = useState<UploadState[]>([]);
  const [previewing, setPreviewing] = useState<Attachment | null>(null);
  // 보고일. 초안일 때만 고칠 수 있다 — 확정된 보고의 날짜는 "언제 보고했는가"라는 사실이다.
  const [reportDate, setReportDate] = useState(report.report_date);
  const [preview, togglePreview] = usePreview();
  // "지난주와 뭐가 달라졌나" — 보고 자리에서 가장 많이 받는 질문이다.
  const [showDiff, setShowDiff] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // 보고 문서를 열면 좌측 칸이 맨 위로 올라온다. 문서가 있는 자리로 데려간다.
  useEffect(() => scrollEditorIntoView(rootRef.current), []);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const base = filesBase(dirName, report.doc_dir);
  const frozen = report.frozen;

  const refresh = useCallback(() => {
    api.listReportAttachments(report.id).then(setAttachments).catch(() => undefined);
  }, [report.id]);

  useEffect(refresh, [refresh]);
  useEffect(() => setBody(report.body ?? ""), [report.id, report.body]);
  useEffect(() => setAudience(report.audience ?? ""), [report.id, report.audience]);
  useEffect(() => setReportDate(report.report_date), [report.id, report.report_date]);

  async function save(): Promise<void> {
    // 보고일은 초안일 때만 보낸다. 바뀌면 서버가 문서 폴더도 함께 옮긴다.
    await api.updateReport(report.id, {
      body,
      audience,
      ...(frozen ? {} : { report_date: reportDate }),
    });
    setDirty(false);
    onChanged();
  }

  /** 초안에 딸려 온 "진행 내용"만 지우고 보고서 뼈대는 남긴다. */
  function clearProgressSection() {
    if (!window.confirm("초안에 붙어 온 '진행 내용'을 지울까요? 요약·특이사항·다음 계획은 남습니다.")) {
      return;
    }
    setBody((prev) => {
      const start = prev.indexOf("## 진행 내용");
      if (start < 0) return prev;
      const rest = prev.slice(start + 1);
      const nextHeading = rest.indexOf("\n## ");
      return nextHeading < 0 ? prev.slice(0, start).trimEnd() + "\n" : prev.slice(0, start) + rest.slice(nextHeading + 1);
    });
    setDirty(true);
  }

  function insertAtCursor(snippet: string) {
    const textarea = textareaRef.current;
    const start = textarea ? textarea.selectionStart : body.length;
    setBody((prev) => `${prev.slice(0, start)}\n${snippet}\n${prev.slice(start)}`);
    setDirty(true);
  }

  async function handleFiles(files: File[]) {
    for (const file of files) {
      const key = `${file.name}-${Date.now()}`;
      const handle = uploadAttachment(`/api/reports/${report.id}/attachments`, file, (loaded, total) =>
        setUploads((prev) => prev.map((item) => (item.key === key ? { ...item, loaded, total } : item))),
      );
      setUploads((prev) => [
        ...prev,
        { key, name: file.name, loaded: 0, total: file.size, startedAt: Date.now(), abort: handle.abort },
      ]);
      try {
        await handle.promise;
        setUploads((prev) => prev.filter((item) => item.key !== key));
        refresh();
      } catch (err) {
        setUploads((prev) =>
          prev.map((item) => (item.key === key ? { ...item, error: (err as Error).message } : item)),
        );
      }
    }
  }

  async function copy(kind: "excel" | "plain") {
    const text = toPlainText(body);
    try {
      if (kind === "excel") await copyAsExcelCell(text);
      else await copyAsPlainText(text);
      setNotice(kind === "excel" ? "엑셀 한 칸에 붙여넣을 수 있게 복사했습니다." : "평문으로 복사했습니다.");
      window.setTimeout(() => setNotice(null), 4000);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div
      ref={rootRef}
      className={`report-editor card${frozen ? " frozen" : ""}`}
      onKeyDown={(event) => {
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
          event.preventDefault();
          if (!frozen) void save().catch((err: Error) => setError(err.message));
        }
      }}
      onDragOver={frozen ? undefined : (event) => event.preventDefault()}
      onDrop={
        frozen
          ? undefined
          : (event) => {
              event.preventDefault();
              void handleFiles(Array.from(event.dataTransfer.files));
            }
      }
    >
      <div className="card-head">
        <h2>
          {report.report_date} 보고
          {frozen ? (
            <span className="frozen-tag">확정됨 · 읽기 전용</span>
          ) : (
            <span className="draft-tag">작성 중</span>
          )}
        </h2>
        <div className="form-actions" style={{ margin: 0 }}>
          {!frozen && body.includes("## 진행 내용") && (
            <button className="ghost" onClick={clearProgressSection}>
              진행 내용 지우기
            </button>
          )}
          <button
            className={showDiff ? "ghost on" : "ghost"}
            onClick={() => setShowDiff((prev) => !prev)}
            title="직전에 확정한 보고와 비교합니다."
          >
            지난 보고 대비
          </button>
          <button className="ghost" onClick={() => copy("excel")}>
            엑셀 셀로 복사
          </button>
          <button className="ghost" onClick={() => copy("plain")}>
            평문 복사
          </button>
          <button className="ghost" onClick={onClose}>
            닫기
          </button>
        </div>
      </div>

      <div className="report-meta">
        <label className="report-date-field">
          보고일
          <input
            type="date"
            value={reportDate}
            disabled={frozen}
            title={frozen ? "확정된 보고의 날짜는 바꿀 수 없습니다. 확정을 풀면 고칠 수 있습니다." : undefined}
            onChange={(event) => {
              setReportDate(event.target.value);
              setDirty(true);
            }}
          />
        </label>
        <label>
          피보고자 · 회의체
          <input
            list="audience-options"
            value={audience}
            onChange={(event) => {
              setAudience(event.target.value);
              setDirty(true);
            }}
            placeholder="예: 팀장, 주간회의체"
          />
          <datalist id="audience-options">
            {audiences.map((name) => (
              <option key={name} value={name} />
            ))}
          </datalist>
        </label>
        {frozen && (
          <button
            className="ghost small"
            disabled={audience === (report.audience ?? "")}
            onClick={async () => {
              await api.updateReport(report.id, { audience });
              setDirty(false);
              onChanged();
            }}
          >
            피보고자만 저장
          </button>
        )}
        <span className="hint">
          {report.covers_from
            ? `포함 기간 ${report.covers_from} ~ ${report.covers_to} · 진행일지 ${report.entry_count}건`
            : "포함된 진행일지가 없습니다."}
          {report.author && ` · 작성 ${report.author}`}
        </span>
      </div>

      {showDiff && <ReportDiff reportId={report.id} />}

      {frozen ? (
        <div className="markdown snapshot" dangerouslySetInnerHTML={{ __html: renderMarkdown(body, base) }} />
      ) : (
        <>
        <PreviewToggle on={preview} onToggle={togglePreview} />
        <div className={preview ? "split" : "split solo"}>
          <textarea
            ref={textareaRef}
            value={body}
            onChange={(event) => {
              setBody(event.target.value);
              setDirty(true);
            }}
            onPaste={(event) => {
              const files = Array.from(event.clipboardData.files);
              if (files.length > 0) {
                event.preventDefault();
                void handleFiles(files);
                return;
              }
              // 보고 문서야말로 엑셀 표를 그대로 옮겨 오는 일이 잦다.
              if (pasteAsTable(event, insertAtCursor)) setDirty(true);
            }}
            spellCheck={false}
          />
          {preview && (
            <div className="preview markdown" dangerouslySetInnerHTML={{ __html: renderMarkdown(body, base) }} />
          )}
        </div>
        </>
      )}

      {uploads.length > 0 && (
        <ul className="uploads">
          {uploads.map((upload) => {
            const percent = upload.total ? Math.round((upload.loaded / upload.total) * 100) : 0;
            const elapsed = (Date.now() - upload.startedAt) / 1000;
            return (
              <li key={upload.key} className={upload.error ? "upload-error" : undefined}>
                <div className="upload-head">
                  <span className="upload-name">{upload.name}</span>
                  <span className="muted">
                    {upload.error
                      ? upload.error
                      : `${formatBytes(upload.loaded)} / ${formatBytes(upload.total)} · ${formatRate(
                          elapsed > 0 ? upload.loaded / elapsed : 0,
                        )}`}
                  </span>
                  {!upload.error && (
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
          <h3>보고 자료 ({attachments.length})</h3>
          {!frozen && (
            <div className="attach-actions">
              <span className="hint">엑셀·이미지를 끌어다 놓아도 됩니다.</span>
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
                  event.target.value = "";
                }}
              />
            </div>
          )}
        </div>
        <AttachmentList
          attachments={attachments}
          onPreview={(attachment) => setPreviewing(attachment)}
          onInsert={frozen ? undefined : (attachment) => insertAtCursor(attachment.markdown)}
        />
      </div>

      {notice && <p className="hint notice">{notice}</p>}
      {error && <p className="form-error">{error}</p>}

      <div className="editor-footer">
        <span className="muted save-state">{dirty ? "저장 안 됨" : ""}</span>
        <div className="form-actions">
          {frozen ? (
            <button
              className="ghost"
              onClick={async () => {
                if (!window.confirm("확정을 해제하면 문서를 다시 고칠 수 있습니다. 해제할까요?")) return;
                await api.unfreezeReport(report.id);
                onChanged();
              }}
            >
              확정 해제
            </button>
          ) : (
            <>
              <button className="ghost" disabled={busy || !dirty} onClick={() => void save()}>
                저장
              </button>
              <button
                disabled={busy}
                onClick={async () => {
                  if (!window.confirm("보고를 확정하면 이 문서는 읽기 전용이 되고, 미보고 분량이 초기화됩니다.")) return;
                  setBusy(true);
                  try {
                    if (dirty) await save();
                    await api.freezeReport(report.id);
                    onChanged();
                  } catch (err) {
                    setError((err as Error).message);
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                보고 확정
              </button>
            </>
          )}
        </div>
      </div>

      {previewing && <XlsxPreview attachment={previewing} onClose={() => setPreviewing(null)} />}
    </div>
  );
}
