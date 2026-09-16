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
