import { normalizeTag, sameTagAs } from "../inputRules";

/**
 * 이미 쓰고 있는 태그를 눌러서 덧붙인다.
 *
 * 태그 칸은 쉼표로 여러 개를 적는 자리라 `<datalist>` 로는 두 번째 태그부터 도움이 안 된다.
 * 자유 입력을 그대로 두면 `공정` / `공정개선` / `공정 개선` 이 따로 쌓이고,
 * 시간이 지날수록 되돌리기 어려워진다.
 *
 * 대소문자 · 띄어쓰기 · 앞의 `#` 만 다른 태그는 서버가 처음 쓴 표기로 합친다 (TODO 214 D12) —
 * 저장 전에 "‘AI’ 로 저장됩니다" 라고 미리 보인다.
 */
interface Props {
  known: string[];
  value: string;
  onPick: (next: string) => void;
}

function parse(value: string): string[] {
  return value
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean);
}

const keyOf = (tag: string) => normalizeTag(tag).toLowerCase().replace(/\s/g, "");

export default function TagSuggestions({ known, value, onPick }: Props) {
  const chosen = parse(value);
  const chosenKeys = new Set(chosen.map(keyOf));
  // 적은 태그 중 이미 쓰는 표기와 모양만 다른 것 — 서버가 그 표기로 합친다
  const merges = chosen
    .map((tag) => ({ tag, as: sameTagAs(tag, known) ?? (normalizeTag(tag) !== tag ? normalizeTag(tag) : null) }))
    .filter((item): item is { tag: string; as: string } => Boolean(item.as) && item.as !== item.tag);
  // 이미 고른 것(모양만 다른 것 포함)은 빼고, 너무 길어지지 않게 앞에서부터 보여 준다.
  const rest = known.filter((tag) => !chosenKeys.has(keyOf(tag))).slice(0, 12);
  if (rest.length === 0 && merges.length === 0) return null;

  return (
    <>
      {merges.length > 0 && (
        <p className="hint tag-merge-hint">
          {merges.map((item) => `‘${item.tag}’ → ‘${item.as}’`).join(" · ")} 로 저장됩니다
        </p>
      )}
      {rest.length > 0 && (
        <div className="tag-suggest">
          <span className="muted">쓰던 태그</span>
          {rest.map((tag) => (
            <button key={tag} type="button" className="tag-pick" onClick={() => onPick([...chosen, tag].join(", "))}>
              {tag}
            </button>
          ))}
        </div>
      )}
    </>
  );
}
