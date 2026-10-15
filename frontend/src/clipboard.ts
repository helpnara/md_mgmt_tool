/**
 * 클립보드에 글을 넣는다 (TODO 208).
 *
 * `navigator.clipboard` 는 **보안 컨텍스트**(https · localhost · 127.0.0.1)에만 있다. 읽기 전용 공유로 연
 * `http://PC이름:8000` 에서는 undefined 라, 표 복사 · [엑셀 셀로 복사] 가 팀원 PC 에서 전부 영어 TypeError 로 죽었다.
 * 여기서는 되는 길을 차례로 밟는다 — `navigator.clipboard` → 숨긴 textarea + `execCommand("copy")`.
 * 둘 다 안 되면 false 를 돌려 주고, 부르는 쪽은 한국어로 안내한다(`COPY_FAILED`). 예외를 밖으로 내지 않는다.
 */
export const COPY_FAILED = "복사하지 못했습니다 — 표를 드래그해 선택한 뒤 Ctrl+C 로 복사하세요";

/** 평문을 클립보드에 넣는다. 성공하면 true. */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* 아래 폴백으로 */
  }
  return copyWithTextarea(text);
}

/**
 * HTML 과 평문을 함께 넣는다 — 엑셀은 HTML 플레이버를 먼저 읽어 한 칸에 줄바꿈을 살린다.
 * `ClipboardItem` 이 없으면 평문만 넣는다(그래도 복사는 된다). 성공하면 true.
 */
export async function copyRich(html: string, plain: string): Promise<boolean> {
  try {
    if (typeof ClipboardItem !== "undefined" && navigator.clipboard?.write) {
      await navigator.clipboard.write([
        new ClipboardItem({
          "text/html": new Blob([html], { type: "text/html" }),
          "text/plain": new Blob([plain], { type: "text/plain" }),
        }),
      ]);
      return true;
    }
  } catch {
    /* 아래 폴백으로 */
  }
  return copyText(plain);
}

/** 비보안 컨텍스트의 길 — 보이지 않는 textarea 에 넣고 선택해 복사 명령을 내린다. */
function copyWithTextarea(text: string): boolean {
  if (typeof document === "undefined") return false;
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.top = "0";
  area.style.left = "0";
  area.style.width = "1px";
  area.style.height = "1px";
  area.style.opacity = "0";
  area.style.pointerEvents = "none";
  const active = document.activeElement as HTMLElement | null;
  document.body.appendChild(area);
  let ok = false;
  try {
    area.focus();
    area.select();
    area.setSelectionRange(0, text.length);
    ok = document.execCommand("copy");
  } catch {
    ok = false;
  } finally {
    document.body.removeChild(area);
    // 포커스를 원래 자리로 — 단추를 눌렀던 사람이 키보드로 이어 가게
    if (active && typeof active.focus === "function") active.focus();
  }
  return ok;
}
