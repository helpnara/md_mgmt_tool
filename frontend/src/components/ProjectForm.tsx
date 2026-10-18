import { useEffect, useState } from "react";
import { api, projectTitleCheck } from "../api";
import type { ClassificationInfo, ClassificationKey, Meta, Partner, Project } from "../types";
import TagSuggestions from "./TagSuggestions";
import UnknownOwners from "./UnknownOwners";
import { useFormUnsaved } from "../unsaved";
import { confirmDiscard, dateOrderProblem } from "../util";
import {
  DATE_MAX,
  DATE_MIN,
  LIMITS,
  checkPeople,
  confirmEffects,
  confirmOutsiders,
  confirmPeople,
  dateProblem as dayProblem,
  hasControlChars,
  idYear,
  isDeparted,
  lengthHint,
  lengthState,
  similarTeam,
  splitNames,
  titleProblem,
  today,
} from "../inputRules";

/**
 * 같은 이름 과제를 저장 **전에** 묻는다 (TODO 214 D11) — 새 과제 · 제목 수정 · 승격 · [이 과제로 새 과제].
 * 계속 저장해도 되면 true. 서버에 묻지 못하면(아직 그 길이 없거나 끊김) 묻지 않고 true.
 */
export async function confirmSameTitle(title: string, exclude?: string | null): Promise<boolean> {
  const same = await projectTitleCheck(title.trim(), exclude);
  if (same.length === 0) return true;
  const shown = same.slice(0, 5).map((row) => `${row.id} · ${row.title}`);
  const more = same.length > shown.length ? ` 외 ${same.length - shown.length}건` : "";
  return window.confirm(`같은 이름의 과제가 이미 있습니다: ${shown.join(", ")}${more}\n\n그래도 저장할까요?`);
}

/** 유관부서 담당자 칸의 이름들 — 서버처럼 쉼표 · 세미콜론 · 줄바꿈으로 나눈다 */
const partnerNames = (value: string) => splitNames(value.replace(/[;\n]/g, ","));

interface Props {
  meta: Meta;
  /** 명부에 사람을 새로 넣었을 때 상단 meta 를 다시 읽는다 */
  onMetaChange?: () => void;
  initial?: Partial<Project>;
  submitLabel: string;
  onSubmit: (payload: Partial<Project>) => Promise<void>;
  onCancel: () => void;
}

