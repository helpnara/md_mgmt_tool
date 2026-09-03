import { useEffect, useRef } from "react";

/**
 * 화면 이동 — 어디서 왔는지와 무엇을 걸러 놨는지를 **주소가 기억한다.**
 *
 * 과제 상세로 들어오는 길은 다섯이다 (메인·보고 대상·보고 이력·검색·과제 목록).
 * 그런데 나가는 길은 "과제 목록" 하나뿐이라, 보고 이력에서 과제를 열어 본 뒤에는
 * 메뉴를 다시 눌러 돌아가야 했다.
 *
 * 클릭 이력을 따로 들고 있는 방법도 있지만 쓰지 않는다. 기억과 주소가 따로 놀기
 * 시작하면 새로고침·주소 복사·탭 두 개에서 어긋나고, 그때 나는 오류는 재현이 안 된다.
 * 대신 **온 곳을 주소에 실어 보낸다.** 기억할 것이 없으면 어긋날 것도 없다.
 *
 * 거른 조건도 같은 이유로 주소에 둔다. 되돌아왔을 때 조건이 그대로 살아 있고,
 * 덤으로 자주 보는 조건을 즐겨찾기해 둘 수 있다.
 */

/** 되돌아갈 곳을 담는 주소 칸. */
export const BACK_PARAM = "back";

const LABELS: Record<string, string> = {
  "": "과제 목록",
  reports: "보고 대상",
  history: "보고 이력",
  search: "검색 결과",
};

/** 지금 주소에서 `#/` 를 뗀 부분. 되돌아갈 곳으로 그대로 쓴다. */
export function currentLocation(): string {
  return window.location.hash.replace(/^#\/?/, "");
}

/** 주소의 물음표 뒷부분. */
export function queryOf(location: string): URLSearchParams {
  return new URLSearchParams(location.split("?")[1] ?? "");
}

/**
 * 과제 상세로 가는 주소. 지금 화면을 `back` 에 실어 보낸다.
 *
 * 이미 상세 화면에 있을 때(보고 문서 열기 등)는 **그 화면의 back 을 그대로 물려준다.**
 * 그러지 않으면 상세 → 상세로 이어질 때 되돌아갈 곳이 상세 자신이 되어 제자리를 맴돈다.
 */
export function projectLink(projectId: string, extra?: Record<string, string | number | undefined>): string {
  const here = currentLocation();
  const back = here.split("?")[0].startsWith("projects/")
    ? queryOf(here).get(BACK_PARAM) ?? ""
    : here;

  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(extra ?? {})) {
    if (value !== undefined && value !== "") params.set(key, String(value));
  }
  if (back) params.set(BACK_PARAM, back);
  const query = params.toString();
  return `#/projects/${projectId}${query ? `?${query}` : ""}`;
}

/** 뒤로 가기가 가리킬 곳과 거기에 쓸 문구. */
export function backTarget(back: string | null | undefined): { href: string; label: string } {
  if (!back) return { href: "#/", label: "과제 목록" };
  const path = back.split("?")[0].replace(/\/$/, "");
  const label = LABELS[path];
  // 아는 화면이 아니면(주소를 손으로 고쳤다든가) 안전하게 과제 목록으로 보낸다.
  if (label === undefined) return { href: "#/", label: "과제 목록" };
  return { href: `#/${back}`, label };
}

function buildQuery(values: Record<string, string>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value) params.set(key, value);
  }
  return params.toString();
}

/**
 * 거른 조건을 주소에 반영한다.
 *
 * `replaceState` 를 쓰는 이유: 조건을 하나 고를 때마다 방문 기록이 쌓이면
 * 브라우저 뒤로가기를 열 번 눌러야 이전 화면으로 나가게 된다. 조건 바꾸기는
 * "이동"이 아니라 "지금 화면을 다듬는 일"이므로 기록을 남기지 않는다.
 */
export function syncQuery(screen: string, values: Record<string, string>): void {
  const query = buildQuery(values);
  const next = `#/${screen}${query ? `?${query}` : ""}`;
  if (window.location.hash !== next) {
    window.history.replaceState(null, "", next);
  }
}

/**
 * 화면의 조건과 주소를 양쪽으로 맞춘다.
 *
 * 나가는 쪽: 조건이 바뀌면 주소에 적는다.
 * 들어오는 쪽: **우리가 적지 않은 주소 변화**(상단 메뉴를 눌렀다든가)면 조건을 그리로 맞춘다.
 *   이게 없으면 `#/?status=done` 에서 [과제] 메뉴를 눌렀을 때 주소는 `#/` 인데
 *   목록은 여전히 걸러진 채로 남아, 주소가 화면을 속이게 된다.
 */
export function useAddressBar(
  screen: string,
  values: Record<string, string>,
  onAddressChanged: (params: URLSearchParams) => void,
): void {
  const written = useRef<string | null>(null);
  const handler = useRef(onAddressChanged);
  handler.current = onAddressChanged;
  const signature = JSON.stringify(values);

  useEffect(() => {
    written.current = buildQuery(values);
    syncQuery(screen, values);
    // values 는 매번 새 객체라 내용(signature)으로 비교한다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [screen, signature]);

  // 들어오는 쪽은 **주소를 직접 읽는다.**
  //
  // 화면 위쪽에서 넘겨주는 값을 믿으면 안 된다. 조건을 바꿀 때 쓰는 replaceState 는
  // hashchange 를 일으키지 않아, 위쪽이 기억하는 주소가 실제 주소보다 뒤처져 있다.
  // 그 상태로 비교하면 "메뉴를 눌러 조건 없는 주소로 왔다"를 알아채지 못한다.
  useEffect(() => {
    const onHashChange = () => {
      const here = currentLocation();
      // 다른 화면으로 떠나는 중이면 이 화면의 조건을 건드릴 이유가 없다.
      if (here.split("?")[0].replace(/\/$/, "") !== screen) return;
      const params = queryOf(here);
      if (written.current !== null && buildQuery(Object.fromEntries(params)) !== written.current) {
        handler.current(params);
      }
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, [screen]);
}
