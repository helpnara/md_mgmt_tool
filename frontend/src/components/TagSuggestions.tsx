/**
 * 이미 쓰고 있는 태그를 눌러서 덧붙인다.
 *
 * 태그 칸은 쉼표로 여러 개를 적는 자리라 `<datalist>` 로는 두 번째 태그부터 도움이 안 된다.
 * 자유 입력을 그대로 두면 `공정` / `공정개선` / `공정 개선` 이 따로 쌓이고,
 * 시간이 지날수록 되돌리기 어려워진다.
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

export default function TagSuggestions({ known, value, onPick }: Props) {
  const chosen = parse(value);
  // 이미 고른 것은 빼고, 너무 길어지지 않게 앞에서부터 보여 준다.
  const rest = known.filter((tag) => !chosen.includes(tag)).slice(0, 12);
  if (rest.length === 0) return null;

  return (
    <div className="tag-suggest">
      <span className="muted">쓰던 태그</span>
      {rest.map((tag) => (
        <button
          key={tag}
          type="button"
          className="tag-pick"
          onClick={() => onPick([...chosen, tag].join(", "))}
        >
          {tag}
        </button>
      ))}
    </div>
  );
}
