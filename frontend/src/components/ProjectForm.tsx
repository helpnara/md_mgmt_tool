import { useState } from "react";
import type { Meta, Project } from "../types";
import TagSuggestions from "./TagSuggestions";

interface Props {
  meta: Meta;
  initial?: Partial<Project>;
  submitLabel: string;
  onSubmit: (payload: Partial<Project>) => Promise<void>;
  onCancel: () => void;
}

export default function ProjectForm({ meta, initial, submitLabel, onSubmit, onCancel }: Props) {
  const [form, setForm] = useState({
    title: initial?.title ?? "",
    status: initial?.status ?? "in_progress",
    type: initial?.type ?? "",
    group: initial?.group ?? "",
    owners: (initial?.owners ?? []).join(", "),
    start_date: initial?.start_date ?? "",
    due_date: initial?.due_date ?? "",
    effect_expected: initial?.effect_expected?.toString() ?? "",
    effect_verified: initial?.effect_verified?.toString() ?? "",
    tags: (initial?.tags ?? []).join(", "),
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const update = (key: string, value: string) => setForm((prev) => ({ ...prev, [key]: value }));

  // 비우면 null 로 보낸다 — "아직 안 정했다"와 "0원"은 다른 뜻이다.
  const effect = (value: string): number | null => (value.trim() === "" ? null : Number(value));

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onSubmit({
        title: form.title.trim(),
        status: form.status,
        type: form.type || null,
        group: form.group.trim() || null,
        owners: form.owners
          .split(",")
          .map((name) => name.trim())
          .filter(Boolean),
        start_date: form.start_date || null,
        due_date: form.due_date || null,
        effect_expected: effect(form.effect_expected),
        effect_verified: effect(form.effect_verified),
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
    <form className="project-form" onSubmit={handleSubmit}>
      <label>
        과제명
        <input
          value={form.title}
          onChange={(event) => update("title", event.target.value)}
          required
          autoFocus
        />
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
        <label>
          그룹 (예 : 회의체, 지시사항 등)
          <input
            list="group-options"
            value={form.group ?? ""}
            onChange={(event) => update("group", event.target.value)}
            placeholder="예: 회의체"
          />
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
            {meta.owners.map((name) => (
              <option key={name} value={name} />
            ))}
          </datalist>
        </label>
      </div>
      <div className="form-row">
        <label>
          시작일
          <input
            type="date"
            value={form.start_date ?? ""}
            onChange={(event) => update("start_date", event.target.value)}
          />
        </label>
        <label>
          마감일
          <input
            type="date"
            value={form.due_date ?? ""}
            onChange={(event) => update("due_date", event.target.value)}
          />
        </label>
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
      <div className="form-row">
        <label>
          기대효과 (억원/년)
          <input
            type="number"
            step="0.1"
            min="0"
            value={form.effect_expected}
            onChange={(event) => update("effect_expected", event.target.value)}
            placeholder="예: 1.2"
          />
        </label>
        <label>
          실증효과 (억원/년)
          <input
            type="number"
            step="0.1"
            min="0"
            value={form.effect_verified}
            onChange={(event) => update("effect_verified", event.target.value)}
            placeholder="과제가 끝난 뒤 채웁니다"
          />
        </label>
        <p className="hint effect-hint">
          정성적 효과와 산출 근거는 <b>과제 개요</b>에 적습니다.
          근거 자료(엑셀·PPT)는 개요의 [파일 첨부]로 붙일 수 있습니다.
        </p>
      </div>
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button type="button" className="ghost" onClick={onCancel}>
          취소
        </button>
        <button type="submit" disabled={busy}>
          {busy ? "저장 중…" : submitLabel}
        </button>
      </div>
    </form>
  );
}
