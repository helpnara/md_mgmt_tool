/**
 * 이름 여럿을 나누는 규칙. **서버(`services/activities.py`)와 같은 규칙이어야 한다.**
 *
 * 나누는 일 자체는 서버가 한다 — 화면만 고치면 API 를 직접 부르는 길로 같은 사고가 다시 난다.
 * 화면이 이것을 쓰는 이유는 하나다: **저장하기 전에 무엇이 만들어질지 보여 주기 위해서.**
 */
export function splitPeople(value: string): string[] {
  const names: string[] = [];
  for (const chunk of (value ?? "").split(/[,;\n]+/)) {
    const name = chunk.trim();
    if (name && !names.includes(name)) names.push(name);
  }
  return names;
}

/**
 * 떠난 사람이면 딱지 문구(전배·퇴사)를, 아니면 빈 글자를 돌려준다 (TODO 122).
 *
 * 이름을 지우지 않는 것이 이 기능의 요점이라 **화면 어디서나 같은 판단**을 써야 한다.
 * 사유를 안 적었으면 `떠남` 으로 적는다 — 날짜만 넣고 사유를 비워 둘 수 있기 때문이다.
 */
export function leftLabel(meta: { people_left?: { name: string; left_reason?: string }[] }, name: string): string {
  const found = meta.people_left?.find((person) => person.name === name);
  return found ? found.left_reason || "떠남" : "";
}

/** 명부의 팀장인가 (TODO 235) */
export function isLeader(meta: { leader?: string }, name: string): boolean {
  return Boolean(meta.leader) && meta.leader === name.trim();
}

/**
 * 323 — 화면 어디서나 같은 떠난 사람 판단. App 이 meta 를 받을 때마다 채운다(`meta.people_left` 는
 * 서버가 떠난 날이 오늘이거나 지난 사람만 준다 — 앞날은 떠날 예정이라 아직 지금 사람).
 * meta 를 props 로 받지 않는 카드 · 목록도 이것으로 띠지를 붙이거나 뺀다.
 */
let leftNow: { name: string; left_reason?: string }[] = [];
export function setLeftPeople(list: { name: string; left_reason?: string }[] | undefined): void {
  leftNow = list ?? [];
}
/** 떠난 사람이면 전배 · 퇴사(사유가 없으면 떠남), 아니면 "" */
export function leftOf(name: string | null | undefined): string {
  const key = (name ?? "").trim();
  const found = key ? leftNow.find((person) => person.name === key) : undefined;
  return found ? found.left_reason || "떠남" : "";
}
export function isGone(name: string | null | undefined): boolean {
  return leftOf(name) !== "";
}
/** 고르기 칸의 이름 — 떠난 사람은 "이름 (퇴사)" 로 적고 맨 뒤로 */
export function withLeftMark(names: string[]): { name: string; label: string }[] {
  return [...names]
    .sort((a, b) => Number(isGone(a)) - Number(isGone(b)))
    .map((name) => ({ name, label: isGone(name) ? `${name} (${leftOf(name)})` : name }));
}
