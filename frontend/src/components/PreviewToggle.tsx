import { useState } from "react";

const KEY = "md-mgmt:preview";

/**
 * 편집기의 미리보기를 켜고 끈다.
 *
 * 2단 화면에서 편집 칸은 절반의 절반이 된다. 표를 그리거나 문장을 다듬을 때는
 * 미리보기를 접어 입력 칸을 두 배로 쓰는 편이 낫다. 선택은 사람마다 다르므로
 * 브라우저에 기억해 둔다.
 */
export function usePreview(): [boolean, () => void] {
  const [on, setOn] = useState(() => localStorage.getItem(KEY) !== "off");
  const toggle = () =>
    setOn((value) => {
      const next = !value;
      localStorage.setItem(KEY, next ? "on" : "off");
      return next;
    });
  return [on, toggle];
}

export default function PreviewToggle({ on, onToggle }: { on: boolean; onToggle: () => void }) {
  return (
    <div className="split-head">
      <button type="button" className="ghost small" onClick={onToggle}>
        {on ? "미리보기 접기" : "미리보기 펼치기"}
      </button>
    </div>
  );
}
