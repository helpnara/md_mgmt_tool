import { useState } from "react";
import type { Meta, Project } from "../types";

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
    group: initial?.group ?? "",
    owners: (initial?.owners ?? []).join(", "),
    start_date: initial?.start_date ?? "",
    due_date: initial?.due_date ?? "",
    tags: (initial?.tags ?? []).join(", "),
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const update = (key: string, value: string) => setForm((prev) => ({ ...prev, [key]: value }));

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onSubmit({
        title: form.title.trim(),
        status: form.status,
        group: form.group.trim() || null,
        owners: form.owners
          .split(",")
          .map((name) => name.trim())
          .filter(Boolean),
        start_date: form.start_date || null,
        due_date: form.due_date || null,
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
          그룹
          <input
            list="group-options"
            value={form.group ?? ""}
            onChange={(event) => update("group", event.target.value)}
            placeholder="예: 차세대전지"
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
          태그 (쉼표 구분)
          <input value={form.tags} onChange={(event) => update("tags", event.target.value)} />
        </label>
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
