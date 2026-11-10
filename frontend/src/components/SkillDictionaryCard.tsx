import { useEffect, useState } from "react";
import { Tags } from "lucide-react";
import { api } from "../api";
import { notifyError } from "../notify";
import type { ExperienceSkill, SkillDictionary, SkillEntry } from "../types";
import { useEditedUnsaved } from "../util";
import CardIntro from "./CardIntro";
import IconTitle from "./IconTitle";

const AXES: ExperienceSkill["axis"][] = ["기술", "업무", "리더십", "문제해결"];

type Row = { axis: ExperienceSkill["axis"]; name: string; aliases: string; origin: string };

const toRows = (entries: SkillEntry[]): Row[] =>
  entries.map((e) => ({ axis: e.axis, name: e.name, aliases: e.aliases.join(", "), origin: `${e.axis}|${e.name}` }));

/**
 * 역량 사전 (TODO 260 · 253 의 4단계 — 4단계.md 2절 · 정할 것 ①). 설정 → [분류 · 접수] 탭.
 *
 * 경험의 역량 태그를 맞추는 표 — 대표 이름 + 다른 이름(동의어). 비우면 기본(설계 원본 9절의 46개).
 * 쓰는 경험이 있는 항목은 지우지 않고 **다른 역량으로 합치기**(경험의 태그를 함께 바꾸고 옛 이름은 동의어로 남긴다).
 */
export default function SkillDictionaryCard() {
  const [data, setData] = useState<SkillDictionary | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [axis, setAxis] = useState<ExperienceSkill["axis"] | "">("");
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
  const set = (index: number, patch: Partial<Row>) => setRows(rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));
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

  const shown = rows.map((row, index) => ({ row, index })).filter(({ row }) => !axis || row.axis === axis);
  return (
    <div className="card skill-dictionary settings-wide" data-testid="skill-dictionary">
      <div className="card-head">
        <IconTitle icon={Tags}>역량 사전 {rows.length}개{data && !data.custom ? " (기본)" : ""}</IconTitle>
        <div className="person-tools">
          <select aria-label="축으로 거르기" value={axis} onChange={(event) => setAxis(event.target.value as ExperienceSkill["axis"] | "")}>
            <option value="">축 전체</option>
            {AXES.map((a) => <option key={a}>{a}</option>)}
          </select>
        </div>
      </div>
      <CardIntro id="skill-dictionary">
        경험의 <b>역량 태그</b>를 맞추는 표입니다 — 저장하거나 AI 응답을 되받을 때 다른 이름(동의어)을 대표 이름 · 축으로 바꿉니다. 팀원역량(교육 · 행사)과는 다른 것입니다.
        쓰는 경험이 있는 역량은 지우지 않고 <b>다른 역량으로 합치기</b>로 정리합니다. [기본으로]는 처음 46개로 돌아갑니다.
      </CardIntro>
      <div className="table-scroll skill-table-wrap">
        <table className="grid skill-table">
          <thead><tr><th>축</th><th>대표 이름</th><th>다른 이름 (쉼표로)</th><th title="이 역량 태그가 붙은 경험 수">경험</th><th /></tr></thead>
          <tbody>
            {shown.map(({ row, index }) => {
              const used = usage(row);
              return (
                <tr key={index} data-skill={row.name}>
                  <td>
                    <select aria-label="축" value={row.axis} onChange={(event) => set(index, { axis: event.target.value as ExperienceSkill["axis"] })}>
                      {AXES.map((a) => <option key={a}>{a}</option>)}
                    </select>
                  </td>
                  <td><input aria-label="대표 이름" value={row.name} maxLength={60} onChange={(event) => set(index, { name: event.target.value })} /></td>
                  <td><input aria-label="다른 이름" value={row.aliases} onChange={(event) => set(index, { aliases: event.target.value })} /></td>
                  <td className={used ? "num" : "zero num"}>{used || "-"}</td>
                  <td className="one-line">
                    {used > 0 && row.origin ? (
                      <select aria-label="다른 역량으로 합치기" value="" disabled={busy || dirty} title={dirty ? "고친 것을 먼저 저장하세요" : ""}
                        onChange={(event) => void merge(row, event.target.value)}>
                        <option value="">다른 역량으로 합치기 ▾</option>
                        {rows.filter((other) => other.origin && other.origin !== row.origin).map((other) => (
                          <option key={other.origin} value={other.origin}>{other.axis} · {other.name}</option>
                        ))}
                      </select>
                    ) : (
                      <button type="button" className="ghost small danger" onClick={() => setRows(rows.filter((_, i) => i !== index))}>빼기</button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {duplicate && <p className="form-warn">같은 대표 이름이 둘 있습니다: {duplicate}</p>}
      {notice && <p className="hint notice">{notice}</p>}
      <div className="form-actions">
        <button type="button" className="ghost" onClick={() => setRows([...rows, { axis: axis || "기술", name: "", aliases: "", origin: "" }])}>+ 역량</button>
        <button type="button" className="ghost" disabled={busy || !data?.custom}
          onClick={() => window.confirm("역량 사전을 처음 46개로 되돌릴까요? 경험의 태그는 그대로입니다.") && void save(null, "기본 사전으로 되돌렸습니다.")}>
          기본으로
        </button>
        <button disabled={busy || !dirty || Boolean(duplicate)}
          onClick={() => void save(rows.filter((row) => row.name.trim()).map((row) => ({
            axis: row.axis, name: row.name.trim(), aliases: row.aliases.split(",").map((a) => a.trim()).filter(Boolean),
          })), "저장했습니다.")}>
          {busy ? "저장 중…" : "저장"}
        </button>
      </div>
    </div>
  );
}
