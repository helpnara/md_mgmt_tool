import { useState } from "react";
import { api } from "../api";
import { splitNames } from "../inputRules";

/**
 * 명부에 없는 담당자 이름을 알려 준다.
 *
 * **막지 않는다.** 막으면 급할 때 못 쓴다. 묻기만 한다 —
 * 오타면 고칠 기회가 되고, 새 사람이면 그 자리에서 명부에 넣을 수 있다.
 * 명부가 아직 비어 있으면 아무 말도 하지 않는다 (아직 쓸 기준이 없다).
 * 저장할 때 한 번 더 묻는다(TODO 214 D6, `confirmPeople`) — 여기는 미리 보이는 안내다.
 */
interface Props {
  known: string[];
  value: string;
  onAdded: () => void;
  /** 이미 떠난 사람 — "명부에 없는 이름" 이 아니라 "떠난 사람" 으로 알린다 (TODO 214 D7) */
  departed?: string[];
}

export default function UnknownOwners({ known, value, onAdded, departed = [] }: Props) {
  const [added, setAdded] = useState<string[]>([]);
  const [busy, setBusy] = useState<string | null>(null);

  if (known.length === 0 && departed.length === 0) return null;

  // 나누는 규칙은 서버와 같게 — 쉼표 · 앞뒤 공백 · 겹친 것 (TODO 214 U8)
  const names = splitNames(value);
  const gone = names.filter((name) => departed.includes(name));
  const unknown =
    known.length === 0
      ? []
      : names.filter((name) => !known.includes(name) && !added.includes(name) && !departed.includes(name));

  if (unknown.length === 0 && gone.length === 0) return null;

  async function add(name: string) {
    setBusy(name);
    try {
      await api.addPerson(name);
      setAdded((prev) => [...prev, name]);
      onAdded();
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="tag-suggest">
      {gone.length > 0 && <span className="warn-text">떠난 사람: {gone.join(", ")}</span>}
      {unknown.length > 0 && <span className="warn-text">명부에 없는 이름</span>}
      {unknown.map((name) => (
        <button
          key={name}
          type="button"
          className="tag-pick add"
          disabled={busy !== null}
          title={`${name} 을(를) 담당자 명부에 넣습니다`}
          onClick={() => void add(name)}
        >
          {busy === name ? "넣는 중…" : `${name} + 추가`}
        </button>
      ))}
    </div>
  );
}
