import { useEffect, useState } from "react";
import { FileDown, History, Settings2, ShieldOff } from "lucide-react";
import { api } from "../api";
import { copyText, COPY_FAILED } from "../clipboard";
import { isManager } from "../me";
import { notifyError } from "../notify";
import { personLink, setPageTitle } from "../nav";
import type { AnonymizeCandidates, AnonymizeRule, ExperienceSummary, ExportLogRow, ExportOptions, ExportResult } from "../types";
import IconTitle from "./IconTitle";

const KINDS = ["회사", "조직", "인명", "제품", "공정", "고객", "기관", "기타"];
/** 원본 FR-H8 의 고정 문구를 사내에 맞춰 */
const NOTE = "이 파일은 팀원 본인에게 건네는 업무 이력입니다. 사외 AI 서비스에 넣을 수 있으니 익명화 · 효과 금액 옵션을 확인하세요.";

/**
 * 업무 이력 파일 (TODO 262 · 253 의 5단계 — 원본 UX S-08 을 두 칸으로, 프롬프트 · 합본 탭은 없다: README 1절 · 238 ④).
 *
 * 왼쪽 설정(범위 · 상태 · 근거 ID · 효과 금액 · 익명화) → 오른쪽 미리보기. **보인 글 = 저장 · 복사되는 글**(서버가 만든 그대로).
 * 저장 · 복사할 때 기록 한 줄(누가 · 언제 · 범위 · 옵션 — 내용은 남기지 않음).
 */
