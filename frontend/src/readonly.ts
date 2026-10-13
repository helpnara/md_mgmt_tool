/**
 * 읽기 전용 공유 (TODO 191).
 *
 * 바깥에서 온 브라우저에는 서버가 `meta.readonly` 를 준다. App 이 `<body class="readonly">` 를 걸면
 * styles.css 가 쓰기 단추(채운 단추 · .commit · .report · .danger · [data-write])를 숨기고, 몇몇 화면은 이 함수로 칸을 통째로 뺀다.
 * **숨기는 것은 편의다. 막는 것은 서버다** — 단추가 보여도 바깥에서 보낸 쓰기는 403 이다.
 */
export function isReadonly(): boolean {
  return document.body.classList.contains("readonly");
}
