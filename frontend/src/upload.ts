import { errorText, OFFLINE_MESSAGE } from "./api";
export interface Attachment {
  id: number;
  entry_id: number | null;
  report_id: number | null;
  preview_url: string | null;
  rel_path: string;
  orig_name: string;
  mime: string | null;
  size_bytes: number | null;
  is_image: boolean;
  url: string;
  thumb_url: string | null;
  markdown: string;
  orphan: boolean;
  deduplicated: boolean;
}

export interface UploadHandle<T = Attachment> {
  promise: Promise<T>;
  abort: () => void;
}

/**
 * 용량 제한이 없으므로 진행률을 반드시 보여준다.
 * fetch는 업로드 진행률을 주지 않아 XHR을 쓴다.
 */
export function uploadAttachment<T = Attachment>(
  endpoint: string,
  file: File,
  onProgress: (loaded: number, total: number) => void,
): UploadHandle<T> {
  const xhr = new XMLHttpRequest();
  const promise = new Promise<T>((resolve, reject) => {
    const form = new FormData();
    form.append("file", file, file.name);

    xhr.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable) onProgress(event.loaded, event.total);
    });
    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText) as T);
      } else {
        // 다른 요청과 같은 말로 (TODO 165) — 사유가 목록(422)이어도, 글이 아닌 500 이어도
        let body: unknown = null;
        try {
          body = JSON.parse(xhr.responseText);
        } catch {
          /* 응답이 JSON이 아니면 상태 번호로 말한다 */
        }
        reject(new Error(errorText(xhr.status, body)));
      }
    });
    xhr.addEventListener("error", () => reject(new Error(OFFLINE_MESSAGE)));
    xhr.addEventListener("abort", () => reject(new Error("업로드를 취소했습니다.")));

    xhr.open("POST", endpoint);
    xhr.send(form);
  });

  return { promise, abort: () => xhr.abort() };
}

/**
 * 파일을 **본문 그대로** 올린다(TODO 267) — 서버가 받는 대로 데이터 폴더 드라이브에 바로 쓴다(웹 틀의 임시 파일 · 복사를 거치지 않음).
 * 되살리기의 큰 zip 에 쓴다. 파일 이름은 `X-Filename` 머리에.
 */
export function uploadRaw<T>(endpoint: string, file: File, onProgress: (loaded: number, total: number) => void): UploadHandle<T> {
  const xhr = new XMLHttpRequest();
  const promise = new Promise<T>((resolve, reject) => {
    xhr.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable) onProgress(event.loaded, event.total);
    });
    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText) as T);
      } else {
        let body: unknown = null;
        try {
          body = JSON.parse(xhr.responseText);
        } catch {
          /* 응답이 JSON이 아니면 상태 번호로 말한다 */
        }
        reject(new Error(errorText(xhr.status, body)));
      }
    });
    xhr.addEventListener("error", () => reject(new Error(OFFLINE_MESSAGE)));
    xhr.addEventListener("abort", () => reject(new Error("업로드를 취소했습니다.")));
    xhr.open("POST", endpoint);
    xhr.setRequestHeader("Content-Type", file.type || "application/zip");
    xhr.setRequestHeader("X-Filename", encodeURIComponent(file.name));
    xhr.send(file);
  });
  return { promise, abort: () => xhr.abort() };
}

export function formatBytes(bytes: number | null | undefined): string {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** exponent;
  return `${value >= 10 || exponent === 0 ? Math.round(value) : value.toFixed(1)} ${units[exponent]}`;
}

export function formatRate(bytesPerSecond: number): string {
  return `${formatBytes(bytesPerSecond)}/s`;
}
