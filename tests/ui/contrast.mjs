/**
 * 명암비 계산 (WCAG 2.1) — 브라우저 안에서 돌린다.
 *
 * 색만 바꾸는 결함은 백엔드 시험으로 절대 잡히지 않는다. 눈으로 봐야 알고,
 * 그래서 실제로 한 번 놓쳤다 (TODO 25 — 칩을 누르면 글자가 흰색으로 바뀌어 안 보였다).
 * 여기서 기계가 대신 본다.
 */

/**
 * 페이지에 주입해 쓰는 함수 문자열. 브라우저 문맥에서 실행된다.
 * addInitScript 는 이 코드를 함수로 감싸므로, 선언만 해서는 evaluate 에서 보이지 않는다.
 * window 에 직접 걸어야 한다.
 */
export const CONTRAST_HELPERS = `
function __srgb(value) {
  const v = value / 255;
  return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
}
function __parse(color) {
  const parts = (color || "").match(/[\\d.]+/g);
  if (!parts) return null;
  const [r, g, b, a] = parts.map(Number);
  return { r, g, b, a: a === undefined ? 1 : a };
}
function __luminance(c) {
  return 0.2126 * __srgb(c.r) + 0.7152 * __srgb(c.g) + 0.0722 * __srgb(c.b);
}
/** 투명한 배경은 실제로 보이는 색이 아니다. 불투명한 조상을 찾을 때까지 올라간다. */
function __effectiveBackground(el) {
  let node = el;
  while (node) {
    const c = __parse(getComputedStyle(node).backgroundColor);
    if (c && c.a > 0.99) return c;
    node = node.parentElement;
  }
  return { r: 255, g: 255, b: 255, a: 1 };
}
window.__contrast = function (el) {
  const fg = __parse(getComputedStyle(el).color);
  const bg = __effectiveBackground(el);
  if (!fg) return null;
  // 반투명 글자는 배경 위에 얹힌 결과 색으로 본다.
  const mixed = fg.a >= 0.99 ? fg : {
    r: fg.r * fg.a + bg.r * (1 - fg.a),
    g: fg.g * fg.a + bg.g * (1 - fg.a),
    b: fg.b * fg.a + bg.b * (1 - fg.a),
  };
  const [hi, lo] = [__luminance(mixed), __luminance(bg)].sort((a, b) => b - a);
  return Math.round(((hi + 0.05) / (lo + 0.05)) * 100) / 100;
};
`;

/** 보통 크기 글자의 최소 명암비 (WCAG AA). */
export const AA = 4.5;
/** 굵거나 큰 글자, 그리고 테두리·구분선 같은 비문자 요소 (WCAG AA). */
export const AA_LARGE = 3.0;
