import type React from "react";
import { isPlainEnter } from "../util";

/**
 * 설정 카드의 Enter 규칙 (TODO 214 U9) — 한 줄 칸에서 Enter = 그 카드의 [저장]. 여러 줄 칸 · 찾기 칸 · 목록 칸(data-enter="add")은 그대로.
 * 안쪽(이름 창 · 폴더 고르기)이 먼저 Enter 를 썼으면(`preventDefault`) 건드리지 않는다.
 */
export function enterToSave(save: () => void, enabled: boolean) {
  return (event: React.KeyboardEvent) => {
    if (!isPlainEnter(event)) return;
    if ((event.target as HTMLInputElement).type === "search") return;
    event.preventDefault();
    if (enabled) save();
  };
}
