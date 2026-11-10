import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { backTarget, useAddressBar } from "../nav";
import type { Health, Meta } from "../types";
import { formatBytes } from "../upload";
import { isAdmin } from "../me";
import { useEditedUnsaved } from "../util";
import AiPromptCard from "./AiPromptCard";
import ReportTemplateCard from "./ReportTemplateCard";
import IntakeSettingsCard from "./IntakeSettingsCard";
import MeetingSettingsCard from "./MeetingSettingsCard";
import SkillDictionaryCard from "./SkillDictionaryCard";
import SkillCleanupCard from "./SkillCleanupCard";
import BackupDownloadCard from "./BackupDownloadCard";
import EntryTemplateCard from "./EntryTemplateCard";
import TrashCard from "./TrashCard";
import PeopleCard from "./PeopleCard";
import ProjectCodeCard from "./ProjectCodeCard";
import ProjectTypeCard from "./ProjectTypeCard";
import ReportDayCard from "./ReportDayCard";
import ErrorLogCard from "./ErrorLogCard";
import LinkFixCard from "./LinkFixCard";
import PasteCheckCard from "./PasteCheckCard";
import VersionsCard from "./VersionsCard";
import BackupCard from "./BackupCard";
import RestoreCard from "./RestoreCard";
import LoadError from "./LoadError";
import EffectConfirmCard from "./EffectConfirmCard";
import { enterToSave } from "./enterSave";
import CardIntro from "./CardIntro";
import ViewTabs from "./ViewTabs";
import { LIMITS, hasControlChars, lengthState } from "../inputRules";
import { FolderOpen, Gauge, Server, UserPen } from "lucide-react";
import IconTitle from "./IconTitle";

/** 설정 묶음 (TODO 249 ⑤) — "" = 기본. title 은 탭 아래 한 줄 설명이기도 하다 */
type SettingsTab = "" | "class" | "report" | "forms" | "backup" | "check";
const SETTINGS_TABS: { key: SettingsTab; label: string; title: string }[] = [
  { key: "", label: "기본", title: "누가 쓰는가 · 과제를 무엇으로 가르는가 — 작성자 · 담당자 명부 · 면담 · 과제 속성 · 번호 체계 · 효과 금액" },
  { key: "class", label: "분류 · 접수", title: "스마트과제의 성격 · 분류 · 수행 방식 · 비용구분 목록 · 접수 서식 · 묵힘 기준 · 사전점검 · 역량 사전" },
  { key: "report", label: "보고", title: "언제 보고하는가 · 무엇을 후보로 올리는가" },
  { key: "forms", label: "서식", title: "새 문서를 무엇으로 시작하는가 — 진행일지 · 보고 초안 · AI 프롬프트" },
  { key: "backup", label: "보관과 백업", title: "어디에 쌓이는가 · 잘못됐을 때 어디서 되찾는가" },
  { key: "check", label: "점검", title: "뭔가 안 됐을 때 볼 자리 — 실행 중인 배포본 · 최근 오류 · 첨부 링크 · 붙여넣기" },
];
function tabFrom(params: URLSearchParams): SettingsTab {
  const value = params.get("tab") ?? "";
  return SETTINGS_TABS.some((item) => item.key === value) ? (value as SettingsTab) : "";
}

/**
 * 도구 설정.
 * 지금은 팀장 한 명이 쓰므로 작성자를 여기서 한 번 정해 두고 쓴다.
 * 나중에 로그인이 생기면 이 값 대신 로그인한 사용자가 작성자가 된다.
 */
