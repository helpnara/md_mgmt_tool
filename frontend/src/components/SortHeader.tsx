/**
 * 눌러서 정렬하는 열 머리글.
 *
 * 세 번 돌려 해제하는 방식(오름 → 내림 → 기본)은 쓰지 않는다.
 * 세 번째 상태를 사람들이 잘 못 찾기 때문이다. 여기서는 **두 방향만** 돌고,
 * 기본 순서로 돌아가는 길은 표 위의 [기본 순서로] 단추가 따로 맡는다.
 */
export interface SortState {
  key: string;
  order: "asc" | "desc";
}

interface Props {
  /** 서버가 아는 정렬 이름. 없으면 그냥 글자만 나온다. */
  sortKey?: string;
  current: SortState | null;
  onSort: (next: SortState) => void;
  children: React.ReactNode;
  /** 처음 눌렀을 때의 방향. 수·날짜는 큰 것/최근 것부터가 자연스럽다. */
  first?: "asc" | "desc";
}

export default function SortHeader({ sortKey, current, onSort, children, first = "asc" }: Props) {
  if (!sortKey) return <th>{children}</th>;

  const on = current?.key === sortKey;
  const order = on ? current.order : null;

  return (
    <th className={`sortable${on ? " sorted" : ""}`}>
      <button
        type="button"
        onClick={() => onSort({ key: sortKey, order: on && order === first ? (first === "asc" ? "desc" : "asc") : first })}
        title={on ? "방향 바꾸기" : "이 열로 정렬"}
      >
        {children}
        <span className="sort-arrow" aria-hidden="true">
          {order === "asc" ? "▲" : order === "desc" ? "▼" : "⇅"}
        </span>
      </button>
    </th>
  );
}
