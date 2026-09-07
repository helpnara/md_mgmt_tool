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
