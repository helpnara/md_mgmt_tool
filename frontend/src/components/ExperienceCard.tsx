import { useEffect, useState } from "react";
import { Award } from "lucide-react";
import { api } from "../api";
import { getMe, isManager, isMember } from "../me";
import { notifyError } from "../notify";
import type { ExperienceListing } from "../types";
import IconTitle from "./IconTitle";
import CardIntro from "./CardIntro";

const AXES = ["기술", "업무", "리더십", "문제해결"] as const;

/** 경험 상세 주소 (TODO 257 · 2단계.md ①) — 사람별 이력에서 왔으면 돌아갈 곳을 함께 */
export function experienceLink(id: string): string {
  return `#/experience/${encodeURIComponent(id)}`;
}

/** 업무 이력 파일 주소 (TODO 262 · 5단계.md 5절) */
export function experienceExportLink(name: string): string {
  return `#/experience-export/${encodeURIComponent(name)}`;
}

/** AI 로 정리(응답 되받기) 주소 (TODO 258 · 3단계.md 6절) */
export function experienceImportLink(name: string): string {
  return `#/experience-import/${encodeURIComponent(name)}`;
}

/**
 * 사람별 이력의 [경험] 카드 (TODO 257 · 253 의 2단계 — 원본 UX S-04 를 줄여 옮김).
 *
 * 경험 = 과제 하나에서 나온 "상황 · 목표 · 행동 · 결과 · 교훈" 한 묶음. 2단계는 **초안**만 — 담당과 역할 · 회고에서 만들고 고친다.
 * [AI 로 정리](응답 되받기 — TODO 258)로 구조화, 확정은 4단계. 팀원 PC 는 자기 것을 보기만, 읽기 전용 공유 바깥에는 이 카드가 없다(면담과 같다).
 */
