import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "../api";
import { notifyError } from "../notify";
import type { YearCard, YearCardLines, YearCardListing, YearCardProject } from "../types";
import { useEditedUnsaved } from "../util";

/**
 * 연말 회고 카드 (TODO 285) — 팀원역량 → [연말 카드] 탭(팀장 · 관리자만).
 *
 * 사람마다 엽서 한 장(100 × 148mm)에 그 해의 숫자 · 한 일(과제 최대 3) · 새로 쓴 보유 기술 · **팀장의 감사 편지**.
 * 왼쪽 사람 목록(준비 상태) · 가운데 고치기 · 오른쪽 **실제 크기 미리보기**(넘치면 알림).
 * [인쇄 · PDF 로 저장] — A4 한 장에 네 장(2 × 2)과 자를 선. 브라우저 인쇄 창에서 "PDF 로 저장" 또는 사내 프린터로(배율 100% · 여백 없음).
 *
 * 286 — 과제마다 수행 2줄 · 결과 2줄(카드에서만 다듬기 — 원본 과제 · 경험은 그대로), 역량 · 보유 기술(도구). 287 — 개수 제한 없음 · 288 — 떠난 사람은 접고 TBD 같은 자리 이름은 뺀다.
 */
type Draft = { message: string; headline: string; projects: string[]; lines: YearCardLines; skills: string[]; tools: string[]; signed_on: string };

const LINES = 2;
const sourceLines = (c: YearCardProject) => ({ did: c.did_lines.slice(0, LINES), result: c.result_lines.slice(0, LINES) });

