import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { backTarget } from "../nav";
import type { Meta } from "../types";
import AiPromptCard from "./AiPromptCard";
import ReportTemplateCard from "./ReportTemplateCard";
import IntakeSettingsCard from "./IntakeSettingsCard";
import MeetingSettingsCard from "./MeetingSettingsCard";
import EntryTemplateCard from "./EntryTemplateCard";
import TrashCard from "./TrashCard";
import PeopleCard from "./PeopleCard";
import ProjectCodeCard from "./ProjectCodeCard";
import ProjectTypeCard from "./ProjectTypeCard";
import ReportDayCard from "./ReportDayCard";
import ErrorLogCard from "./ErrorLogCard";
import LinkFixCard from "./LinkFixCard";
import VersionsCard from "./VersionsCard";
import BackupCard from "./BackupCard";
import LoadError from "./LoadError";

/**
 * 도구 설정.
 * 지금은 팀장 한 명이 쓰므로 작성자를 여기서 한 번 정해 두고 쓴다.
 * 나중에 로그인이 생기면 이 값 대신 로그인한 사용자가 작성자가 된다.
 */
export default function Settings({ meta, onSaved, back }: { meta: Meta; onSaved: () => void; back?: string | null }) {
  const [author, setAuthor] = useState("");
  const [savedAuthor, setSavedAuthor] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // 설정 파일에서 읽지 못해 기본값을 쓰는 값 (TODO 163)
  const [unreadable, setUnreadable] = useState<string[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .settings()
      .then((settings) => {
        setAuthor(settings.author);
        setSavedAuthor(settings.author);
        setUnreadable(settings.unreadable ?? []);
        setLoadError(null);
      })
      .catch((err: Error) => setLoadError(err.message));
  }, []);
  useEffect(load, [load]);

  async function save() {
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
        설정은 기능이 늘 때마다 카드가 하나씩 붙어 열넷이 되었고, 한 칸에 죽 늘어놓으니
        무엇이 어디 있는지 눈으로 찾아야 했다. **하는 일이 같은 것끼리 묶는다** —
        백업은 백업끼리, 서식은 서식끼리. 묶음 안에서는 지금처럼 넓은 화면이면 두 칸으로
        흐른다 (styles.css .settings-grid).
      */}
      <div className="settings-group">
        <h2 className="settings-group-title">
          기본
          <span className="hint">누가 쓰는가 · 과제를 무엇으로 가르는가</span>
        </h2>
        <div className="settings-grid">
          <div className="card">
            <h2>작성자</h2>
            <p className="hint">
              진행일지와 보고 문서에 <strong>누가 작성했는지</strong>를 함께 남깁니다. 여기서 정한 이름이 쓰입니다.
              <br />
              나중에 여러 명이 함께 쓰게 되면, 이 설정 대신 로그인한 사용자가 작성자가 됩니다.
            </p>
            <div className="form-row">
              <label className="grow">
                이름
                <input
                  list="owner-options"
                  value={author}
                  onChange={(event) => setAuthor(event.target.value)}
                  placeholder="예: 권경락"
                />
                <datalist id="owner-options">
                  {meta.owners.map((name) => (
                    <option key={name} value={name} />
                  ))}
                </datalist>
              </label>
            </div>
            {!savedAuthor && (
              <p className="hint warn-text">
                아직 작성자가 정해지지 않았습니다. 지금 정해 두면 앞으로 쓰는 기록에 작성자가 남습니다.
                (이미 쓴 기록에는 소급 적용되지 않습니다)
              </p>
            )}
            {notice && <p className="hint notice">{notice}</p>}
            {error && <p className="form-error">{error}</p>}
            <div className="form-actions">
              <button disabled={busy || author.trim() === savedAuthor} onClick={() => void save()}>
                {busy ? "저장 중…" : "저장"}
              </button>
            </div>
          </div>

          <PeopleCard onChanged={onSaved} />
          {/* 팀원 면담의 구분 · 주기 (TODO 182) — 명부 곁에 */}
          <MeetingSettingsCard meta={meta} onSaved={onSaved} />
          <ProjectTypeCard onSaved={onSaved} />
          <ProjectCodeCard onSaved={onSaved} />
        </div>
      </div>

      {/* 과제 분류 넷 · 접수 (TODO 136). 목록은 한 번 정하면 한동안 안 고치므로 접어 둔다. */}
      <details className="settings-group settings-fold">
        <summary className="settings-group-title">
          과제 분류 · 접수
          <span className="hint">스마트과제의 성격·분류·수행 방식·비용구분 목록 · 접수 서식 · 묵힘 기준</span>
        </summary>
        <div className="settings-grid">
          <IntakeSettingsCard meta={meta} onSaved={onSaved} />
        </div>
      </details>

      <div className="settings-group">
        <h2 className="settings-group-title">
          보고
          <span className="hint">언제 보고하는가 · 무엇을 후보로 올리는가</span>
        </h2>
        <div className="settings-grid">
          <ReportDayCard onSaved={onSaved} />
          <div className="card">
            <h2>보고 기준</h2>
            <p className="hint">
              보고 대상 후보의 점수를 계산할 때 쓰는 기준 주기는 <strong>{meta.report_cycle_days}일</strong>입니다.
            </p>
          </div>
        </div>
      </div>

      {/* 서식 셋은 키가 크고 **매일 여는 칸이 아니다.** 접어 두면 설정 화면의 세로가
          세 카드분 짧아진다 (TODO 120). 한 번 정하면 한동안 안 고치는 값들이다. */}
      <details className="settings-group settings-fold">
        <summary className="settings-group-title">
          서식
          <span className="hint">새 문서를 무엇으로 시작하는가 — 진행일지 · 보고 초안 · AI 프롬프트</span>
        </summary>
        <div className="settings-grid">
          <EntryTemplateCard meta={meta} />
          <ReportTemplateCard />
          <AiPromptCard />
        </div>
      </details>

      <div className="settings-group">
        <h2 className="settings-group-title">
          보관과 백업
          <span className="hint">어디에 쌓이는가 · 잘못됐을 때 어디서 되찾는가</span>
        </h2>
        <div className="settings-grid">
          <div className="card">
            <h2>데이터 위치</h2>
            <p className="hint">
              모든 내용은 아래 폴더에 마크다운 파일과 첨부 파일로 저장됩니다. 폴더째 복사하면 그대로 백업입니다.
            </p>
            <code className="vault-box">{meta.vault}</code>
          </div>

          <div className="card">
            <h2>전체 백업</h2>
            <p className="hint">
              모든 과제의 문서와 첨부를 zip 하나로 내려받습니다. 검색 색인처럼 다시 만들 수 있는 것은 빼고
              원본만 담습니다.
            </p>
            <div className="form-actions">
              <a className="button-like primary-link" href="/api/backup">
                전체 백업 내려받기
              </a>
            </div>
          </div>

          <BackupCard />
          <VersionsCard />
          <TrashCard />
        </div>
      </div>

      <div className="settings-group">
        <h2 className="settings-group-title">
          점검
          <span className="hint">뭔가 안 됐을 때 볼 자리</span>
        </h2>
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
        <div className="settings-grid">
          <ErrorLogCard />
          <LinkFixCard />
        </div>
      </div>
    </section>
  );
}