export default function ProjectForm({ meta, initial, submitLabel, onSubmit, onCancel, onMetaChange = () => undefined }: Props) {
  // 자동완성은 명부를 먼저 보여 주고, 명부에 없지만 이미 쓰이는 이름을 뒤에 붙인다.
  // 떠난 사람은 고르는 자리에서 뺀다 (TODO 122) — 새 과제에 실수로 들어가는 것을 막는다.
  // 이미 그 사람이 담당인 과제를 고칠 때는 값이 그대로 있으므로 사라지지 않는다.
  // 떠난 날이 아직 오지 않았으면 아직 있는 사람이다 (TODO 214 D8)
  const left = new Set((meta.people_left ?? []).filter(isDeparted).map((person) => person.name));
  const ownerOptions = [
    ...meta.people.filter((name) => !left.has(name)),
    ...meta.owners.filter((name) => !meta.people.includes(name) && !left.has(name)),
  ];
  // 선행 과제 고르기 (TODO 172) — 번호와 이름을 함께 보여 고른다. 자기 자신은 뺀다.
  // 폼을 열 때마다 전체 과제를 받지 않는다 — 창마다 한 번 받은 번호 · 제목을 쓴다 (TODO 212, api.projectOptions)
  const [projectOptions, setProjectOptions] = useState<{ id: string; title: string }[]>([]);
  // 목록을 받았는가 — 받기 전 · 못 받았을 때는 번호를 검사하지 않는다(서버가 마지막에 본다) (TODO 214 D15)
  const [optionsLoaded, setOptionsLoaded] = useState(false);
  useEffect(() => {
    let alive = true;
    api
      .projectOptions()
      .then((rows) => {
        if (!alive) return;
        setProjectOptions(rows.filter((row) => row.id !== initial?.id));
        setOptionsLoaded(true);
      })
      .catch(() => alive && setProjectOptions([]));
    return () => {
      alive = false;
    };
  }, [initial?.id]);
  // 선행 과제 — 여럿일 수 있다(앞 단계 과제 둘을 이어받는 과제). 칩으로 넣고 뺀다 (TODO 172)
  const [predecessors, setPredecessors] = useState<string[]>(initial?.predecessors ?? []);
  const [predecessorInput, setPredecessorInput] = useState("");
  const addPredecessor = (raw: string) => {
    const id = raw.trim().split(/\s+/)[0];
    if (!id) return;
    setPredecessors((prev) => (prev.includes(id) ? prev : [...prev, id]));
    setPredecessorInput("");
  };
  const [form, setForm] = useState({
    title: initial?.title ?? "",
    status: initial?.status ?? "in_progress",
    type: initial?.type ?? "",
    group: initial?.group ?? "",
    owners: (initial?.owners ?? []).join(", "),
    start_date: initial?.start_date ?? "",
    due_date: initial?.due_date ?? "",
    completed_at: initial?.completed_at ?? "",
    effect_expected: initial?.effect_expected?.toString() ?? "",
    effect_verified: initial?.effect_verified?.toString() ?? "",
    tags: (initial?.tags ?? []).join(", "),
  });
  /**
   * 유관부서 (TODO 92). 한 줄이 팀 하나이고, 담당자는 그 줄 안에서 쉼표로 적는다.
   *
   * **팀과 사람을 한 칸에 섞어 적게 하지 않는다.** "설비기술팀 김철수" 처럼 한 칸에 두면
   * 어디까지가 팀이고 어디부터가 사람인지 아무도 모른다. 줄을 나누는 편이 입력은
   * 한 번 더지만, 그 뒤로 집계·검색·표시가 전부 흔들리지 않는다.
   */
  const [partners, setPartners] = useState<{ team: string; people: string }[]>(
    () => (initial?.partners ?? []).map((row) => ({ team: row.team, people: row.people.join(", ") })),
  );
  const setPartner = (index: number, key: "team" | "people", value: string) =>
    setPartners((prev) => prev.map((row, i) => (i === index ? { ...row, [key]: value } : row)));

  /**
   * 과제 분류 넷 (TODO 136) — 성격 · 분류 · 수행 방식 · 비용구분.
   * 입력 칸은 **분류를 쓰는 속성(스마트과제)일 때만** 선다. 속성을 바꿔 칸이 숨어도 값은 지우지
   * 않는다 — 실수로 속성을 잠깐 바꿨다가 되돌렸을 때 적어 둔 것이 사라지면 안 된다.
   */
  const [classes, setClasses] = useState<Record<ClassificationKey, string>>(() => ({
    nature: initial?.nature ?? "",
    category: initial?.category ?? "",
    delivery: initial?.delivery ?? "",
    cost_kind: initial?.cost_kind ?? "",
  }));

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /**
   * 저장하면 붙을 과제 번호 (TODO 95).
   *
   * 번호의 연도는 **등록한 날이 아니라 착수년도**다. 그 사실은 문장으로 적어 두는 것보다
   * **실제 번호를 미리 보여 주는 편**이 확실하다 — 지난해 과제를 등록하면서 시작일을
   * 비워 둔 채 저장하면 올해 번호가 붙는데, 저장 뒤에는 알아채기 어렵다.
   * 고칠 때는 띄우지 않는다 — 이미 붙은 번호는 이 폼이 바꾸지 않는다.
   */
  const creating = !initial?.id;
  const [nextId, setNextId] = useState<string | null>(null);
  useEffect(() => {
    if (!creating) return;
    let alive = true;
    api
      .nextProjectId(form.start_date)
      .then((row) => alive && setNextId(row.id))
      .catch(() => alive && setNextId(null));
    return () => {
      alive = false;
    };
  }, [creating, form.start_date]);

  const update = (key: string, value: string) => setForm((prev) => ({ ...prev, [key]: value }));

  // 비우면 null 로 보낸다 — "아직 안 정했다"와 "0원"은 다른 뜻이다.
  const effect = (value: string): number | null => (value.trim() === "" ? null : Number(value));
  // 단순 현황 관리를 과제로 세운 경우. 보고 대상 후보에서만 빠진다 (TODO 80).
  const [noReport, setNoReport] = useState(Boolean(initial?.no_report));
  // 금액으로 재지 않는 과제 (TODO 125). 유지보수·기획보고처럼 효과 금액을 적지 않는 일이
  // "완료했는데 실증효과 미입력" 에 계속 남으면, 줄지 않는 그 숫자를 곧 안 보게 된다.
  const [noEffect, setNoEffect] = useState(Boolean(initial?.no_effect));
  // 쓰다가 떠나면 묻는다 (TODO 162). 유관부서 · 분류 · 적다 만 선행 과제 칸까지 (TODO 211 ①)
  const snapshot = { form, noReport, noEffect, predecessors, predecessorInput, partners, classes };
  useFormUnsaved(`project-form:${initial?.id ?? "new"}`, snapshot, busy);
  const [initialSnapshot] = useState(() => JSON.stringify(snapshot));
  const dirty = JSON.stringify(snapshot) !== initialSnapshot;
  // [취소] · Esc — 고친 것이 있으면 버릴지 묻는다 (TODO 211 ①)
  const cancel = () => {
    if (busy || confirmDiscard(dirty)) onCancel();
  };
  // 시작 > 마감 — 서버 422 전에 화면에서 (TODO 212). 날짜는 2000~2100년만 (TODO 214 D5)
  const startProblem = dayProblem(form.start_date, "시작일");
  const dateProblem =
    dayProblem(form.due_date, "마감일") ?? dateOrderProblem(form.start_date, form.due_date, "시작일", "마감일");
  // 완료일 (TODO 214 D1) — 시작일보다 앞이거나 오늘보다 뒤면 막는다. 비우면 서버가 오늘로 남긴다
  const todayDay = today();
  const completedProblem =
    form.status !== "done"
      ? null
      : (dayProblem(form.completed_at, "완료일") ??
        (form.completed_at && form.completed_at > todayDay
          ? `완료일(${form.completed_at})이 오늘(${todayDay})보다 뒤입니다 — 끝난 날을 적어 주세요.`
          : null) ??
        dateOrderProblem(form.start_date, form.completed_at, "시작일", "완료일"));
  // 제목 · 그룹 (TODO 214 D14 · U6) — 상한 · 줄바꿈 · 제어문자
  const titleError = titleProblem(form.title, "과제명");
  const titleLeft = lengthHint(form.title, LIMITS.title);
  const groupError = hasControlChars(form.group)
    ? "그룹에 줄바꿈 · 탭 같은 제어문자를 쓸 수 없습니다."
    : lengthState(form.group.trim(), LIMITS.group).over
      ? `그룹은 ${LIMITS.group}자까지입니다.`
      : null;
  // 유관부서 — 담당자만 적고 부서를 비운 줄은 예전에 말없이 사라졌다. 막고 알린다 (TODO 214 F8)
  const partnerMissingTeam = partners
    .map((row, index) => (!row.team.trim() && row.people.trim() ? index : -1))
    .filter((index) => index >= 0);
  // 선행 과제 (TODO 214 D15) — 이미 저장돼 있던 번호는 보관함에 갔어도 그대로 둔다(칩에 "찾을 수 없음").
  // **새로 넣는** 번호만 목록과 맞춰 본다.
  const storedPredecessors = initial?.predecessors ?? [];
  const typedPredecessor = predecessorInput.trim().split(/\s+/)[0] ?? "";
  const allPredecessors = [
    ...predecessors,
    ...(typedPredecessor && !predecessors.includes(typedPredecessor) ? [typedPredecessor] : []),
  ];
  const known = (id: string) => projectOptions.some((option) => option.id === id);
  const unknownPredecessors = optionsLoaded
    ? allPredecessors.filter((id) => !storedPredecessors.includes(id) && !known(id))
    : [];
  // 연도가 거꾸로 — 2026 과제가 2027 과제를 앞 단계로 (경고만)
  const ownYear = idYear(initial?.id) ?? (form.start_date ? Number(form.start_date.slice(0, 4)) : Number(todayDay.slice(0, 4)));
  const laterPredecessors = allPredecessors.filter((id) => (idYear(id) ?? 0) > ownYear);
  // 효과 (TODO 214 D2 · D3) — 비대상이면 칸을 잠근다(값은 남는다). 실증만 있거나 완료 전 실증은 알린다
  const verifiedFilled = form.effect_verified.trim() !== "";
  const expectedFilled = form.effect_expected.trim() !== "";
  // 저장을 막는 까닭 — 단추 바로 위에 첫째 것을 (TODO 214 U2 · U5)
  const blockers = [
    titleError,
    groupError,
    startProblem,
    dateProblem,
    completedProblem,
    partnerMissingTeam.length > 0 ? "유관부서 줄에 부서를 적어 주세요." : null,
    unknownPredecessors.length > 0 ? `선행 과제 번호를 확인해 주세요: ${unknownPredecessors.join(", ")}` : null,
  ].filter((item): item is string => Boolean(item));

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (blockers.length > 0 || busy) return;
    setBusy(true);
    setError(null);
    try {
      // 같은 이름 과제 — 만들 때 · 제목을 바꿀 때 (D11)
      const titleChanged = creating || form.title.trim() !== (initial?.title ?? "").trim();
      if (titleChanged && !(await confirmSameTitle(form.title, initial?.id))) return;
      // 명부에 없는 담당자 · 떠난 사람 — 이번에 새로 적은 이름만 묻는다 (D6 · D7)
      const owners = splitNames(form.owners);
      const newOwners = owners.filter((name) => !(initial?.owners ?? []).includes(name));
      const addsPeople = checkPeople(newOwners, meta).unknown.length > 0;
      if (!(await confirmPeople(newOwners, meta, api.addPerson, "담당자"))) return;
      if (addsPeople) onMetaChange();
      const oldPartnerPeople = (initial?.partners ?? []).flatMap((row) => row.people);
      const newPartnerPeople = partners
        .flatMap((row) => partnerNames(row.people))
        .filter((name) => !oldPartnerPeople.includes(name));
      if (
        !(await confirmOutsiders(newPartnerPeople, meta, { role: "유관부서 담당자", known: meta.partner_people ?? [] }))
      )
        return;
      // 단위 실수 — 기준선을 넘는 금액은 한 번 묻는다 (D4). 비대상 과제의 금액은 합계에 안 들어가니 묻지 않는다
      if (
        !noEffect &&
        !confirmEffects(
          [
            { label: "기대효과", value: effect(form.effect_expected) },
            { label: "실증효과", value: effect(form.effect_verified) },
          ],
          meta,
        )
      )
        return;
      await onSubmit({
        title: form.title.trim(),
        status: form.status,
        type: form.type || null,
        group: form.group.trim() || null,
        owners,
        start_date: form.start_date || null,
        due_date: form.due_date || null,
        // 완료 상태가 아니면 완료일을 보내지 않는다 — 서버가 비운다 (TODO 104).
        ...(form.status === "done" ? { completed_at: form.completed_at || null } : {}),
        effect_expected: effect(form.effect_expected),
        effect_verified: effect(form.effect_verified),
        no_report: noReport,
        no_effect: noEffect,
        nature: classes.nature || null,
        category: classes.category || null,
        delivery: classes.delivery || null,
        cost_kind: classes.cost_kind || null,
        // 칸에 적어 두고 [추가] 를 안 눌렀어도 함께 보낸다 — 번호만(서버도 번호만 쓴다). [] 이면 모두 끊는다.
        predecessors: allPredecessors,
        // 팀 이름이 빈 줄은 보내지 않는다(담당자만 적은 줄은 위에서 막았다 — F8). 사람 이름을 나누는 일은 **서버가** 한다 (TODO 74).
        partners: partners
          .filter((row) => row.team.trim())
          .map((row) => ({ team: row.team.trim(), people: row.people })) as unknown as Partner[],
        tags: form.tags
          .split(",")
          .map((tag) => tag.trim())
          .filter(Boolean),
      });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      className="project-form"
      onSubmit={handleSubmit}
      onKeyDown={(event) => {
        // Esc = [취소] (TODO 211 ①). 자동완성 목록이 열려 있으면 브라우저가 먼저 닫는다
        if (event.key === "Escape" && !event.defaultPrevented) {
          event.preventDefault();
          cancel();
        }
      }}
    >
      <label>
        {/* 필수 표시 * (TODO 214 U1) · 남은 글자 (D14 · U6) */}
        과제명 *
        <input
          value={form.title}
          onChange={(event) => update("title", event.target.value)}
          required
          autoFocus
          aria-invalid={titleError ? true : undefined}
        />
        {titleError ? (
          <span className="form-warn">{titleError}</span>
        ) : (
          titleLeft && <span className="hint length-count">{titleLeft}</span>
        )}
      </label>
      <div className="form-row">
        <label>
          상태
          <select value={form.status} onChange={(event) => update("status", event.target.value)}>
            {meta.statuses.map((status) => (
              <option key={status.key} value={status.key}>
                {status.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          속성
          <select value={form.type ?? ""} onChange={(event) => update("type", event.target.value)}>
            <option value="">선택 안 함</option>
            {meta.types.map((type) => (
              <option key={type.key} value={type.key}>
                {type.label}
              </option>
            ))}
          </select>
        </label>
        <div className="label-like predecessor-field">
          <span>선행 과제 (다년도 과제의 앞 단계 — 여럿이면 하나씩 추가)</span>
          <div className="predecessor-chips">
            {predecessors.map((id) => {
              // 목록에 없는 번호 — 저장돼 있던 것은 "찾을 수 없음"(그대로 둔다), 새로 넣은 것은 고칠 것 (D15)
              const missing = optionsLoaded && !known(id);
              const stored = storedPredecessors.includes(id);
              return (
              <span
                key={id}
                className={`chip predecessor-chip${missing ? (stored ? " missing" : " invalid") : ""}`}
                title={
                  missing
                    ? stored
                      ? "삭제 보관함에 있거나 찾을 수 없는 과제입니다 — 이어진 번호는 그대로 둡니다"
                      : "과제 목록에 없는 번호입니다"
                    : undefined
                }
              >
                {id}{" "}
                {missing ? (
                  <span className="muted">{stored ? "찾을 수 없음" : "목록에 없음"}</span>
                ) : (
                  projectOptions.find((option) => option.id === id)?.title ?? ""
                )}
                <button
                  type="button"
                  className="ghost small"
                  aria-label={`${id} 빼기`}
                  onClick={() => setPredecessors((prev) => prev.filter((item) => item !== id))}
                >
                  ×
                </button>
              </span>
              );
            })}
            <input
              list="predecessor-options"
              value={predecessorInput}
              onChange={(event) => {
                const value = event.target.value;
                // 목록에서 고르면 바로 칩으로
                if (projectOptions.some((option) => option.id === value.trim())) addPredecessor(value);
                else setPredecessorInput(value);
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  addPredecessor(predecessorInput);
                }
              }}
              placeholder={predecessors.length ? "더 이을 과제 번호" : "예: 2025-003 — 1단계면 비워 둡니다"}
              aria-label="선행 과제 번호"
            />
            <datalist id="predecessor-options">
              {projectOptions
                .filter((option) => !predecessors.includes(option.id))
                .map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.title}
                  </option>
                ))}
            </datalist>
          </div>
          {unknownPredecessors.length > 0 && (
            <span className="form-warn">
              목록에 없는 과제 번호입니다: {unknownPredecessors.join(", ")} — 목록에서 고르거나 번호를 고쳐 주세요.
            </span>
          )}
          {laterPredecessors.length > 0 && (
            <span className="hint warn-text">
              선행 과제 {laterPredecessors.join(", ")} 의 연도가 이 과제({ownYear})보다 뒤입니다 — 앞뒤가 바뀌지 않았는지 확인해 주세요.
            </span>
          )}
        </div>
        <label>
          그룹 (예 : 회의체, 지시사항 등)
          <input
            list="group-options"
            value={form.group ?? ""}
            onChange={(event) => update("group", event.target.value)}
            placeholder="예: 회의체"
            aria-invalid={groupError ? true : undefined}
          />
          {groupError && <span className="form-warn">{groupError}</span>}
          <datalist id="group-options">
            {meta.groups.map((group) => (
              <option key={group} value={group} />
            ))}
          </datalist>
        </label>
        <label>
          담당자 (여러 명은 쉼표로)
          <input
            list="owner-options"
            value={form.owners}
            onChange={(event) => update("owners", event.target.value)}
            placeholder="예: 권경락, 홍길동"
          />
          <datalist id="owner-options">
            {ownerOptions.map((name) => (
              <option key={name} value={name} />
            ))}
          </datalist>
          <UnknownOwners
            known={meta.people}
            value={form.owners}
            onAdded={onMetaChange}
            departed={[...left]}
          />
        </label>
      </div>
      {/* ── 과제 분류 넷 (TODO 136) ─────────────────────────────────────
          스마트과제일 때만 선다. 다른 속성에 이미 값이 있으면(예전에 적어 둔 것) 그대로 보인다. */}
      {(form.type === meta.classified_type || Object.values(classes).some(Boolean)) && (
        <div className="form-row class-row">
          {meta.classifications.map((info) => (
            <ClassSelect
              key={info.key}
              info={info}
              value={classes[info.key]}
              onChange={(value) => setClasses((prev) => ({ ...prev, [info.key]: value }))}
            />
          ))}
        </div>
      )}
      {creating && form.type === meta.classified_type && (
        <p className="hint intake-hint">
          스마트과제는 <a href="#/intakes">접수</a>에서 승격해 만들 수도 있습니다 — 접수 번호와 인터뷰 기록이 과제에
          함께 이어집니다. 급한 건은 여기서 바로 만들어도 됩니다.
        </p>
      )}
      {/* ── 유관부서 (TODO 92) ────────────────────────────────────────
          두 팀 이상이 함께 하고, 팀마다 담당자가 여럿인 일이 흔하다.
          팀은 줄로, 사람은 그 줄 안에서 쉼표로 나눈다. */}
      <div className="partner-field">
        <div className="partner-head">
          <span>유관부서</span>
          <span className="hint">함께 일하는 팀과 그쪽 담당자입니다. 담당자는 나중에 채워도 됩니다.</span>
        </div>
        {partners.length > 0 && (
          <ul className="partner-rows">
            {partners.map((row, index) => {
              // 비슷한 팀 이름 (D13) — "품질팀" 과 "품질 팀" 이 따로 쌓이지 않게
              const similar = similarTeam(row.team.trim(), meta.partner_teams ?? []);
              const noTeam = partnerMissingTeam.includes(index);
              return (
              <li key={index}>
                <input
                  list="partner-team-options"
                  value={row.team}
                  onChange={(event) => setPartner(index, "team", event.target.value)}
                  placeholder="부서 (예: 설비기술팀)"
                  aria-label={`유관부서 ${index + 1} 부서명`}
                  aria-invalid={noTeam ? true : undefined}
                />
                <input
                  list="partner-person-options"
                  value={row.people}
                  onChange={(event) => setPartner(index, "people", event.target.value)}
                  placeholder="담당자 (여러 명은 쉼표로)"
                  aria-label={`유관부서 ${index + 1} 담당자`}
                />
                <button
                  type="button"
                  className="ghost small danger"
                  onClick={() => setPartners((prev) => prev.filter((_, i) => i !== index))}
                >
                  삭제
                </button>
                {noTeam && <span className="form-warn partner-warn">부서를 적어 주세요 — 담당자만 적은 줄은 저장할 수 없습니다.</span>}
                {similar && <span className="hint warn-text partner-warn">비슷한 팀이 있습니다: {similar}</span>}
              </li>
              );
            })}
          </ul>
        )}
        <button data-write
          type="button"
          className="ghost small"
          onClick={() => setPartners((prev) => [...prev, { team: "", people: "" }])}
        >
          + 부서 추가
        </button>
        <datalist id="partner-team-options">
          {meta.partner_teams?.map((team) => (
            <option key={team} value={team} />
          ))}
        </datalist>
        <datalist id="partner-person-options">
          {meta.partner_people?.filter((name) => !left.has(name)).map((name) => (
            <option key={name} value={name} />
          ))}
        </datalist>
      </div>

      <div className="form-row">
        {/* 날짜 짝 칸의 min · max (TODO 214 U3) — 달력이 고를 수 없는 날을 먼저 흐린다 */}
        <label>
          시작일
          <input
            type="date"
            value={form.start_date ?? ""}
            min={DATE_MIN}
            max={DATE_MAX}
            onChange={(event) => update("start_date", event.target.value)}
            aria-invalid={startProblem ? true : undefined}
          />
          {startProblem && <span className="form-warn date-warn">{startProblem}</span>}
        </label>
        <label>
          마감일
          <input
            type="date"
            value={form.due_date ?? ""}
            min={form.start_date || DATE_MIN}
            max={DATE_MAX}
            onChange={(event) => update("due_date", event.target.value)}
            aria-invalid={dateProblem ? true : undefined}
          />
          {dateProblem && <span className="form-warn date-warn">{dateProblem}</span>}
        </label>
        {/* 완료일 (TODO 104 · 214 D1) — 상태가 완료일 때만 선다. 비워 두면 오늘로 남는다.
            지난 과제를 뒤늦게 넣을 때는 여기서 실제 끝난 날을 적는다. 미래 · 시작일보다 앞은 막는다. */}
        {form.status === "done" && (
          <label>
            완료일
            <input
              type="date"
              value={form.completed_at ?? ""}
              min={form.start_date || DATE_MIN}
              max={todayDay}
              onChange={(event) => update("completed_at", event.target.value)}
              aria-invalid={completedProblem ? true : undefined}
            />
            {completedProblem ? (
              <span className="form-warn date-warn">{completedProblem}</span>
            ) : (
              <span className="hint">비워 두면 오늘 날짜로 남습니다</span>
            )}
          </label>
        )}

        <label>
          태그(예 : 공정, 쉼표 구분)
          <input
            value={form.tags}
            onChange={(event) => update("tags", event.target.value)}
            placeholder="예: 공정, 수명평가"
          />
          <TagSuggestions
            known={meta.tags}
            value={form.tags}
            onPick={(next) => update("tags", next)}
          />
        </label>
      </div>
      {/* 번호의 연도는 등록한 날이 아니라 **착수년도**다 (TODO 95).
          적어 두기보다 붙을 번호를 그대로 보여 주는 편이 확실하다. */}
      {creating && (
        <p className="hint next-id-hint">
          과제 번호는 <b>시작일의 연도</b>로 붙습니다
          {nextId && (
            <>
              {" "}— 지금 저장하면 <b className="next-id">{nextId}</b>
            </>
          )}
          .{!form.start_date && " 시작일을 비워 두면 올해로 붙습니다."}
        </p>
      )}
      {/* 효과 비대상이면 금액 칸을 잠그고 흐린다 — 적어 둔 값은 지우지 않는다 (TODO 214 D2) */}
      <div className={noEffect ? "form-row effect-row effect-locked" : "form-row effect-row"}>
        <label>
          기대효과 (억원/년)
          <input
            type="number"
            step="0.01"
            min="0"
            value={form.effect_expected}
            onChange={(event) => update("effect_expected", event.target.value)}
            placeholder="예: 1.2"
            disabled={noEffect}
            aria-label="기대효과 (억원/년)"
          />
        </label>
        <label>
          실증효과 (억원/년)
          <input
            type="number"
            step="0.01"
            min="0"
            value={form.effect_verified}
            onChange={(event) => update("effect_verified", event.target.value)}
            placeholder="과제가 끝난 뒤 채웁니다"
            disabled={noEffect}
            aria-label="실증효과 (억원/년)"
          />
          {/* 완료로 바꾸는 순간 한 번 묻는다 (TODO 106-C). 막지는 않는다 — 아직 모를 수 있다. */}
          {!noEffect && form.status === "done" && !verifiedFilled && (
            <span className="hint warn-text">
              완료 과제입니다. 실증효과를 적어 두면 홈의 실증 합계에 잡힙니다. (모르면 비워 두어도 됩니다)
            </span>
          )}
          {/* 진행중 과제의 실증효과는 중간 결산으로 홈 합계에 바로 든다 (TODO 217 — 214 D3 를 되돌림) */}
          {!noEffect && verifiedFilled && form.status !== "done" && (
            <span className="hint effect-note">
              중간 결산으로 홈의 실증 합계에 들어갑니다 — 분기 · 반기 결산 때 지금까지 확인된 금액으로 고쳐 적으세요.
            </span>
          )}
          {!noEffect && verifiedFilled && !expectedFilled && (
            <span className="hint warn-text effect-note">기대효과 없이 실증효과만 있습니다 — 기대효과도 적어 주세요.</span>
          )}
        </label>
        {noEffect && (
          <p className="hint effect-locked-note">
            효과성 관리 비대상 — 적어 둔 금액은 그대로 남지만 <b>합계에서 빠집니다</b>.
          </p>
        )}
        <p className="hint effect-hint">
          <b>소수점 둘째 자리까지</b> 적을 수 있습니다 (억원/년 단위라 둘째 자리가 100만 원).
          <br />
          정성적 효과와 산출 근거는 <b>과제 개요</b>에 적습니다.
          근거 자료(엑셀·PPT)는 개요의 [파일 첨부]로 붙일 수 있습니다.
        </p>
      </div>

      <div className="form-row">
        <label className="check-label">
          <input
            type="checkbox"
            checked={noEffect}
            onChange={(event) => setNoEffect(event.target.checked)}
          />
          <span>
            <b>효과성 관리 비대상 과제</b>
            <span className="hint">
              유지보수처럼 <b>금액으로 재지 않는</b> 과제입니다. 체크하면 홈의{" "}
              <b>[완료했는데 실증효과 미입력]</b> 에서 빠지고, 효과 금액의 분모에도 들어가지 않습니다.
              과제 자체는 그대로 관리됩니다.
            </span>
          </span>
        </label>
      </div>

      <div className="form-row">
        <label className="check-label">
          <input
            type="checkbox"
            checked={noReport}
            onChange={(event) => setNoReport(event.target.checked)}
          />
          <span>
            <b>별도 보고 불필요</b>
            <span className="hint">
              단순 현황 관리처럼 주간보고에 올리지 않는 과제입니다. 체크하면{" "}
              <b>보고 대상 후보에서 빠집니다</b> — 필요할 때 손으로 보고를 남기는 길은 그대로입니다.
            </span>
          </span>
        </label>
      </div>
      {/* 서버가 거절한 사유(항목 이름이 든 한국어)는 단추 바로 위에 — 아래 알림만으로는 어느 칸인지 놓친다 (TODO 205) */}
      {error && <p className="form-error" role="alert">{error}</p>}
      {blockers.length > 0 && (
        <p className="hint warn-text form-blocker">
          {startProblem || dateProblem || completedProblem
            ? "날짜를 고쳐야 저장할 수 있습니다."
            : `저장하려면 — ${blockers[0]}`}
        </p>
      )}
      <div className="form-actions">
        <button type="button" className="ghost" onClick={cancel}>
          취소
        </button>
        <button type="submit" disabled={busy || blockers.length > 0}>
          {busy ? "저장 중…" : submitLabel}
        </button>
      </div>
    </form>
  );
}

/** 분류 하나의 선택 상자. 목록에서 빠진 예전 값도 그대로 보인다 — 빈칸으로 바뀌면 안 된다. */
function ClassSelect({
  info,
  value,
  onChange,
}: {
  info: ClassificationInfo;
  value: string;
  onChange: (value: string) => void;
}) {
  const items = value && !info.items.includes(value) ? [...info.items, value] : info.items;
  return (
    <label>
      {info.label}
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">선택 안 함</option>
        {items.map((item) => (
          <option key={item} value={item}>
            {item}
            {!info.items.includes(item) ? " (목록에 없음)" : ""}
          </option>
        ))}
      </select>
    </label>
  );
}
