import { useEffect, useState } from "react";
import { Wand2 } from "lucide-react";
import { api } from "../api";
import { copyText, COPY_FAILED } from "../clipboard";
import { notifyError } from "../notify";
import type { SkillEntry, TagAction, TagDecision, UnknownTag } from "../types";
import CardIntro from "./CardIntro";
import IconTitle from "./IconTitle";

const AXES = ["기술", "업무", "리더십", "문제해결"];
type Choice = { action: TagAction | ""; target: string; axis: string; unsure?: boolean; note?: string };

/**
 * 역량 태그 정리함 (TODO 262 · 261 — docs/팀원이력정리/역량태그입력.md).
 *
 * 사전에 없는 태그를 **팀 전체에서 모아** 한 번에 — 동의어로 · 새 역량으로 · 도구로 · 빼기. 비슷한 대표 역량을 먼저 제안한다.
 * **AI 로 맞추기** — 사전 + 정리할 태그로 프롬프트를 만들어 먼저 보이고 복사(71), 돌아온 `태그 | 맞출 곳` 답을 읽어 **고르는 칸만 채운다**.
 * 적용은 사람이 [적용]으로.
 */
export default function SkillCleanupCard() {
  const [tags, setTags] = useState<UnknownTag[] | null>(null);
  const [dictionary, setDictionary] = useState<SkillEntry[]>([]);
  const [choices, setChoices] = useState<Record<string, Choice>>({});
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [prompt, setPrompt] = useState<string | null>(null);
  const [answer, setAnswer] = useState("");
  const [copied, setCopied] = useState(false);

  const keyOf = (t: { axis: string; name: string }) => `${t.axis}|${t.name}`;
  const load = async () => {
    try {
      const [unknown, dict] = await Promise.all([api.unknownTags(), api.experienceSkills()]);
      setTags(unknown.items);
      setDictionary(dict.dictionary);
      // 처음 고르기 — 팀의 기술 · 도구에 있으면 "도구로", 아니면 비워 둔다(사람이 고른다)
      setChoices(Object.fromEntries(unknown.items.map((t) => [keyOf(t), {
        action: t.tool_like ? "tool" : "", target: t.suggest[0] ? keyOf(t.suggest[0]) : "", axis: t.axis,
      } as Choice])));
    } catch (error) {
      notifyError((error as Error).message);
    }
  };
  useEffect(() => { void load(); }, []);

  const set = (key: string, patch: Partial<Choice>) => setChoices({ ...choices, [key]: { ...choices[key], ...patch } });
  const decided = Object.entries(choices).filter(([, c]) => c.action && (c.action !== "alias" || c.target));

  async function apply() {
    if (!tags || decided.length === 0) return;
    const actions: TagDecision[] = decided.map(([key, c]) => {
      const [axis, name] = key.split("|");
      const [targetAxis, targetName] = c.target.split("|");
      return c.action === "alias" ? { axis, name, action: "alias", target_axis: targetAxis, target_name: targetName }
        : c.action === "new" ? { axis, name, action: "new", target_axis: c.axis } : { axis, name, action: c.action as TagAction };
    });
    if (!window.confirm(`태그 ${actions.length}개를 정리할까요? 사전과 모든 팀원 경험의 태그가 함께 바뀝니다(이전 버전에 남습니다).`)) return;
    setBusy(true);
    try {
      const result = await api.cleanupTags(actions);
      setNotice(`정리했습니다 — 경험 ${result.changed.length}건의 태그를 바꿨습니다.`);
      setPrompt(null);
      setAnswer("");
      await load();
    } catch (error) {
      notifyError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function openPrompt() {
    try {
      setPrompt((await api.tagPrompt()).text);
    } catch (error) {
      notifyError((error as Error).message);
    }
  }

  async function readAnswer() {
    try {
      const { items } = await api.tagAnswer(answer);
      const next = { ...choices };
      for (const row of items) {
        const key = keyOf(row);
        if (!next[key]) continue;
        if (row.problem) next[key] = { ...next[key], note: row.problem };
        else if (row.action) {
          next[key] = {
            ...next[key], action: row.action as TagAction, unsure: row.unsure, note: "",
            target: row.action === "alias" ? `${row.target_axis}|${row.target_name}` : next[key].target,
            axis: row.action === "new" ? row.target_axis ?? next[key].axis : next[key].axis,
          };
        }
      }
      setChoices(next);
      setNotice(`AI 의 답 ${items.length}줄을 고르는 칸에 채웠습니다 — 확인하고 [적용]하세요. ? 표시는 AI 가 확실하지 않다고 한 것입니다.`);
    } catch (error) {
      notifyError((error as Error).message);
    }
  }

  async function copyPrompt() {
    if (!prompt) return;
    if (!(await copyText(prompt))) {
      notifyError(COPY_FAILED);
      return;
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="card skill-cleanup settings-wide" data-testid="skill-cleanup">
      <div className="card-head">
        <IconTitle icon={Wand2}>역량 태그 정리함 — 사전에 없는 태그 {tags?.length ?? 0}개</IconTitle>
        <div className="person-tools">
          <button className="ghost" disabled={!tags?.length} onClick={() => (prompt === null ? void openPrompt() : setPrompt(null))}>
            {prompt === null ? "AI 로 맞추기" : "AI 로 맞추기 닫기"}
          </button>
        </div>
      </div>
      <CardIntro id="skill-cleanup">
        모든 팀원 경험에서 <b>사전에 없는 태그</b>를 모았습니다. 태그마다 <b>동의어로</b>(사전의 역량에 다른 이름으로 더함) · <b>새 역량으로</b> ·
        <b> 도구로</b>(Python 같은 이름 — 도구 칸으로) · <b>빼기</b>(“개발 · 구축” 같은 넓은 말)를 고르고 [적용]합니다. 경험 하나씩 고치지 않아도 됩니다.
      </CardIntro>
      {prompt !== null && (
        <div className="refine-panel" data-testid="tag-prompt">
          <p className="hint">사내 AI 에 붙여넣을 글입니다 — <b>읽어 보고</b> 복사하세요. 답의 <code>태그 | 맞출 곳</code> 줄을 아래에 붙이면 고르는 칸만 채웁니다(바로 적용하지 않음).</p>
          <textarea className="refine-text" readOnly value={prompt} aria-label="태그 맞추기 프롬프트" />
          <div className="form-actions"><button onClick={() => void copyPrompt()}>{copied ? "복사됨 ✓" : "전문 복사"}</button></div>
          <textarea className="import-paste" value={answer} onChange={(e) => setAnswer(e.target.value)} aria-label="AI 의 답" placeholder="- 알고리즘 개발 | 버림" />
          <div className="form-actions"><button className="ghost" disabled={!answer.trim()} onClick={() => void readAnswer()}>답 읽기</button></div>
        </div>
      )}
      {notice && <p className="hint notice">{notice}</p>}
      {!tags ? <p className="muted">불러오는 중…</p> : tags.length === 0 ? (
        <p className="muted">사전에 없는 태그가 없습니다.</p>
      ) : (
        <div className="table-scroll skill-table-wrap">
          <table className="grid cleanup-table">
            <thead><tr><th>축</th><th>태그</th><th title="이 태그가 붙은 경험 수">경험</th><th>누구</th><th>정리</th></tr></thead>
            <tbody>
              {tags.map((t) => {
                const key = keyOf(t);
                const c = choices[key] ?? { action: "", target: "", axis: t.axis };
                return (
                  <tr key={key} data-tag={t.name}>
                    <td className="muted">{t.axis}</td>
                    <td>{t.name}{t.tool_like && <span className="muted" title="팀의 기술 · 도구 목록에 있는 이름"> · 도구?</span>}</td>
                    <td className="num">{t.count}</td>
                    <td className="muted">{t.people.join(" · ")}</td>
                    <td className="cleanup-choice">
                      <select aria-label="정리" value={c.action} onChange={(e) => set(key, { action: e.target.value as TagAction | "", note: "" })}>
                        <option value="">그대로</option>
                        <option value="alias">동의어로</option>
                        <option value="new">새 역량으로</option>
                        <option value="tool">도구로</option>
                        <option value="drop">빼기</option>
                      </select>
                      {c.action === "alias" && (
                        <select aria-label="맞출 역량" value={c.target} onChange={(e) => set(key, { target: e.target.value })}>
                          <option value="">— 고르기 —</option>
                          {t.suggest.length > 0 && <optgroup label="비슷한 것">{t.suggest.map((sg) => <option key={`s${keyOf(sg)}`} value={keyOf(sg)}>{sg.axis} · {sg.name}</option>)}</optgroup>}
                          <optgroup label="사전 전체">{dictionary.map((d) => <option key={keyOf(d)} value={keyOf(d)}>{d.axis} · {d.name}</option>)}</optgroup>
                        </select>
                      )}
                      {c.action === "new" && (
                        <select aria-label="새 역량의 축" value={c.axis} onChange={(e) => set(key, { axis: e.target.value })}>
                          {AXES.map((a) => <option key={a}>{a}</option>)}
                        </select>
                      )}
                      {c.unsure && <span className="form-warn" title="AI 가 확실하지 않다고 한 것">?</span>}
                      {c.note && <span className="form-warn">{c.note}</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <div className="form-actions">
        <button disabled={busy || decided.length === 0} onClick={() => void apply()}>{busy ? "정리하는 중…" : `적용 (${decided.length})`}</button>
      </div>
    </div>
  );
}
