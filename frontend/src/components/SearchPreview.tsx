import { useEffect, useState } from "react";
import { api } from "../api";
import { projectLink, screenLink } from "../nav";
import type { SearchResults } from "../types";

type Item = { key: string; href: string; kind: string; title: string; sub: string };

/** 미리보기에 보일 줄 — 과제 먼저, 갈래마다 몇 건씩, 모두 6건까지 */
function itemsOf(results: SearchResults): Item[] {
  const out: Item[] = [
    ...results.projects.slice(0, 3).map((p) => ({ key: `p${p.id}`, href: projectLink(p.id), kind: "과제", title: p.title, sub: p.id })),
    ...(results.intakes ?? []).slice(0, 1).map((i) => ({ key: `i${i.id}`, href: screenLink(`intakes/${i.id}`), kind: "접수", title: i.title, sub: i.id })),
    ...results.entries.slice(0, 2).map((e) => ({ key: `e${e.id}`, href: projectLink(e.project_id, { entry: e.id }), kind: "일지", title: e.title, sub: `${e.date} · ${e.project_title}` })),
    ...results.reports.slice(0, 1).map((r) => ({ key: `r${r.id}`, href: projectLink(r.project_id, { report: r.id }), kind: "보고", title: r.audience || r.title || "보고", sub: `${r.report_date} · ${r.project_title}` })),
    ...(results.contributions ?? []).slice(0, 1).map((c) => ({ key: `c${c.project_id}${c.name}`, href: projectLink(c.project_id), kind: "역할", title: c.name, sub: c.project_title })),
    ...(results.activities ?? []).slice(0, 1).map((a) => ({ key: `a${a.id}`, href: screenLink(`skills?tab=records&person=${encodeURIComponent(a.person)}`), kind: "역량", title: a.title, sub: `${a.date} · ${a.person}` })),
  ];
  return out.slice(0, 6);
}

/**
 * 머리줄 검색 칸의 입력 중 미리보기 (TODO 254 2차 D) — 두 글자부터 0.25초 쉬면 위 몇 건을 펼친다.
 * 누르면 바로 그곳으로, [엔터]는 지금처럼 전체 결과. Esc · 칸 밖을 누르면 접는다. 검색 결과 화면에서는 띄우지 않는다.
 */
export default function SearchPreview({ term, active, onClose }: { term: string; active: boolean; onClose: () => void }) {
  const [items, setItems] = useState<Item[] | null>(null);
  const [total, setTotal] = useState(0);

  useEffect(() => {
    const query = term.trim();
    if (!active || query.length < 2) {
      setItems(null);
      return;
    }
    let stale = false;
    const timer = window.setTimeout(() => {
      api.search(query, "relevance", 3)
        .then((results) => {
          if (stale) return;
          setItems(itemsOf(results));
          setTotal(results.total);
        })
        .catch(() => { if (!stale) setItems(null); });
    }, 250);
    return () => { stale = true; window.clearTimeout(timer); };
  }, [term, active]);

  if (!active || !items) return null;
  return (
    <div className="search-preview" role="listbox" aria-label="검색 미리보기" data-testid="search-preview"
      onMouseDown={(event) => event.preventDefault() /* 칸의 포커스를 지킨다 — 누르면 그곳으로 */}>
      {items.length === 0 ? (
        <p className="muted">일치하는 것이 없습니다.</p>
      ) : (
        items.map((item) => (
          <a key={item.key} href={item.href} className="search-preview-item" role="option" aria-selected="false" onClick={onClose}>
            <span className="search-preview-kind">{item.kind}</span>
            <span className="search-preview-title">{item.title}</span>
            <span className="muted search-preview-sub">{item.sub}</span>
          </a>
        ))
      )}
      <a className="search-preview-all" href={`#/search?q=${encodeURIComponent(term.trim())}`} onClick={onClose}>
        전체 결과 보기{total ? ` (${total}건${total > items.length ? " 이상" : ""})` : ""} — 엔터
      </a>
    </div>
  );
}