export default function ExperienceExport({ name }: { name: string }) {
  const manager = isManager();
  const [opt, setOpt] = useState<ExportOptions>({ scope: "all", structured: false, ids_in: true, money: false, anonymize: false });
  const [result, setResult] = useState<ExportResult | null>(null);
  const [error, setError] = useState("");
  const [items, setItems] = useState<ExperienceSummary[]>([]);
  const [log, setLog] = useState<ExportLogRow[]>([]);
  const [copied, setCopied] = useState(false);
  const [anon, setAnon] = useState<AnonymizeCandidates | null>(null);
  const [rules, setRules] = useState<AnonymizeRule[]>([]);
  const [showRules, setShowRules] = useState(false);

  useEffect(() => setPageTitle(`${name} — 업무 이력 파일`), [name]);
  useEffect(() => {
    api.experiences(name).then((data) => setItems(data.items)).catch(() => setItems([]));
    api.exportLog(name).then((data) => setLog(data.items)).catch(() => setLog([]));
  }, [name]);
  // 옵션을 바꾸면 미리보기를 다시(원본 S-08 — 0.3초 디바운스)
  useEffect(() => {
    let stale = false;
    const timer = window.setTimeout(() => {
      api.exportFile(name, opt)
        .then((next) => { if (!stale) { setResult(next); setError(""); } })
        .catch((err: Error) => { if (!stale) { setResult(null); setError(err.message); } });
    }, 300);
    return () => { stale = true; window.clearTimeout(timer); };
  }, [name, JSON.stringify(opt)]); // eslint-disable-line react-hooks/exhaustive-deps

  async function loadAnon() {
    try {
      const data = await api.anonymizeCandidates(name);
      setAnon(data);
      setRules(data.rules);
    } catch (err) {
      notifyError((err as Error).message);
    }
  }
  useEffect(() => { if (opt.anonymize && !anon) void loadAnon(); }, [opt.anonymize]); // eslint-disable-line react-hooks/exhaustive-deps

  async function saveRules(next: AnonymizeRule[]) {
    try {
      await api.saveSettings({ anonymize_rules: { rules: next.filter((r) => r.from.trim() && r.to.trim()), patterns: anon?.patterns } });
      await loadAnon();
      setOpt({ ...opt });                                        // 미리보기를 다시
    } catch (err) {
      notifyError((err as Error).message);
    }
  }

  async function record(how: "저장" | "복사") {
    try {
      await api.logExport(name, opt, how);
      setLog((await api.exportLog(name)).items);
    } catch {
      /* 기록이 안 남아도 파일은 이미 나갔다 — 다음 번에 다시 */
    }
  }

  function download() {
    if (!result) return;
    const blob = new Blob([result.text], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = result.filename;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    void record("저장");
  }

  async function copy() {
    if (!result) return;
    if (!(await copyText(result.text))) {
      notifyError(COPY_FAILED);
      return;
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
    void record("복사");
  }

  const set = (patch: Partial<ExportOptions>) => setOpt({ ...opt, ...patch });
  const pickable = items.filter((i) => i.status === "확정" || (opt.structured && i.status === "구조화"));
  const s = result?.summary;
  return (
    <section className="experience-export" data-testid="experience-export">
      <a className="back" href={personLink(name)}>← {name}의 이력</a>
      <h1 className="import-title">{name} — 업무 이력 파일</h1>
      <div className="export-columns">
        <div className="export-left">
          <div className="card">
            <IconTitle icon={Settings2}>설정</IconTitle>
            <fieldset className="export-options">
              <legend className="exp-label">범위</legend>
              {(["all", "period", "pick"] as const).map((scope) => (
                <label key={scope}><input type="radio" name="scope" checked={opt.scope === scope} onChange={() => set({ scope })} />
                  {scope === "all" ? "전체" : scope === "period" ? "기간" : "직접 고르기"}</label>
              ))}
            </fieldset>
            {opt.scope === "period" && (
              <div className="form-row">
                <label>시작<input aria-label="시작" placeholder="2025-01" value={opt.start ?? ""} onChange={(e) => set({ start: e.target.value })} /></label>
                <label>끝<input aria-label="끝" placeholder="비우면 지금" value={opt.end ?? ""} onChange={(e) => set({ end: e.target.value })} /></label>
              </div>
            )}
            {opt.scope === "pick" && (
              <div className="export-pick">
                {pickable.length === 0 && <p className="muted">고를 경험이 없습니다(확정{opt.structured ? " · 구조화" : ""}).</p>}
                {pickable.map((i) => (
                  <label key={i.id}><input type="checkbox" checked={(opt.ids ?? []).includes(i.id)}
                    onChange={() => set({ ids: (opt.ids ?? []).includes(i.id) ? (opt.ids ?? []).filter((x) => x !== i.id) : [...(opt.ids ?? []), i.id] })} />
                    <span className="project-id">{i.id}</span> {i.title} <span className="muted">· {i.status}</span></label>
                ))}
              </div>
            )}
            <div className="export-flags">
              <label><input type="checkbox" checked={Boolean(opt.structured)} onChange={(e) => set({ structured: e.target.checked })} /> 구조화도 넣기 <span className="muted">(초안은 넣지 않음)</span></label>
              <label><input type="checkbox" checked={opt.ids_in !== false} onChange={(e) => set({ ids_in: e.target.checked })} /> 근거 ID 넣기 <span className="muted">(E-001)</span></label>
              <label><input type="checkbox" checked={Boolean(opt.money)} onChange={(e) => set({ money: e.target.checked })} /> 효과 금액 넣기 <span className="muted">(과제 전체 금액)</span></label>
              <label><input type="checkbox" checked={Boolean(opt.anonymize)} onChange={(e) => set({ anonymize: e.target.checked })} /> 익명화</label>
            </div>
          </div>
          {opt.anonymize && anon && (
            <div className="card export-anon" data-testid="anonymize">
              <IconTitle icon={ShieldOff}>익명화 치환표 {rules.length}개</IconTitle>
              <p className="hint">팀 하나에 하나 — 고객사 이름 · 공정명은 자동으로 다 찾지 못합니다. 직접 넣으세요.</p>
              {manager ? (
                <>
                  <button className="ghost small" onClick={() => setShowRules((v) => !v)} aria-expanded={showRules}>{showRules ? "접기" : "치환표 · 후보 보기"}</button>
                  {showRules && (
                    <>
                      <table className="grid export-rules">
                        <thead><tr><th>종류</th><th>바꿀 말</th><th>바꾼 말</th><th /></tr></thead>
                        <tbody>
                          {rules.map((rule, index) => (
                            <tr key={index}>
                              <td><select aria-label="종류" value={rule.kind} onChange={(e) => setRules(rules.map((r, i) => (i === index ? { ...r, kind: e.target.value } : r)))}>
                                {KINDS.map((k) => <option key={k}>{k}</option>)}</select></td>
                              <td><input aria-label="바꿀 말" value={rule.from} onChange={(e) => setRules(rules.map((r, i) => (i === index ? { ...r, from: e.target.value } : r)))} /></td>
                              <td><input aria-label="바꾼 말" value={rule.to} onChange={(e) => setRules(rules.map((r, i) => (i === index ? { ...r, to: e.target.value } : r)))} /></td>
                              <td><button className="ghost small danger" onClick={() => setRules(rules.filter((_, i) => i !== index))}>빼기</button></td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      <div className="form-actions">
                        <button className="ghost small" onClick={() => setRules([...rules, { kind: "회사", from: "", to: "" }])}>+ 규칙</button>
                        <button className="small" onClick={() => void saveRules(rules)}>치환표 저장</button>
                      </div>
                      <p className="exp-label">후보 — 눌러 치환표에 더합니다</p>
                      <div className="export-candidates">
                        {anon.items.filter((c) => !rules.some((r) => r.from === c.text)).map((c) => (
                          <button key={c.text} className="exp-chip" title={c.kind}
                            onClick={() => setRules([...rules, { kind: c.kind, from: c.text, to: c.suggest || "○○" }])}>
                            {c.text}{c.suggest ? ` → ${c.suggest}` : ""}
                          </button>
                        ))}
                      </div>
                    </>
                  )}
                </>
              ) : (
                <p className="muted">치환표는 팀장이 정합니다 — 지금 규칙 {rules.length}개가 적용됩니다.</p>
              )}
            </div>
          )}
        </div>

        <div className="card export-right" data-testid="export-preview">
          <IconTitle icon={FileDown}>미리보기</IconTitle>
          {error && <p className="error">{error}</p>}
          {s && (
            <>
              <div className="import-summary export-summary">
                <span>경험 <b>{s.experiences}</b>건(확정 {s.confirmed}{s.structured ? ` · 구조화 ${s.structured}` : ""})</span>
                {s.period && <span>{s.period}</span>}
                <span>과제 {s.projects}</span>
                <span>정량 {s.quants} (비교 {s.quants_compared} · 기준 없음 {s.quants - s.quants_compared})</span>
                <span>{(result?.chars ?? 0).toLocaleString()}자</span>
                {opt.anonymize && <span>치환 {Object.values(s.replaced).reduce((a, b) => a + b, 0)}회</span>}
              </div>
              <div className="export-axes">
                {Object.entries(s.axes).map(([axis, n]) => <span key={axis} className="exp-chip">{axis} <b>{n}</b></span>)}
                {s.top_skills.length > 0 && <span className="muted">많이 쓴 역량: {s.top_skills.join(" · ")}</span>}
              </div>
            </>
          )}
          {result && result.warnings.length > 0 && (
            <ul className="exp-warn-list export-warnings" data-testid="export-warnings">{result.warnings.map((w) => <li key={w}>⚠ {w}</li>)}</ul>
          )}
          <textarea className="export-text" readOnly value={result?.text ?? ""} aria-label="업무 이력 파일 원문" />
          <div className="form-actions">
            <span className="muted">{result?.filename}</span>
            <button className="ghost" disabled={!result || result.ids.length === 0} onClick={() => void copy()}>{copied ? "복사됨 ✓" : "파일 복사"}</button>
            <button disabled={!result || result.ids.length === 0} onClick={download}>파일 저장 (.md)</button>
          </div>
          <p className="hint">ⓘ {NOTE}</p>
          <div className="export-log" data-testid="export-log">
            <IconTitle icon={History}>내보내기 기록</IconTitle>
            {log.length === 0 ? <p className="muted">아직 없습니다.</p> : (
              <ul>
                {log.map((row, index) => (
                  <li key={index}>
                    {row.at.slice(0, 16).replace("T", " ")} · {row.by || row.role} · {row.how} · {row.count}건 ·{" "}
                    {row.options.scope === "all" ? "전체" : row.options.scope === "period" ? `기간 ${row.options.start}~${row.options.end}` : "선택"}
                    {row.options.structured ? " · 구조화 포함" : ""}{row.options.money ? " · 효과 금액" : ""}{row.options.anonymize ? " · 익명화" : ""}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
