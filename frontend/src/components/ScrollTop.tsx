import { useEffect, useState } from "react";

/** 이만큼 내려갔을 때부터 보인다. 한 화면 남짓. */
const SHOW_AFTER = 600;

/**
 * 맨 위로 가는 단추.
 *
 * 진행일지가 쌓인 과제는 상세 화면이 매우 길어져, 제목까지 되돌아가려면
 * 한참을 올려야 했다.
 *
 * 두 가지를 지킨다.
 * · **모든 화면에서 같은 자리.** `App.tsx` 에 한 번만 두어 목록·상세·설정이 전부 같이 갖는다.
 * · **한 화면 넘게 내렸을 때만 나타난다.** 늘 떠 있으면 내용을 가린다.
 *
 * 자리는 오른쪽 아래인데, 편집기의 [저장]·[보고 확정] 이 그 근처에 온다.
 * 그래서 본문에 여백이 있는 넓은 화면에서는 바깥쪽에 붙이고,
 * 여백이 없는 좁은 화면에서는 위로 띄워 단추를 가리지 않게 한다.
 */
export default function ScrollTop() {
  const [shown, setShown] = useState(false);

  useEffect(() => {
    const onScroll = () => setShown(window.scrollY > SHOW_AFTER);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  if (!shown) return null;

  return (
    <button
      className="scroll-top"
      title="맨 위로"
      aria-label="맨 위로"
      onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
    >
      ↑
    </button>
  );
}
