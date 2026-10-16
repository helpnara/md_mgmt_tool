import { api } from "../api";
import type { Meta, Person } from "../types";
import { isDeparted } from "../inputRules";

/**
 * 저장 직전의 명부 (TODO 214 D6 · D7).
 *
 * 화면의 `meta` 는 켤 때 받은 것이라, 방금 [명부에 추가] 한 이름을 모른다 — 그대로 견주면 같은 이름을 또 묻는다.
 * 저장 직전에 명부를 새로 받아 견준다. 받지 못하면 들고 있던 `meta` 로.
 */
export async function freshRoster(meta: Pick<Meta, "people" | "people_left">): Promise<Pick<Meta, "people" | "people_left">> {
  try {
    const data = await api.people();
    const people: Person[] = Array.isArray(data?.people) ? data.people : [];
    return { people: people.map((person) => person.name), people_left: people.filter((person) => person.left_on) };
  } catch {
    return meta;
  }
}

/** 지금 떠난 사람의 이름 — 떠난 날이 오늘 이후면 아직 있는 사람이다 (D8) */
export function departedNames(meta: Pick<Meta, "people_left">): Set<string> {
  return new Set((meta.people_left ?? []).filter((person) => isDeparted(person)).map((person) => person.name));
}