function draftOf(card: YearCard): Draft {
  const lines: YearCardLines = {};
  for (const p of card.picked) lines[p.id] = { did: p.did_lines_card ?? sourceLines(p).did, result: p.result_lines_card ?? sourceLines(p).result,
    ...(p.title_card && p.title_card !== p.title ? { title: [p.title_card] } : {}) };
  return { message: card.message, headline: card.headline, projects: card.chosen, lines, skills: card.skills, tools: card.tools, signed_on: card.signed_on ?? "" };
}
export default function YearCards() {
  const thisYear = String(new Date().getFullYear());
  const [year, setYear] = useState(thisYear);
  const [listing, setListing] = useState<YearCardListing | null>(null);
  const [name, setName] = useState("");
  const [card, setCard] = useState<YearCard | null>(null);
  const [draft, setDraft] = useState<Draft>({ message: "", headline: "", projects: [], lines: {}, skills: [], tools: [], signed_on: "" });
  const [saved, setSaved] = useState(draft);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [printing, setPrinting] = useState<YearCard[] | null>(null);
  const [overflow, setOverflow] = useState(false);

  const loadList = async (keep = name) => {
    try {
      const next = await api.yearCards(year);
      setListing(next);
      // 303 — 팀장은 카드 대상이 아니다(목록에 흐리게만). 처음엔 첫 팀원
      const first = next.people.find((p) => !p.leader && !p.left)?.name ?? next.people.find((p) => !p.left && !p.leader)?.name ?? "";
      setName(keep && next.people.some((p) => p.name === keep && !p.leader) ? keep : first);
    } catch (error) {
      notifyError((error as Error).message);
    }
  };
  useEffect(() => { void loadList(""); }, [year]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!name) { setCard(null); return; }
    api.yearCard(name, year).then((next) => {
      setCard(next);
      const d = draftOf(next);
      setDraft(d);
      setSaved(d);
    }).catch((error: Error) => notifyError(error.message));
  }, [name, year]);
  const dirty = JSON.stringify(draft) !== JSON.stringify(saved);
  useEditedUnsaved("yearcards", draft, saved, busy);

  // 311 — 그 해 모든 카드의 날짜를 같게. 지금 카드에 고친 것이 있으면 먼저 저장한다
  async function signAll() {
    if (!card) return;
    const value = draft.signed_on.trim();
    if (!window.confirm(`${year}년 카드 모두의 날짜를 "${value || `${year}. 12.`}" (으)로 맞춥니다. 카드마다 따로 적은 날짜는 지워집니다(그 뒤 카드마다 다시 고칠 수 있습니다).`)) return;
    setBusy(true);
    try {
      if (dirty) {
        const lines: YearCardLines = {};
        for (const id of draft.projects) if (draft.lines[id]) lines[id] = draft.lines[id];
        await api.saveYearCard(card.name, year, { ...draft, lines, signed_on: "" });
      }
      await api.yearCardsSignedAll(year, value);
      const next = await api.yearCard(card.name, year);
      setCard(next);
      const d = draftOf(next);
      setDraft(d);
      setSaved(d);
      setNotice(`${year}년 카드 모두의 날짜를 "${next.signed_default}" (으)로 맞췄습니다.`);
      window.setTimeout(() => setNotice(""), 3500);
    } catch (error) {
      notifyError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    if (!card) return;
    setBusy(true);
    try {
      const lines: YearCardLines = {};
      for (const id of draft.projects) if (draft.lines[id]) lines[id] = draft.lines[id];
      const next = await api.saveYearCard(card.name, year, { ...draft, lines });
      setCard(next);
      const d = draftOf(next);
      setDraft(d);
      setSaved(d);
      setNotice("저장했습니다.");
      window.setTimeout(() => setNotice(""), 2500);
      await loadList(card.name);
    } catch (error) {
      notifyError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function print(names: string[]) {
    if (dirty && !window.confirm("저장하지 않은 고친 것이 있습니다 — 저장한 내용으로 인쇄합니다. 계속할까요?")) return;
    try {
      const { cards } = await api.yearCardsMany(year, names);
      setPrinting(cards);
    } catch (error) {
      notifyError((error as Error).message);
    }
  }
  useEffect(() => {
    if (!printing) return;
    document.body.classList.add("yc-printing");
    const done = () => { document.body.classList.remove("yc-printing"); setPrinting(null); };
    window.addEventListener("afterprint", done, { once: true });
    const timer = window.setTimeout(() => window.print(), 300);
    return () => { window.clearTimeout(timer); window.removeEventListener("afterprint", done); document.body.classList.remove("yc-printing"); };
  }, [printing]);

  const toggle = (id: string) => setDraft((d) => {
    const has = d.projects.includes(id);
    const source = card?.candidates.find((c) => c.id === id);
    const lines = { ...d.lines };
    if (!has && source && !lines[id]) lines[id] = sourceLines(source);
    return { ...d, lines, projects: has ? d.projects.filter((p) => p !== id) : [...d.projects, id] };
  });
  const setLine = (id: string, key: "did" | "result", i: number, value: string) => setDraft((d) => {
    const source = card?.candidates.find((c) => c.id === id);
    const now = d.lines[id] ?? (source ? sourceLines(source) : { did: [], result: [] });
    const list = [...(now[key] ?? [])];
    while (list.length <= i) list.push("");
    list[i] = value;
    return { ...d, lines: { ...d.lines, [id]: { ...now, [key]: list } } };
  });
  // 311 — 카드에서만 과제명 줄이기(비우면 원래 과제명)
  const setTitle = (id: string, value: string) => setDraft((d) => {
    const source = card?.candidates.find((c) => c.id === id);
    const now = d.lines[id] ?? (source ? sourceLines(source) : { did: [], result: [] });
    const next = { ...now };
    if (value) next.title = [value]; else delete next.title;
    return { ...d, lines: { ...d.lines, [id]: next } };
  });
  const cardTitle = (c: YearCardProject) => draft.lines[c.id]?.title?.[0]?.trim() || c.title;
  // 287 — 과제 · 역량 · 보유 기술 개수 제한 없음(넘치면 미리보기가 알린다). 칩 후보는 처음 12개, 나머지는 [더 보기]
  const [moreChips, setMoreChips] = useState<Record<string, boolean>>({});
  // 288 — 떠난 사람(전배 · 퇴사)은 접어 둔다
  const [showLeft, setShowLeft] = useState(false);
  const toggleChip = (key: "skills" | "tools", value: string) => setDraft((d) => {
    const has = d[key].includes(value);
    return { ...d, [key]: has ? d[key].filter((v) => v !== value) : [...d[key], value] };
  });
  const cardLines = (c: YearCardProject) => {
    const own = draft.lines[c.id];
    const clean = (list?: string[]) => (list ?? []).map((v) => v.trim()).filter(Boolean);
    return own ? { did: clean(own.did), result: clean(own.result) } : sourceLines(c);
  };
  const preview: YearCard | null = card ? {
    ...card, message: draft.message, headline: draft.headline, skills: draft.skills, tools: draft.tools, signed_on: draft.signed_on,
    picked: draft.projects.map((id) => card.candidates.find((c) => c.id === id)).filter(Boolean).map((c) => {
      const lines = cardLines(c!);
      return { ...c!, did_lines_card: lines.did, result_lines_card: lines.result, title_card: cardTitle(c!) };
    }),
  } : null;
  // 팀장 본인 카드는 [모두 인쇄] · 준비 수에서 빼고, 목록에서도 고를 수 없다(303)
  const members = listing?.people.filter((p) => !p.leader && !p.left) ?? [];
  const leftPeople = listing?.people.filter((p) => p.left) ?? [];
  const shownPeople = listing?.people.filter((p) => !p.left || showLeft || p.name === name) ?? [];
  const ready = members.filter((p) => p.missing.length === 0).length;
  const years = [String(Number(thisYear) - 1), thisYear];

  return (
    <div className="yearcards" data-testid="yearcards">
      <div className="card yc-head">
        <div className="card-head">
          <h2>
            <select aria-label="해" value={year} onChange={(e) => setYear(e.target.value)} className="year-pick">
              {years.map((y) => <option key={y} value={y}>{y}년</option>)}
            </select>
            {" "}연말 회고 카드
          </h2>
          <div className="person-tools">
            <span className="muted">준비 끝 <b>{ready}</b> / {members.length}명</span>
            <button className="ghost" disabled={!members.length} onClick={() => void print(members.map((p) => p.name))}>모두 인쇄 · PDF</button>
          </div>
        </div>
        <p className="hint">
          사람마다 <b>엽서 한 장</b>(100 × 148mm)입니다 — 그 해의 숫자 · 대표 과제(과제마다 수행 2줄 · 결과 2줄) · 역량 · 보유 기술 · <b>감사 편지</b> — 개수는 미리보기를 보며 정하세요.
          인쇄는 <b>A4 한 장에 네 장</b>이 자를 선과 함께 나옵니다. 인쇄 창에서 <b>배율 100%(실제 크기) · 여백 없음</b>으로 출력하거나 "PDF 로 저장" 하세요. 팀장 표시가 된 사람은 카드 대상이 아니라 고를 수 없습니다.
          이 화면과 편지는 팀장 · 관리자만 봅니다(팀원 화면 · 업무 이력 파일에 나오지 않습니다). 면담 기록 · 효과 금액 · 다른 사람과의 비교는 넣지 않습니다.
        </p>
      </div>
      <div className="yc-cols">
        <ul className="yc-people card" aria-label="사람">
          {shownPeople.map((p) => (
            <li key={p.name}>
              <button type="button" className={p.name === name ? "yc-person on" : "yc-person"} onClick={() => setName(p.name)}
                disabled={p.leader} title={p.leader ? "팀장은 연말카드 대상이 아닙니다" : undefined}>
                <b>{p.name}</b>{p.leader && <span className="tag leader-tag">팀장</span>}
                {p.left && <span className="tag">{p.left_reason || "떠남"} {p.left_on}</span>}
                {p.leader
                  ? <span className="muted yc-state">카드 대상 아님</span>
                  : <span className={p.missing.length ? "muted yc-state" : "yc-state ok"}>{p.missing.length ? `남음: ${p.missing.join(" · ")}` : "준비 끝 ✓"}</span>}
              </button>
            </li>
          ))}
          {leftPeople.length > 0 && (
            <li className="yc-left-toggle">
              <button type="button" className="link-button" onClick={() => setShowLeft(!showLeft)} data-testid="yc-left-toggle">
                {showLeft ? `떠난 사람 ${leftPeople.length}명 접기` : `떠난 사람 ${leftPeople.length}명 숨김 · 보기`}
              </button>
              <span className="muted"> — [모두 인쇄]에는 들어가지 않습니다</span>
            </li>
          )}
        </ul>
        {card && preview && (
          <div className="card yc-edit" data-testid="yc-edit">
            <h3>{card.name} 님의 카드</h3>
            <label>한 줄 제목 <span className="muted">(선택 — 비우면 "{year}년, 고마웠어요")</span>
              <input value={draft.headline} maxLength={40} placeholder={`${year}년, 고마웠어요`} onChange={(e) => setDraft({ ...draft, headline: e.target.value })} />
            </label>
            {/* 311 — 서명 줄 날짜(카드마다). 비우면 그 해 기본 날짜 */}
            <div className="yc-date-row">
              <label>날짜 <span className="muted">(선택 — 비우면 "{card.signed_default ?? `${year}. 12.`}")</span>
                <input value={draft.signed_on} maxLength={20} placeholder={card.signed_default ?? `${year}. 12.`} aria-label="카드 날짜"
                  onChange={(e) => setDraft({ ...draft, signed_on: e.target.value })} />
              </label>
              <button type="button" className="ghost" disabled={busy} onClick={() => void signAll()} data-testid="yc-sign-all">모든 카드에 같은 날짜</button>
            </div>
            <div className="yc-pick">
              <span className="exp-label">넣을 과제 <span className="muted">— {draft.projects.length}개 고름, 몇 개든 됩니다(넘치면 미리보기 아래에 알림). 올해 마친 과제 · 인정 한 줄이 있는 과제가 위</span></span>
              {card.candidates.length === 0 && <p className="muted">{year}년에 맡은 과제가 없습니다.</p>}
              {card.candidates.map((c) => (
                <label key={c.id} className="check-label yc-candidate">
                  <input type="checkbox" checked={draft.projects.includes(c.id)} onChange={() => toggle(c.id)} aria-label={`${c.title} 넣기`} />
                  <span>
                    <b>{c.title}</b> <span className="muted">{c.id}{c.done_this_year ? " · 마침" : ""}{c.role ? ` · ${c.role}` : ""}</span>
                    <br /><span className="muted">{c.did_lines.length ? `수행 ${c.did_lines.length}줄` : "수행 없음"} · {c.result ? `결과: ${c.result}` : "결과 칸이 비었습니다 — 과제의 담당과 역할에서 채우면 카드에 나옵니다"}</span>
                    {c.praise && <><br /><span className="muted">인정 한 줄: “{c.praise}”</span></>}
                  </span>
                </label>
              ))}
            </div>
            {draft.projects.length > 0 && (
              <div className="yc-lines" data-testid="yc-lines">
                <span className="exp-label">카드에 나갈 줄 <span className="muted">— 과제마다 과제명(비우면 원래 이름) · 수행 2줄 · 결과 2줄. 여기서 고쳐도 원본 과제 · 경험은 그대로입니다(칸을 누르면 원본 줄을 골라 넣을 수 있습니다)</span></span>
                {draft.projects.map((id) => {
                  const c = card.candidates.find((x) => x.id === id);
                  if (!c) return null;
                  const now = draft.lines[id] ?? sourceLines(c);
                  const same = JSON.stringify(cardLines(c)) === JSON.stringify(sourceLines(c)) && cardTitle(c) === c.title;
                  return (
                    <fieldset key={id} className="yc-line-block" data-project={id}>
                      <legend><b>{c.title}</b>{same ? <span className="muted"> · 원본 그대로</span> : <span className="tag">다듬음</span>}</legend>
                      <div className="yc-line-row">
                        <span className="muted yc-line-label">과제명</span>
                        <div className="yc-line-inputs">
                          <input aria-label={`${c.title} 카드 과제명`} value={draft.lines[id]?.title?.[0] ?? ""} maxLength={40} placeholder={c.title}
                            onChange={(e) => setTitle(id, e.target.value)} />
                        </div>
                      </div>
                      {(["did", "result"] as const).map((key) => (
                        <div key={key} className="yc-line-row">
                          <span className="muted yc-line-label">{key === "did" ? "수행" : "결과"}</span>
                          <div className="yc-line-inputs">
                            {[0, 1].map((i) => (
                              <input key={i} aria-label={`${c.title} ${key === "did" ? "수행" : "결과"} ${i + 1}`} value={now[key]?.[i] ?? ""}
                                maxLength={listing?.line_max ?? 80} list={`yc-src-${id}-${key}`}
                                placeholder={(key === "did" ? c.did_lines : c.result_lines).length ? "" : key === "did" ? "내가 한 일이 비었습니다" : "결과가 비었습니다"}
                                onChange={(e) => setLine(id, key, i, e.target.value)} />
                            ))}
                          </div>
                          <datalist id={`yc-src-${id}-${key}`}>
                            {(key === "did" ? c.did_lines : c.result_lines).map((line) => <option key={line} value={line} />)}
                          </datalist>
                        </div>
                      ))}
                      {!same && (
                        <button type="button" className="ghost small" onClick={() => setDraft((d) => ({ ...d, lines: { ...d.lines, [id]: sourceLines(c) } }))}>원본으로</button>
                      )}
                    </fieldset>
                  );
                })}
              </div>
            )}
            {(["skills", "tools"] as const).map((key) => {
              const options = key === "skills" ? card.skill_options : card.tool_options;
              const all = [...new Set([...draft[key], ...options])];
              const shown = moreChips[key] ? all : all.slice(0, 12);
              return (
                <div key={key} className="yc-chips" data-testid={`yc-${key}`}>
                  <span className="exp-label">{key === "skills" ? "역량" : "보유 기술(도구)"} <span className="muted">— {draft[key].length}개 고름, {key === "skills" ? "그 해 경험의 역량 태그" : "과제 담당과 역할 · 경험의 도구"} 자주 나온 순{key === "tools" ? " · ● 그 해 처음 쓴 것" : ""}</span></span>
                  {shown.length === 0 && <span className="muted">{key === "skills" ? "그 해 경험에 역량 태그가 없습니다" : "그 해 과제 · 경험에 보유 기술이 없습니다"}</span>}
                  <div className="dict-axes">
                    {shown.map((value) => (
                      <button key={value} type="button" className={draft[key].includes(value) ? "chip on" : "chip"} aria-pressed={draft[key].includes(value)}
                        onClick={() => toggleChip(key, value)}>
                        {value}{key === "tools" && card.new_skills.includes(value) ? " ●" : ""}
                      </button>
                    ))}
                    {all.length > 12 && (
                      <button type="button" className="link-button" onClick={() => setMoreChips({ ...moreChips, [key]: !moreChips[key] })}>
                        {moreChips[key] ? "접기" : `더 보기 (${all.length - 12})`}
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
            <label>감사 편지 <span className="muted">— {draft.message.length} / {listing?.message_max ?? 400}자</span>
              <textarea className="yc-message" rows={6} maxLength={listing?.message_max ?? 400} value={draft.message}
                placeholder="한 해 동안 고마웠던 일을 적어 주세요." onChange={(e) => setDraft({ ...draft, message: e.target.value })} />
            </label>
            {overflow && <p className="form-warn" data-testid="yc-overflow">카드에 다 들어가지 않습니다 — 편지를 줄이거나 넣을 과제를 하나 빼 주세요.</p>}
            {notice && <p className="hint notice">{notice}</p>}
            <div className="form-actions">
              <button className="ghost" onClick={() => void print([card.name])}>이 카드만 인쇄 · PDF</button>
              <button disabled={busy || !dirty} onClick={() => void save()}>{busy ? "저장 중…" : "저장"}</button>
            </div>
          </div>
        )}
        {preview && (
          <div className="yc-preview" aria-label="미리보기">
            <p className="muted">미리보기 — 실제 크기(100 × 148mm)</p>
            <PostCard card={preview} onOverflow={setOverflow} />
          </div>
        )}
      </div>
      {printing && createPortal(
        <div className="yc-print-root" aria-hidden>
          {chunk(printing, 4).map((sheet, i) => (
            <div className="yc-sheet" key={i}>
              {sheet.map((c) => <div className="yc-slot" key={c.name}><PostCard card={c} /></div>)}
            </div>
          ))}
        </div>,
        document.body,
      )}
    </div>
  );
}

function chunk<T>(items: T[], size: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size));
  return out;
}

/** 엽서 한 장 — 화면 미리보기와 인쇄가 같은 모양을 쓴다 */
export function PostCard({ card, onOverflow }: { card: YearCard; onOverflow?: (over: boolean) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (el && onOverflow) onOverflow(el.scrollHeight > el.clientHeight + 1);
  });
  const n = card.numbers;
  const stats = [
    // 311 — 응원 카드라 "마친 과제" · "중간 성과" 대신 함께한 동료 · 부서(0 이면 숨김)
    n.projects ? ["함께한 과제", `${n.projects}`] : null,
    n.colleagues ? ["함께한 동료", `${n.colleagues}명`] : null,
    n.partners ? ["함께한 부서", `${n.partners}곳`] : null,
    n.hours ? ["역량 강화", `${n.hours}시간`] : n.activities ? ["역량 강화 활동", `${n.activities}`] : null,   // 303 — 엽서 칸이 좁아 "개인" 은 뺌
  ].filter(Boolean) as string[][];
  return (
    <div className="postcard" ref={ref} data-testid="postcard">
      <div className="pc-top">
        <span className="pc-year">{card.year}</span>
        <span className="pc-headline">{card.headline || `${card.year}년, 고마웠어요`}</span>
      </div>
      <div className="pc-person">
        <div className="pc-name">{card.name} 님</div>
        {stats.length > 0 && (
          <div className="pc-stats">{stats.map(([label, value]) => <span key={label}><b>{value}</b>{label}</span>)}</div>
        )}
      </div>
      {card.picked.length > 0 && (
        <div className="pc-works">
          {card.picked.map((c) => {
            const did = c.did_lines_card ?? c.did_lines.slice(0, 2);
            const result = c.result_lines_card ?? c.result_lines.slice(0, 2);
            return (
              <div className="pc-work" key={c.id}>
                <div className="pc-work-title"><b>{c.title_card || c.title}</b>{c.role && <span className="pc-role"> · {c.role}</span>}</div>
                {did.length > 0 && <ul className="pc-did">{did.map((line, i) => <li key={i}>{line}</li>)}</ul>}
                {result.length > 0 && <ul className="pc-result">{result.map((line, i) => <li key={i}>{line}</li>)}</ul>}
                {c.praise && <div className="pc-praise">“{c.praise}”</div>}
              </div>
            );
          })}
        </div>
      )}
      {(card.skills.length > 0 || card.tools.length > 0) && (
        <div className="pc-chips">
          {card.skills.length > 0 && <div className="pc-chip-row"><span className="pc-chip-label">역량</span><span className="pc-chip-list">{card.skills.map((v) => <span className="pc-chip" key={v}>{v}</span>)}</span></div>}
          {card.tools.length > 0 && <div className="pc-chip-row"><span className="pc-chip-label">보유 기술</span><span className="pc-chip-list">{card.tools.map((v) => <span className="pc-chip" key={v}>{v}</span>)}</span></div>}
        </div>
      )}
      {card.message && <div className="pc-letter">{card.message}</div>}
      <div className="pc-sign">{card.signer ? `— ${card.signer}` : ""} · {card.signed_on || card.signed_default || `${card.year}. 12.`}</div>
    </div>
  );
}
