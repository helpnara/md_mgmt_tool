import { useEffect, useRef, useState } from "react";

interface Props {
  projectId: string;
}

const OPTIONS = [
  {
    key: "zip",
    label: "마크다운 + 첨부 (zip)",
    hint: "압축을 풀면 md 옆에 첨부가 함께 있어 링크가 그대로 열립니다.",
    query: "format=zip",
  },
  {
    key: "md",
    label: "마크다운 한 파일",
    hint: "이미지를 파일 안에 심어 md 하나로 완결됩니다.",
    query: "format=md&assets=inline",
  },
  {
    key: "html",
    label: "HTML 한 파일",
    hint: "메일로 보내거나 인쇄하기 좋습니다.",
    query: "format=html",
  },
  {
    key: "backup",
    label: "과제 폴더 백업 (zip)",
    hint: "원본 폴더 구조 그대로 내려받습니다.",
    query: "format=backup",
  },
];

export default function ExportMenu({ projectId }: Props) {
  const [open, setOpen] = useState(false);
  const [withReports, setWithReports] = useState(false);
  const container = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (event: MouseEvent) => {
      if (!container.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  return (
    <div className="export-menu" ref={container}>
      <button className="ghost" onClick={() => setOpen((value) => !value)}>
        내보내기
      </button>
      {open && (
        <div className="export-panel card">
          <label className="toggle">
            <input
              type="checkbox"
              checked={withReports}
              onChange={(event) => setWithReports(event.target.checked)}
            />
            보고 문서 전문 포함
          </label>
          <ul>
            {OPTIONS.map((option) => (
              <li key={option.key}>
                <a
                  href={`/api/projects/${projectId}/export?${option.query}${
                    withReports ? "&include_reports_full=true" : ""
                  }`}
                  onClick={() => setOpen(false)}
                >
                  <strong>{option.label}</strong>
                  <span className="hint">{option.hint}</span>
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