export default function ExperienceCard({
  name,
  retroProjects,
  reloadKey,
  onChanged,
}: {
  name: string;
  /** 회고가 있는 맡은 과제 번호 — [회고 있는 과제 모두 초안] 이 이것만 만든다 */
  retroProjects: string[];
  reloadKey: number;
  onChanged: (listing: ExperienceListing) => void;
}) {
  const [data, setData] = useState<ExperienceListing | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const manager = isManager();
  // 업무 이력 파일 — 관리자 · 팀장은 누구 것이든, 팀원 PC 는 자기 것만(5단계.md ⑥)
  const canExport = manager || (isMember() && getMe().name === name);

  const load = () =>
    api
      .experiences(name)
      .then((next) => {
        setData(next);
        onChanged(next);
      })
      .catch((error: Error) => notifyError(error.message));

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [name, reloadKey]);

  async function draftAll() {
    setBusy(true);
    try {
      const result = await api.draftExperiences(name);
      setNotice(
        result.made.length
          ? `초안 ${result.made.length}건을 만들었습니다(${result.made.join(" · ")}).` +
              (result.skipped.length ? ` 이미 있는 ${result.skipped.length}건은 건너뛰었습니다.` : "")
          : "새로 만들 초안이 없습니다 — 회고가 있는 과제는 이미 경험이 있습니다.",
      );
      await load();
    } catch (error) {
      notifyError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function rematch() {
    try {
      const result = await api.rematchSkills(name);
      setNotice(result.changed.length ? `경험 ${result.changed.length}건의 태그를 사전에 맞췄습니다.` : "바뀐 태그가 없습니다 — 사전에 없는 이름은 그대로입니다.");
      await load();
    } catch (error) {
      notifyError((error as Error).message);
    }
  }

  async function addBlank() {
    try {
      const made = await api.createExperience({ person: name, title: "새 경험", kind: "업무" });
      window.location.hash = experienceLink(made.id);
    } catch (error) {
      notifyError((error as Error).message);
    }
  }

  const missing = retroProjects.filter((pid) => !data?.items.some((item) => item.project === pid));
  return (
    <div className="card person-experiences" data-testid="experience-card">
      <div className="card-head">
        <IconTitle icon={Award}>경험 {data?.total ?? 0}건</IconTitle>
        {!manager && canExport && (
          <div className="person-tools">
            <a className="button-link" href={experienceExportLink(name)}>업무 이력 파일</a>
          </div>
        )}
        {manager && (
          <div className="person-tools">
            <a className="button-link" href={experienceExportLink(name)}
              title="확정한 경험을 .md 파일 하나로 — 팀원 본인에게 건네는 업무 이력">업무 이력 파일</a>
            <button onClick={() => { window.location.hash = experienceImportLink(name); }}
              title="고른 과제의 기록으로 경험 정리 프롬프트를 만들고, 사내 AI 의 응답을 붙여 넣어 경험으로 저장합니다">
              AI 로 정리
            </button>
            <button className="ghost" onClick={() => void addBlank()}>+ 새 경험</button>
            <button className="ghost" disabled={busy || missing.length === 0} onClick={() => void draftAll()}
              title="회고가 있는 맡은 과제마다 초안 하나 — 이미 경험이 있는 과제는 건너뜁니다">
              {busy ? "만드는 중…" : `회고 있는 과제 모두 초안${missing.length ? ` (${missing.length})` : ""}`}
            </button>
          </div>
        )}
      </div>
      <CardIntro id="experiences">
        과제 하나에서 나온 <b>상황 · 목표 · 행동 · 결과 · 교훈</b> 한 묶음입니다. 담당과 역할 · 회고 · 과제 개요 · 효과 금액에서 <b>초안</b>을 만들고,
        <b>[AI 로 정리]</b>에서 사내 AI 의 응답을 붙여 넣으면 <b>구조화</b>가 됩니다. 확정은 다음 단계에서 붙습니다. 통합 검색 · 과제 내보내기에는 들어가지 않습니다.
      </CardIntro>
      {notice && <p className="hint notice">{notice}</p>}
      {data && data.total > 0 && (
        <p className="muted experience-counts">
          확정 {data.counts["확정"] ?? 0} · 구조화 {data.counts["구조화"] ?? 0} · 초안 {data.counts["초안"] ?? 0}
        </p>
      )}
      {/* 역량 칩 (TODO 260 · 4단계.md ⑩) — 축별 · 경험 수. 사전에 없는 태그는 점선 */}
      {data && (data.skills?.length ?? 0) > 0 && (
        <div className="experience-skills" data-testid="experience-skills">
          {AXES.map((axis) => {
            const chips = data.skills.filter((skill) => skill.axis === axis);
            return chips.length === 0 ? null : (
              <div key={axis} className="exp-skill-axis">
                <span className="exp-label">{axis}</span>
                {chips.map((skill) => (
                  <span key={skill.name} className={skill.known ? "exp-chip" : "exp-chip unknown"} title={skill.known ? "" : "역량 사전에 없음"}>
                    {skill.name} <b>{skill.count}</b>
                  </span>
                ))}
              </div>
            );
          })}
          {manager && data.skills.some((skill) => !skill.known) && (
            <button className="link-button" onClick={() => void rematch()} title="역량 사전을 고친 뒤 — 이 사람 경험의 태그를 지금 사전으로 다시 맞춥니다">
              사전에 다시 맞추기
            </button>
          )}
        </div>
      )}
      {!data ? (
        <p className="muted">불러오는 중…</p>
      ) : data.total === 0 ? (
        <p className="muted">아직 경험이 없습니다.{manager && missing.length > 0 ? " 위의 [회고 있는 과제 모두 초안] 으로 시작하세요." : ""}</p>
      ) : (
        <div className="table-scroll">
          <table className="grid experience-table">
            <thead>
              <tr>
                <th>번호</th>
                <th>제목</th>
                <th>기간</th>
                <th>과제</th>
                <th>상태</th>
                <th title="확인 필요 — 답하거나 지울 질문">질문</th>
                <th title="검사 경고(기간 · 정량 기준 등)">경고</th>
                <th>고친 날</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((item) => (
                <tr key={item.id} data-experience={item.id}>
                  <td className="project-id">{item.id}</td>
                  <td><a href={experienceLink(item.id)}>{item.title}</a></td>
                  <td className="muted one-line">{item.start || "?"} ~ {item.end || (item.start ? "진행 중" : "?")}</td>
                  <td className="muted">
                    {item.project ? (item.project_gone ? <span title="지운 과제 — 경험은 남습니다">{item.project} (지운 과제)</span> : item.project) : "—"}
                  </td>
                  <td><span className={`exp-status exp-${item.status}`}>{item.status}</span></td>
                  <td className={item.open_count ? "num" : "zero num"}>{item.open_count || "-"}</td>
                  <td className={item.warn_count ? "num" : "zero num"}>{item.warn_count || "-"}</td>
                  <td className="muted">{item.updated_at.slice(5, 10)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
