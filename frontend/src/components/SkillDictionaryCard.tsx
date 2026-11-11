import { useEffect, useState } from "react";
import { Tags } from "lucide-react";
import { api } from "../api";
import { notifyError } from "../notify";
import type { ExperienceSkill, SkillDictionary, SkillEntry } from "../types";
import { axisLabel, useEditedUnsaved } from "../util";
import CardIntro from "./CardIntro";
import IconTitle from "./IconTitle";
import DictionaryEditor, { type DictRow } from "./DictionaryEditor";

const AXES: ExperienceSkill["axis"][] = ["기술", "업무", "리더십", "문제해결"];

type Row = DictRow;

const toRows = (entries: SkillEntry[]): Row[] =>
  entries.map((e) => ({ axis: e.axis, name: e.name, aliases: [...e.aliases], origin: `${e.axis}|${e.name}` }));

/**
 * 역량 사전 (TODO 260 · 253 의 4단계 — 4단계.md 2절 · 정할 것 ①). 설정 → [분류 · 접수] 탭.
 *
 * 경험의 역량 태그를 맞추는 표 — 대표 이름 + 다른 이름(동의어). 비우면 기본(설계 원본 9절의 46개).
 * 쓰는 경험이 있는 항목은 지우지 않고 **다른 역량으로 합치기**(경험의 태그를 함께 바꾸고 옛 이름은 동의어로 남긴다).
 */
export default function SkillDictionaryCard() {
  const [data, setData] = useState<SkillDictionary | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");

  const load = () =>
    api.experienceSkills().then((next) => {
      setData(next);
      setRows(toRows(next.dictionary));
    }).catch((error: Error) => notifyError(error.message));
  useEffect(() => { void load(); }, []);

  const savedRows = data ? toRows(data.dictionary) : [];
  const dirty = JSON.stringify(rows) !== JSON.stringify(savedRows);
  useEditedUnsaved("settings:skills", dirty ? "1" : "0", "0", busy);

  const usage = (row: Row) => data?.usage[row.origin] ?? 0;
  const names = rows.map((row) => row.name.trim()).filter(Boolean);
  const duplicate = names.find((name, i) => names.indexOf(name) !== i);

  async function save(next: SkillEntry[] | null, message: string) {
    setBusy(true);
    try {
      await api.saveSettings({ skill_dictionary: next ?? [] });
      await load();
      setNotice(message);
      window.setTimeout(() => setNotice(""), 3000);
    } catch (error) {
      notifyError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function merge(row: Row, target: string) {
    const [toAxis, toName] = target.split("|");
    if (!toName || !window.confirm(`‘${row.name}’ 을(를) ‘${toName}’ 으로 합칠까요? 쓰는 경험 ${usage(row)}건의 태그가 함께 바뀌고, 옛 이름은 동의어로 남습니다.`)) return;
    setBusy(true);
    try {
      const [fromAxis, fromName] = row.origin.split("|");
      const result = await api.mergeSkill({ axis: fromAxis, name: fromName }, { axis: toAxis, name: toName });
      await load();
      setNotice(`합쳤습니다 — 경험 ${result.changed.length}건의 태그를 바꿨습니다.`);
    } catch (error) {
      notifyError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card skill-dictionary" data-testid="skill-dictionary">
      <div className="card-head">
        <IconTitle icon={Tags}>역량 사전 {rows.length}개{data && !data.custom ? " (기본)" : ""}</IconTitle>
      </div>
      <CardIntro id="skill-dictionary">
        경험의 <b>역량 태그</b>(무엇을 할 줄 아는가 — 분석 기법 · 방법 포함)를 맞추는 사전입니다 — 저장하거나 AI 응답을 되받을 때 다른 이름을 대표 이름 · 축으로 바꿉니다.
        쓰는 역량은 지우지 않고 <b>다른 역량으로 합치기</b>로 정리합니다. [기본으로]는 처음 46개로 돌아갑니다.
      </CardIntro>
      <DictionaryEditor rows={rows} saved={savedRows} setRows={setRows} axes={AXES} usage={usage} itemLabel="역량"
        removable={(row) => !usage(row)}
        extraActions={(row) => usage(row) > 0 && row.origin ? (
          <select aria-label="다른 역량으로 합치기" value="" disabled={busy || dirty} title={dirty ? "고친 것을 먼저 저장하세요" : ""}
            onChange={(event) => void merge(row, event.target.value)}>
            <option value="">다른 역량으로 합치기 ▾ (쓰는 경험 {usage(row)}건)</option>
            {rows.filter((other) => other.origin && other.origin !== row.origin).map((other) => (
              <option key={other.origin} value={other.origin}>{axisLabel(other.axis ?? "")} · {other.name}</option>
            ))}
          </select>
        ) : null} />
      {duplicate && <p className="form-warn">같은 대표 이름이 둘 있습니다: {duplicate}</p>}
      {notice && <p className="hint notice">{notice}</p>}
      <div className="form-actions">
                <button type="button" className="ghost" disabled={busy || dirty} title="실제 팀원 태그에서 본 다른 이름(운영 최적화 → 최적화·시뮬레이션 등)을 한 번에 더합니다(TODO 261)"
          onClick={() => void (async () => {
            setBusy(true);
            try {
              const { added } = await api.addSuggestedAliases();
              await load();
              setNotice(added ? `추천 동의어 ${added}개를 더했습니다.` : "더할 추천 동의어가 없습니다 — 이미 있습니다.");
            } catch (error) {
              notifyError((error as Error).message);
            } finally {
              setBusy(false);
            }
          })()}>추천 동의어 더하기</button>
        <button type="button" className="ghost" disabled={busy || !data?.custom}
          onClick={() => window.confirm("역량 사전을 처음 46개로 되돌릴까요? 경험의 태그는 그대로입니다.") && void save(null, "기본 사전으로 되돌렸습니다.")}>
          기본으로
        </button>
        <button disabled={busy || !dirty || Boolean(duplicate)}
          onClick={() => void save(rows.filter((row) => row.name.trim()).map((row) => ({
            axis: row.axis as ExperienceSkill["axis"], name: row.name.trim(), aliases: row.aliases,
          })), "저장했습니다.")}>
          {busy ? "저장 중…" : "저장"}
        </button>
      </div>
    </div>
  );
}
