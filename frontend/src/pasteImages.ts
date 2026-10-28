/**
 * 붙여넣기의 그림을 제자리에 (TODO 225).
 *
 * `htmlPaste` 가 그림 자리에 표시를 남기고 일(`ImageJob`)을 돌려주면, 편집기는 이것으로 하나씩 가져와 올리고 표시를 그림 링크로 바꾼다.
 * 못 가져오면 그 자리에 안내 줄. 클립보드에 그림 파일이 함께 왔으면(`spare`) **못 가져온 자리부터** 채운다.
 * 222 는 그림을 모두 본문 끝(커서 자리)에 붙였다 — 표 사이에 있던 그림이 맨 뒤로 갔다.
 */
import type { ImageJob } from "./htmlPaste";

export async function placeImages(
  jobs: ImageJob[],
  spare: File[],
  upload: (file: File) => Promise<string>,
  replace: (marker: string, text: string) => void,
): Promise<void> {
  const pool = [...spare];
  for (const job of jobs) {
    let file: File | null = null;
    try {
      file = await job.load();
    } catch {
      file = null;
    }
    if (!file && pool.length > 0) file = pool.shift() ?? null;
    if (!file) {
      replace(job.marker, job.fallback());
      continue;
    }
    try {
      replace(job.marker, await upload(file));
    } catch (err) {
      replace(job.marker, job.fallback(`그림을 올리지 못했습니다 — ${(err as Error).message}.`));
    }
  }
}
