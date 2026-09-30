import { Component } from "react";
import type { ReactNode } from "react";
import { reportClientError } from "../notify";

/**
 * 화면 하나가 그리다 멈추면 **그 화면만** 막는다 (TODO 166).
 *
 * 안전망이 없으면 예외 하나에 머리 메뉴까지 통째로 흰 화면이 된다. 메뉴가 살아 있으면 다른 화면으로
 * 갈 수 있고, 무엇이 멈췄는지는 최근 오류 기록에 남는다(내용 없이 오류 종류와 메시지만).
 * `resetKey`(화면 이름)가 바뀌면 다시 그려 본다 — 다른 화면으로 가면 풀린다.
 */
export default class ErrorBoundary extends Component<
  { resetKey: string; children: ReactNode },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error) {
    reportClientError("render", `${error.name}: ${error.message}`);
  }

  componentDidUpdate(prev: { resetKey: string }) {
    if (prev.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null });
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="card load-error render-error">
        <h2>이 화면을 그리지 못했습니다</h2>
        <p className="hint">{this.state.error.message}</p>
        <p className="hint">
          작성한 내용은 파일에 그대로 있습니다. 다시 시도해도 같으면 <b>설정 › 최근 오류</b>의 내용을 복사해
          알려 주세요 — 방금 것이 거기 남았습니다.
        </p>
        <div className="form-actions">
          <button className="ghost" onClick={() => (window.location.hash = "#/")}>
            홈으로
          </button>
          <button onClick={() => this.setState({ error: null })}>다시 시도</button>
        </div>
      </div>
    );
  }
}