export default function Settings({ meta, onSaved, back, query = "" }: { meta: Meta; onSaved: () => void; back?: string | null; query?: string }) {
  const [tab, setTab] = useState<SettingsTab>(() => tabFrom(new URLSearchParams(query)));
  useAddressBar(
    "settings",
    Object.fromEntries(Object.entries({ tab, back: back ?? "" }).filter(([, value]) => value)) as Record<string, string>,
    (params) => setTab(tabFrom(params)),
  );
  const [author, setAuthor] = useState("");
  // null = 아직 못 불러옴 — 그동안은 "고쳤다" 로 보지 않는다 (TODO 211 ②)
  const [savedAuthor, setSavedAuthor] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // 설정 파일에서 읽지 못해 기본값을 쓰는 값 (TODO 163)
  const [unreadable, setUnreadable] = useState<string[]>([]);
  // 명부의 팀장 (TODO 235) — 있으면 작성자는 이 이름을 따라간다
  const [leader, setLeader] = useState("");
  const [loadError, setLoadError] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .settings()
      .then((settings) => {
        setAuthor(settings.author);
        setSavedAuthor(settings.author);
        setLeader(settings.leader ?? "");
        setUnreadable(settings.unreadable ?? []);
        setLoadError(null);
      })
      .catch((err: Error) => setLoadError(err.message));
  }, []);
  useEffect(load, [load]);
  // 작성자를 고치다 메뉴를 누르면 묻는다 (TODO 211 ②)
  useEditedUnsaved("settings:author", author.trim(), savedAuthor, busy);

  // 점검 (TODO 204 · 206) — 첨부 전체 용량 · 이전 버전을 남기지 못한 문서. 못 받으면 그 줄만 뺀다
  const [health, setHealth] = useState<Health | null>(null);
  useEffect(() => {
    let alive = true;
    api
      .health()
      .then((next) => alive && setHealth(next))
      .catch(() => alive && setHealth(null));
    return () => {
      alive = false;
    };
  }, []);
  const keepFailures = Array.isArray(health?.version_keep_failures) ? health.version_keep_failures : [];

  // 작성자 — 한 줄 · 40자 (TODO 214 F13 · U6). 서버가 같은 규칙으로 다듬는다
  const authorLength = lengthState(author.trim(), LIMITS.name);
  const authorProblem = hasControlChars(author)
    ? "작성자는 한 줄로 적어 주세요."
    : authorLength.over
      ? `작성자는 ${LIMITS.name}자까지입니다.`
      : null;
  const canSaveAuthor = !busy && !authorProblem && author.trim() !== (savedAuthor ?? "");

  async function save() {
    if (!canSaveAuthor) return;
    setBusy(true);
    setError(null);
    try {
      const saved = await api.saveSettings({ author: author.trim() });
      setSavedAuthor(saved.author);
      setNotice("저장했습니다.");
      window.setTimeout(() => setNotice(null), 3000);
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="settings">
      {/* 온 곳으로 돌아간다 (TODO 127). **온 곳이 있을 때만** — 메뉴로 들어오면 그리지 않는다(128 의
          규칙). 예전에는 늘 그려서, 온 곳이 없으면 기본값 "← 과제 목록" 이 섰다 (TODO 153). */}
      {back && (
        <a className="back" href={backTarget(back).href}>
          ← {backTarget(back).label}
        </a>
      )}
      <div className="page-head">
        <h1>설정</h1>
        <p className="hint page-desc">작성자·담당자 명부·과제 속성과 분류·보고 요일·서식·백업과 보관·점검을 정합니다.</p>
      </div>
      {loadError && <LoadError message={loadError} onRetry={load} />}
      {unreadable.length > 0 && (
        <p className="warn-banner">
          {unreadable.includes("*")
            ? "설정 파일(settings.json)을 읽지 못해 모든 설정을 기본값으로 쓰고 있습니다."
            : `설정 파일(settings.json)의 ${unreadable.join(" · ")} 값을 읽지 못해 기본값을 쓰고 있습니다.`}{" "}
          여기서 한 번 저장하면 파일이 바로잡힙니다.
        </p>
      )}

      {/*
        설정은 기능이 늘 때마다 카드가 하나씩 붙어 스물이 넘었다. **하는 일이 같은 것끼리 묶고(97), 한 번에 한 묶음만** 보인다
        (TODO 249 ⑤ — 한 화면에 5,800px 를 늘어놓아 카드 높이가 제각각인 것이 그대로 보였다). 주소에 묶음이 남아
        도움말 · 홈의 안내가 그 묶음으로 바로 간다.
        묶음 안에서는 **두 크기** — 짧은 카드는 두 칸 격자에 짝지어 높이를 맞추고, 넓은 카드(명부 · 분류·접수 · 프롬프트 ·
        붙여넣기 점검)는 가로 전체 (styles.css .settings-grid · .settings-wide).
      */}
      <ViewTabs label="설정 묶음" className="settings-tabs" value={tab} onChange={(key) => setTab(key as SettingsTab)} tabs={SETTINGS_TABS} />
      <div className="settings-group" role="tabpanel">
        <p className="hint settings-group-desc">{SETTINGS_TABS.find((item) => item.key === tab)?.title}</p>

      {tab === "" && (
        <div className="settings-grid">
          <div className="card author-card settings-wide" onKeyDown={enterToSave(() => void save(), canSaveAuthor)}>
            <IconTitle icon={UserPen}>작성자</IconTitle>
            <CardIntro id="author">
              진행일지와 보고 문서에 <strong>누가 작성했는지</strong>를 함께 남깁니다. 이 PC(서버 PC)에서 쓴 기록에 붙는 이름입니다.
              팀원 PC 에서 쓴 기록에는 그 팀원의 이름이 붙습니다.
            </CardIntro>
            {leader ? (
              // 명부에서 팀장을 골랐다 (TODO 235) — 이름이 한 곳에만 있게 칸을 세우지 않는다
              <p className="leader-author">
                팀장 <b>{leader}</b> <span className="tag leader-tag">팀장</span>
                <span className="hint"> — 아래 명부의 [팀장] 을 따라갑니다. 바꾸려면 명부에서 동그라미를 옮기세요.</span>
              </p>
            ) : (
            <>
            <p className="hint">아래 명부에서 <b>팀장</b>을 고르면 그 이름을 따라가고 이 칸은 사라집니다.</p>
            <div className="form-row">
              <label className="grow">
                이름
                <input
                  list="owner-options"
                  value={author}
                  onChange={(event) => setAuthor(event.target.value)}
                  placeholder="예: 권경락"
                  aria-invalid={authorProblem ? true : undefined}
                />
                {authorProblem ? (
                  <span className="field-error">{authorProblem}</span>
                ) : (
                  <span className="hint length-count">
                    한 줄 · {LIMITS.name}자까지 ({authorLength.left}자 남음)
                  </span>
                )}
                <datalist id="owner-options">
                  {meta.owners.map((name) => (
                    <option key={name} value={name} />
                  ))}
                </datalist>
              </label>
            </div>
            {savedAuthor === "" && (
              <p className="hint warn-text">
                아직 작성자가 정해지지 않았습니다. 지금 정해 두면 앞으로 쓰는 기록에 작성자가 남습니다.
                (이미 쓴 기록에는 소급 적용되지 않습니다)
              </p>
            )}
            {notice && <p className="hint notice">{notice}</p>}
            {error && <p className="form-error">{error}</p>}
            <div className="form-actions">
              <button disabled={!canSaveAuthor} onClick={() => void save()}>
                {busy ? "저장 중…" : "저장"}
              </button>
            </div>
            </>
            )}
          </div>

          <PeopleCard onChanged={() => { onSaved(); load(); }} />
          {/* 팀원 면담의 구분 · 주기 (TODO 182) · 과제 속성 — 키가 비슷한 둘을 한 줄에 */}
          <MeetingSettingsCard meta={meta} onSaved={onSaved} />
          <ProjectTypeCard onSaved={onSaved} />
          <ProjectCodeCard onSaved={onSaved} />
          {/* 효과 금액 단위 확인 기준 (TODO 214 D4) — 과제 번호 곁에 */}
          <EffectConfirmCard meta={meta} onSaved={onSaved} />
        </div>
      )}

      {/* 과제 분류 넷 · 접수 (TODO 136) — 카드 하나, 안에서 두 단 */}
      {tab === "class" && (
        <div className="settings-grid">
          <IntakeSettingsCard meta={meta} onSaved={onSaved} />
          {/* 역량 사전 (TODO 260) — 경험의 역량 태그를 맞추는 표 */}
          <SkillDictionaryCard />
          {/* 역량 태그 정리함 (TODO 262) — 사전에 없는 태그를 모아 한 번에 */}
          <SkillCleanupCard />
        </div>
      )}

      {tab === "report" && (
        <div className="settings-grid">
          <ReportDayCard onSaved={onSaved} />
          <div className="card">
            <IconTitle icon={Gauge}>보고 기준</IconTitle>
            <p className="hint">
              보고 대상 후보의 점수를 계산할 때 쓰는 기준 주기는 <strong>{meta.report_cycle_days}일</strong>입니다.
            </p>
          </div>
        </div>
      )}

      {tab === "forms" && (
        <div className="settings-grid">
          <EntryTemplateCard meta={meta} />
          <ReportTemplateCard />
          <AiPromptCard />
        </div>
      )}

      {tab === "backup" && (
        <div className="settings-grid">
          {!isAdmin() && (
            // 팀장 PC (TODO 247) — 서버 운영 칸은 서버 PC 에만 선다
            <div className="card admin-only-note" data-admin-note>
              <IconTitle icon={Server}>서버 운영은 서버 PC 에서</IconTitle>
              <p className="hint">
                지금은 <b>팀장 PC</b> 로 열었습니다. <b>데이터 위치 · 자동 백업 폴더 · 백업에서 되살리기 · 팀장 지정과 팀장 PC 주소</b>는
                서버를 맡은 쪽(서버 PC 에서 연 화면 — 관리자)이 합니다. 전체 백업 내려받기 · 이전 버전 · 삭제 보관함은 여기서도 됩니다.
              </p>
            </div>
          )}
          {isAdmin() && (
          <div className="card">
            <IconTitle icon={FolderOpen}>데이터 위치</IconTitle>
            <CardIntro id="vault">
              모든 내용은 아래 폴더에 마크다운 파일과 첨부 파일로 저장됩니다. 폴더째 복사하면 그대로 백업입니다.
            </CardIntro>
            <code className="vault-box">{meta.vault}</code>
          </div>
          )}

          {/* 전체 백업 — 만들기 진행 · 받기 (TODO 266). 첨부가 GB 단위면 문서만 먼저(202 · 197 ③) */}
          <BackupDownloadCard />

          {/* 키가 비슷한 것끼리 한 줄 — 자동 백업 · 이전 버전 / 되살리기 · 삭제 보관함 */}
          {isAdmin() && <BackupCard />}
          <VersionsCard />
          {isAdmin() && <RestoreCard />}
          <TrashCard />
        </div>
      )}

      {tab === "check" && (
        <>
        {/* 지금 무엇이 돌고 있는가 (TODO 117). "덮어썼는데 새 기능이 없다" 를 여기서 가른다. */}
        <p className="hint build-line" data-testid="build-line">
          {meta.build ? (
            <>
              지금 실행 중인 배포본 <b>{meta.build.name}</b>
              {meta.build.source && <span className="muted"> · 소스 {meta.build.source}</span>}
              {meta.build.built && <span className="muted"> · 만든 날 {meta.build.built}</span>}
            </>
          ) : (
            <>저장소에서 바로 실행 중입니다 (배포본 아님).</>
          )}
          {" "}새 배포본을 덮어쓴 뒤에도 이 이름이 그대로면 도구를 껐다 켜고 브라우저를 Ctrl+F5 로 새로고침하세요.
        </p>
        {/* 읽기 전용 공유 (TODO 192) — 켜져 있으면 주소와 오늘 접속 수, 아니면 켜는 법 */}
        <p className="hint share-line" data-testid="share-line">
          {meta.share ? (
            <>
              <b>팀원에게 공유 중</b> — 주소 <code>{meta.share.url}</code> · 오늘 접속 {meta.share.visitors}명 · 요청 {meta.share.requests}건.
              팀원은 읽기만 할 수 있고, 이 PC 의 브라우저는 그대로 씁니다. 접속 기록은 데이터 폴더의 <code>.logs/access-날짜.jsonl</code> 에
              주소 · 시각 · 끝점만 남습니다.
            </>
          ) : !isAdmin() ? (
            <>팀장 PC 로 접속 중입니다 — 공유 주소 · 오늘 접속 수는 서버 PC 의 이 자리에 보입니다.</>
          ) : (
            <>팀원에게 읽기 전용으로 보여 주려면 <code>run.bat --share</code> 로 켜세요 (도움말 → "팀원에게 보여 주려면?").</>
          )}
        </p>
        {/* 첨부 전체 용량 · 이전 버전 보관 실패 (TODO 204 · 206 ㉕) — 서버가 알려 줄 때만 선다 */}
        {health && typeof health.attachments_total_bytes === "number" && (
          <p className="hint health-line" data-testid="health-attachments">
            첨부 전체 <b>{formatBytes(health.attachments_total_bytes)}</b>
            {typeof health.attachments_count === "number" && <> · {health.attachments_count.toLocaleString("ko-KR")}개</>}
            {" "}— 데이터 폴더의 첨부를 모두 더한 크기입니다. 백업 zip 이 커지면 [첨부 빼고 내려받기] 나 자동 백업의 "첨부 빼기" 를 쓰세요.
          </p>
        )}
        {/* 큰 작업 파일 자리 (TODO 267) — 데이터 폴더 드라이브. 백업 · 되살리기가 여기 쓴다 */}
        {health?.workspace && (
          <p className="hint health-line" data-testid="health-workspace">
            작업 파일 자리 <code>{health.workspace.work_dir}</code>
            {health.workspace.free_bytes !== null && <> · 남은 자리 <b>{formatBytes(health.workspace.free_bytes)}</b></>}
            {" "}— 백업 zip 을 만들고 되살리기 zip 을 받는 곳입니다(데이터 폴더와 같은 드라이브).
          </p>
        )}
        {keepFailures.length > 0 && (
          <div className="warn-banner keep-failures" data-testid="keep-failures">
            <b>이전 버전을 남기지 못한 문서 {keepFailures.length}건</b> — 저장은 됐지만 되돌릴 보관본이 없습니다.
            경로가 너무 길면(윈도우 260자) 생깁니다. 과제 폴더 이름을 줄이면 다음 저장부터 남습니다.
            <ul>
              {keepFailures.slice(0, 5).map((item, index) => (
                <li key={`${item.path}-${index}`}>
                  <code>{item.path}</code> <span className="muted">— {item.reason}</span>
                </li>
              ))}
            </ul>
            {keepFailures.length > 5 && <span className="muted">외 {keepFailures.length - 5}건</span>}
          </div>
        )}
        <div className="settings-grid">
          <ErrorLogCard />
          <LinkFixCard />
          <PasteCheckCard />
        </div>
        </>
      )}
      </div>
    </section>
  );
}
