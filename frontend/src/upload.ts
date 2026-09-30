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

export interface UploadHandle {
  promise: Promise<Attachment>;
  abort: () => void;
}

/**
 * 용량 제한이 없으므로 진행률을 반드시 보여준다.
 * fetch는 업로드 진행률을 주지 않아 XHR을 쓴다.
 */
export function uploadAttachment(
  endpoint: string,
  file: File,
  onProgress: (loaded: number, total: number) => void,
): UploadHandle {
  const xhr = new XMLHttpRequest();
  const promise = new Promise<Attachment>((resolve, reject) => {
    const form = new FormData();
    form.append("file", file, file.name);

    xhr.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable) onProgress(event.loaded, event.total);
    });
    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText) as Attachment);
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
