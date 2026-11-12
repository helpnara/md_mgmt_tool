import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "../api";
import { notifyError } from "../notify";
import type { YearCard, YearCardListing } from "../types";
import { useEditedUnsaved } from "../util";

/**
 * 연말 회고 카드 (TODO 285) — 팀원역량 → [연말 카드] 탭(팀장 · 관리자만).
 *
 * 사람마다 엽서 한 장(100 × 148mm)에 그 해의 숫자 · 한 일(과제 최대 3) · 새로 쓴 보유 기술 · **팀장의 감사 편지**.
 * 왼쪽 사람 목록(준비 상태) · 가운데 고치기 · 오른쪽 **실제 크기 미리보기**(넘치면 알림).
 * [인쇄 · PDF 로 저장] — A4 한 장에 네 장(2 × 2)과 자를 선. 브라우저 인쇄 창에서 "PDF 로 저장" 또는 사내 프린터로(배율 100% · 여백 없음).
 */
export default function YearCards() {
  const thisYear = String(new Date().getFullYear());
  const [year, setYear] = useState(thisYear);
  const [listing, setListing] = useState<YearCardListing | null>(null);
  const [name, setName] = useState("");
  const [card, setCard] = useState<YearCard | null>(null);
  const [draft, setDraft] = useState({ message: "", headline: "", projects: [] as string[] });
  const [saved, setSaved] = useState(draft);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [printing, setPrinting] = useState<YearCard[] | null>(null);
  const [overflow, setOverflow] = useState(false);

  const loadList = async (keep = name) => {
    try {
      const next = await api.yearCards(year);
      setListing(next);
      const first = next.people.find((p) => !p.leader)?.name ?? next.people[0]?.name ?? "";
      setName(keep && next.people.some((p) => p.name === keep) ? keep : first);
    } catch (error) {
      notifyError((error as Error).message);
    }
  };
  useEffect(() => { void loadList(""); }, [year]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!name) { setCard(null); return; }
    api.yearCard(name, year).then((next) => {
      setCard(next);
      const d = { message: next.message, headline: next.headline, projects: next.chosen };
      setDraft(d);
      setSaved(d);
    }).catch((error: Error) => notifyError(error.message));
  }, [name, year]);
  const dirty = JSON.stringify(draft) !== JSON.stringify(saved);
  useEditedUnsaved("yearcards", draft, saved, busy);

  async function save() {
    if (!card) return;
    setBusy(true);
    try {
      const next = await api.saveYearCard(card.name, year, draft);
      setCard(next);
      const d = { message: next.message, headline: next.headline, projects: next.chosen };
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
    if (!has && d.projects.length >= (listing?.pick_max ?? 3)) return d;
    return { ...d, projects: has ? d.projects.filter((p) => p !== id) : [...d.projects, id] };
  });
  const preview: YearCard | null = card ? {
    ...card, message: draft.message, headline: draft.headline,
    picked: draft.projects.map((id) => card.candidates.find((c) => c.id === id)).filter(Boolean) as YearCard["picked"],
  } : null;
  // 팀장 본인 카드는 [모두 인쇄] · 준비 수에서 뺀다 — 고르면 따로 인쇄할 수는 있다
  const members = listing?.people.filter((p) => !p.leader) ?? [];
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
          사람마다 <b>엽서 한 장</b>(100 × 148mm)입니다 — 그 해의 숫자 · 한 일(과제 3개까지) · 새로 쓴 보유 기술 · <b>감사 편지</b>.
          인쇄는 <b>A4 한 장에 네 장</b>이 자를 선과 함께 나옵니다. 인쇄 창에서 <b>배율 100%(실제 크기) · 여백 없음</b>으로 출력하거나 "PDF 로 저장" 하세요. [모두 인쇄]에는 팀장 표시가 된 사람은 빠집니다.
          이 화면과 편지는 팀장 · 관리자만 봅니다(팀원 화면 · 업무 이력 파일에 나오지 않습니다). 면담 기록 · 효과 금액 · 다른 사람과의 비교는 넣지 않습니다.
        </p>
      </div>
      <div className="yc-cols">
        <ul className="yc-people card" aria-label="사람">
          {listing?.people.map((p) => (
            <li key={p.name}>
              <button type="button" className={p.name === name ? "yc-person on" : "yc-person"} onClick={() => setName(p.name)}>
                <b>{p.name}</b>{p.leader && <span className="tag leader-tag">팀장</span>}
                <span className={p.missing.length ? "muted yc-state" : "yc-state ok"}>{p.missing.length ? `남음: ${p.missing.join(" · ")}` : "준비 끝 ✓"}</span>
              </button>
            </li>
          ))}
        </ul>
        {card && preview && (
          <div className="card yc-edit" data-testid="yc-edit">
            <h3>{card.name} 님의 카드</h3>
            <label>한 줄 제목 <span className="muted">(선택 — 비우면 "{year}년, 고마웠어요")</span>
              <input value={draft.headline} maxLength={40} placeholder={`${year}년, 고마웠어요`} onChange={(e) => setDraft({ ...draft, headline: e.target.value })} />
            </label>
            <div className="yc-pick">
              <span className="exp-label">넣을 과제 <span className="muted">— {draft.projects.length} / {listing?.pick_max ?? 3}, 마친 과제 · 인정 한 줄이 있는 과제가 위</span></span>
              {card.candidates.length === 0 && <p className="muted">{year}년에 맡은 과제가 없습니다.</p>}
              {card.candidates.map((c) => (
                <label key={c.id} className="check-label yc-candidate">
                  <input type="checkbox" checked={draft.projects.includes(c.id)} onChange={() => toggle(c.id)} aria-label={`${c.title} 넣기`} />
                  <span>
                    <b>{c.title}</b> <span className="muted">{c.id}{c.done_this_year ? " · 마침" : ""}{c.role ? ` · ${c.role}` : ""}</span>
                    <br /><span className="muted">{c.result ? `결과: ${c.result}` : "결과 칸이 비었습니다 — 과제의 담당과 역할에서 채우면 카드에 나옵니다"}</span>
                    {c.praise && <><br /><span className="muted">인정 한 줄: “{c.praise}”</span></>}
                  </span>
                </label>
              ))}
            </div>
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
    n.projects ? ["함께한 과제", `${n.projects}`] : null,
    n.done ? ["마친 과제", `${n.done}`] : null,
    n.milestones ? ["중간 성과", `${n.milestones}`] : null,
    n.hours ? ["교육", `${n.hours}시간`] : n.activities ? ["교육 · 행사", `${n.activities}`] : null,
  ].filter(Boolean) as string[][];
  return (
    <div className="postcard" ref={ref} data-testid="postcard">
      <div className="pc-top">
        <span className="pc-year">{card.year}</span>
        <span className="pc-headline">{card.headline || `${card.year}년, 고마웠어요`}</span>
      </div>
      <div className="pc-name">{card.name} 님</div>
      {stats.length > 0 && (
        <div className="pc-stats">{stats.map(([label, value]) => <span key={label}><b>{value}</b>{label}</span>)}</div>
      )}
      {card.picked.length > 0 && (
        <div className="pc-works">
          {card.picked.map((c) => (
            <div className="pc-work" key={c.id}>
              <b>{c.title}</b>{c.role && <span className="pc-role"> · {c.role}</span>}
              {c.result && <div className="pc-result">{c.result}</div>}
              {c.praise && <div className="pc-praise">“{c.praise}”</div>}
            </div>
          ))}
        </div>
      )}
      {card.new_skills.length > 0 && <div className="pc-skills">새로 쓴 기술 · {card.new_skills.join(" · ")}</div>}
      {card.message && <div className="pc-letter">{card.message}</div>}
      <div className="pc-sign">{card.signer ? `— ${card.signer}` : ""} · {card.year}. 12.</div>
    </div>
  );
}
