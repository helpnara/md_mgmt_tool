import { useEffect, useState } from "react";
import { Wrench } from "lucide-react";
import { api } from "../api";
import { notifyError } from "../notify";
import type { ToolDictionary, ToolEntry } from "../types";
import { useEditedUnsaved } from "../util";
import CardIntro from "./CardIntro";
import IconTitle from "./IconTitle";
import RunningLine from "./RunningLine";

type Row = { name: string; aliases: string; origin: string };

const toRows = (entries: ToolEntry[]): Row[] => entries.map((e) => ({ name: e.name, aliases: e.aliases.join(", "), origin: e.name }));

/**
 * 보유 기술 사전 (TODO 273). 설정 → [분류 · 접수] 탭, 역량 사전 아래.
 *
 * 역량(무엇을 할 줄 아는가 — 행동 · 방법, 분석 기법 포함)과 보유 기술(무엇으로 했는가 — 언어 · 소프트웨어 · 장비)을 가르는 기준이다.
 * 이 사전에 있는 이름만 보유 기술로 보고(역량 칸에 적어도 보유 기술 칸으로 옮긴다), 다른 이름은 대표 이름으로 맞춘다(파이썬 = Python).
 * 저장하면 **이미 적힌 것도** 지금 사전으로 다시 맞춘다 — 경험 파일의 보유 기술과 과제(담당과 역할) 색인.
 */
export default function ToolDictionaryCard() {
  const [data, setData] = useState<ToolDictionary | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");

  const load = () =>
    api.experienceTools().then((next) => {
      setData(next);
      setRows(toRows(next.dictionary));
    }).catch((error: Error) => notifyError(error.message));
  useEffect(() => { void load(); }, []);

  const savedRows = data ? toRows(data.dictionary) : [];
  const dirty = JSON.stringify(rows) !== JSON.stringify(savedRows);
  useEditedUnsaved("settings:tools", dirty ? "1" : "0", "0", busy);

  const set = (index: number, patch: Partial<Row>) => setRows(rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  const names = rows.map((row) => row.name.trim().toLowerCase()).filter(Boolean);
  const duplicate = rows.find((row, i) => row.name.trim() && names.indexOf(row.name.trim().toLowerCase()) !== i)?.name;
  // 사전에 없는데 쓰인 이름 — 역량 사전에 있는 이름(분석 기법 · 방법)은 후보에서 뺀다
  const candidates = (data?.unlisted ?? []).filter((item) => !item.skill_like && !names.includes(item.name.trim().toLowerCase()));
  const skillLike = (data?.unlisted ?? []).filter((item) => item.skill_like);

  async function save(next: ToolEntry[] | null, message: string) {
    setBusy(true);
    try {
      await api.saveSettings({ tool_dictionary: next ?? [] });
      // 이미 적힌 것도 지금 사전으로 — 경험 파일 · 과제 색인
      const { changed } = await api.rematchTools();
      await load();
      setNotice(`${message}${changed.length ? ` 경험 ${changed.length}건의 보유 기술을 사전에 맞췄습니다.` : ""}`);
      window.setTimeout(() => setNotice(""), 5000);
    } catch (error) {
      notifyError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card skill-dictionary settings-wide" data-testid="tool-dictionary">
      <div className="card-head">
        <IconTitle icon={Wrench}>보유 기술 사전 {rows.length}개{data && !data.custom ? " (기본)" : ""}</IconTitle>
      </div>
      <CardIntro id="tool-dictionary">
        <b>보유 기술</b>은 <b>무엇으로 했는가</b>입니다 — 프로그래밍 언어 · 소프트웨어 · 장비 · 플랫폼처럼 이름만으로 “쓸 줄 안다” 가 되는 것.
        회귀 분석 · 실험계획법 같은 <b>분석 기법 · 방법은 역량</b>(위의 역량 사전)에 둡니다. 이 사전에 있는 이름만 보유 기술로 보고,
        다른 이름은 대표 이름으로 맞춥니다(파이썬 → Python). 저장하면 이미 적힌 경험 · 과제의 보유 기술도 지금 사전으로 다시 맞춥니다.
      </CardIntro>
      <div className="table-scroll skill-table-wrap">
        <table className="grid skill-table">
          <thead><tr><th>대표 이름</th><th>다른 이름 (쉼표로)</th><th title="과제(담당과 역할) · 경험에 적힌 횟수">쓰인 곳</th><th /></tr></thead>
          <tbody>
            {rows.map((row, index) => {
              const used = data?.usage[row.origin] ?? 0;
              return (
                <tr key={index} data-tool={row.name}>
                  <td><input aria-label="보유 기술 대표 이름" value={row.name} maxLength={60} onChange={(event) => set(index, { name: event.target.value })} /></td>
                  <td><input aria-label="보유 기술 다른 이름" value={row.aliases} onChange={(event) => set(index, { aliases: event.target.value })} /></td>
                  <td className={used ? "num" : "zero num"}>{used || "-"}</td>
                  <td className="one-line">
                    <button type="button" className="ghost small danger" onClick={() => setRows(rows.filter((_, i) => i !== index))}
                      title={used ? "사전에서 빼도 과제 · 경험에 적힌 이름은 그대로 남습니다(사전에 없는 이름으로)" : ""}>빼기</button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {candidates.length > 0 && (
        <p className="hint" data-testid="tool-candidates">
          사전에 없는데 쓰인 이름 {candidates.length}개 — {candidates.slice(0, 12).map((item) => `${item.name}(${item.count})`).join(" · ")}
          {candidates.length > 12 ? " …" : ""}{" "}
          <button type="button" className="link-button"
            onClick={() => setRows([...rows, ...candidates.map((item) => ({ name: item.name, aliases: "", origin: "" }))])}>
            쓰인 이름 불러오기
          </button>
          <span className="muted"> — 불러온 뒤 보유 기술이 아닌 줄은 [빼기]하고 저장하세요.</span>
        </p>
      )}
      {skillLike.length > 0 && (
        <p className="hint">
          보유 기술 칸에 적혀 있지만 <b>역량 사전에 있는 이름</b> {skillLike.length}개 — {skillLike.slice(0, 8).map((item) => item.name).join(" · ")}.
          역량이므로 경험의 역량 태그로 옮겨 적는 것이 맞습니다.
        </p>
      )}
      {duplicate && <p className="form-warn">같은 대표 이름이 둘 있습니다: {duplicate}</p>}
      {notice && <p className="hint notice">{notice}</p>}
      <RunningLine active={busy} runKey="tools-rematch" label="보유 기술 다시 맞추기" />
      <div className="form-actions">
        <button type="button" className="ghost" onClick={() => setRows([...rows, { name: "", aliases: "", origin: "" }])}>+ 보유 기술</button>
        <button type="button" className="ghost" disabled={busy || !data?.custom}
          onClick={() => window.confirm("보유 기술 사전을 처음 목록으로 되돌릴까요? 과제 · 경험에 적힌 이름은 지워지지 않습니다.") && void save(null, "기본 사전으로 되돌렸습니다.")}>
          기본으로
        </button>
        <button disabled={busy || !dirty || Boolean(duplicate)}
          onClick={() => void save(rows.filter((row) => row.name.trim()).map((row) => ({
            name: row.name.trim(), aliases: row.aliases.split(",").map((a) => a.trim()).filter(Boolean),
          })), "저장했습니다.")}>
          {busy ? "저장 중…" : "저장"}
        </button>
      </div>
    </div>
  );
}
