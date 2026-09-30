import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles.css";
import { notifyError, reportClientError } from "./notify";

// 누구도 받지 않은 실패 (TODO 161 · 166) — 예전에는 콘솔에만 남아 단추가 "아무 일도 안 한" 것처럼 보였다.
// 화면에 알리고, 최근 오류 기록에도 남긴다.
window.addEventListener("unhandledrejection", (event) => {
  const message = (event.reason as Error)?.message || String(event.reason ?? "알 수 없는 오류");
  notifyError(message);
  reportClientError("unhandled", message);
});
window.addEventListener("error", (event) => {
  if (event.message) reportClientError("error", event.message);
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
