"""체험 자료 만들기 (TODO 295) — 지어낸 제조 · 데이터 분석 팀.

사용자(2026-11-17): *"가정을 팀원 수 10명, 수행과제 수 20건, 퇴사자 2명 제외 이런 시나리오로 체험버전을 만들어보자."*
→ 팀장 1 + 팀원 9(지금 10명) + 퇴사 2 · 과제 20(진행 9 · 마침 8 · 보류 1 · 중단 2, 접수에서 승격 6 · 로드맵 줄기 2 ·
퇴사자가 맡다 넘긴 과제 2) · 접수 2 더(판정 대기) · 진행일지 · 보고 · 담당과 역할 · 경험 20 · 교육 · 행사 · 면담 · 목표 · 연말 카드.

* **이 도구의 API 로 만든다**(앱 안에서 부르는 시험 손님) — 파일 모양 · 색인 · 검사가 진짜와 같다. 사람 · 과제 이름은 모두 지어낸 것.
* **날짜는 오늘 기준** — 언제 만들어도 "올해 · 지난해" 가 산다(지난해 시작해 올해 마친 과제, 올해의 일지 · 경험).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Callable

from .. import clock

LEADER = "한도윤"
MEMBERS = ["김서연", "이준호", "박지민", "최민재", "정하은", "강태윤", "조유나", "윤성민", "임채원"]
LEFT = [("오승현", 120), ("신예린", 330)]          # (이름, 오늘에서 며칠 전에 떠났나)

# 과제 20 — (제목, 상태, 담당, 시작(달 전), 기한(달 뒤, -면 지난), 마친 때(달 전), 기대효과, 실증효과, 접수에서?, 앞 과제 번호, 태그)
PROJECTS: list[tuple] = [
    ("전기로 전극봉 원단위 절감", "done", ["김서연", "이준호"], 14, -6, 6, 0.8, 0.8, False, None, ["원가", "전기로"]),
    ("전극봉 원단위 2단계 — 투입 자동 제어", "in_progress", ["김서연", "윤성민"], 5, 4, None, 0.5, None, True, 0, ["원가", "전기로"]),
    ("표면 결함 비전 AI 판정", "done", ["박지민", "정하은"], 12, -3, 3, 1.2, 1.0, False, None, ["품질", "비전AI"]),
    ("표면 결함 판정 현장 확산(3개 라인)", "in_progress", ["박지민", "조유나"], 3, 5, None, 0.9, None, True, 2, ["품질", "비전AI"]),
    ("가열로 연료 원단위 최적화", "in_progress", ["최민재", "강태윤"], 9, 2, None, 0.6, None, False, None, ["에너지"]),
    ("수요 예측 모델 고도화", "done", ["이준호", "임채원"], 13, -5, 5, 0.4, 0.3, False, None, ["예측"]),
    ("시험 결과 자동 집계 시스템", "done", ["정하은"], 15, -2, 2, 0.2, 0.2, False, None, ["자동화"]),
    ("설비 이상 징후 조기 감지", "in_progress", ["강태윤", "윤성민"], 6, 3, None, 0.7, None, True, None, ["설비", "이상탐지"]),
    ("품질 판정 기준서 디지털화", "done", ["조유나"], 10, -4, 4, None, None, False, None, ["품질"]),
    ("MES 실적 연계 대시보드", "in_progress", ["임채원", "김서연"], 4, 3, None, None, None, False, None, ["MES"]),
    ("부원료 배합 최적화", "on_hold", ["최민재"], 7, 1, None, 0.5, None, False, None, ["원가"]),
    ("생성형 AI 보고서 초안 도우미", "in_progress", ["윤성민", "조유나"], 2, 4, None, None, None, True, None, ["생성형AI"]),
    ("공정 데이터 파이프라인 정비", "done", ["이준호", "강태윤"], 11, -7, 7, None, None, False, None, ["데이터"]),
    ("산소 원단위 절감 시험", "dropped", ["최민재"], 8, -2, None, 0.3, None, False, None, ["원가"]),
    ("재고 예측 PoC", "dropped", ["임채원"], 9, -3, None, None, None, False, None, ["예측"]),
    ("현업 AI 교육 과정(PBL) 운영", "done", [LEADER, "정하은"], 10, -1, 1, None, None, False, None, ["교육"]),
    ("설비 정비 이력 분석", "in_progress", ["박지민"], 3, 3, None, None, None, True, None, ["설비"]),
    ("에너지 사용량 모니터링", "in_progress", ["김서연"], 4, 2, None, 0.3, None, False, None, ["에너지"]),
    ("출하 검사 자동 판정", "in_progress", ["정하은", "박지민"], 2, 6, None, 0.6, None, True, None, ["품질", "비전AI"]),
    ("작업 표준서 검색 도우미", "done", ["조유나", "윤성민"], 6, -1, 1, None, None, False, None, ["생성형AI"]),
]
# 퇴사자가 맡다 넘긴 과제 — (과제 번호, 떠난 사람)
HANDOVER = [(4, "오승현"), (6, "신예린")]
PENDING_INTAKES = [("출하 지연 원인 분석 요청", "최민재"), ("작업자 안전 영상 분석 요청", "강태윤")]

# 담당과 역할의 결과 · 기술 — 과제 번호마다
RESULTS = {
    0: ("- 투입 시점 · 전력 패턴 분석\n- 시험 3회 설계와 현장 적용\n- 표준 작업서 개정", "- 원단위 2.10 → 1.85 kg/t (−12%)\n- 연 0.8억원 절감(연환산)", "Python, Minitab"),
    2: ("- 결함 이미지 3,000장 라벨링 기준 정리\n- 판정 모델 학습 · 검증\n- 현장 화면 연동", "- 판정 정확도 92.4%, 재현율 95%\n- 육안 검사 하루 2시간 줄임", "Python, PyTorch"),
    5: ("- 이동평균 방식 진단\n- 특성 설계 · 모델 비교", "- 예측 오차(MAPE) 18% → 9%", "Python, scikit-learn, SQL"),
    6: ("- 수기 집계 절차 분석\n- 자동 집계 스크립트 작성", "- 주 6시간 → 0.5시간", "Excel, VBA, Python"),
    8: ("- 판정 기준 12항목 정리\n- 기준서 검색 화면", "- 기준 문의 월 20 → 5건", "Excel"),
    12: ("- 수집 경로 정리\n- 실시간 적재 · 품질 검사", "- 데이터 지연 1일 → 10분", "Python, SQL, Linux"),
    15: ("- 과정 설계(PBL 6주)\n- 멘토링 운영", "- 수료 35명, 현업 과제 7건", "Teams Copilot"),
    19: ("- 표준서 1,200건 정리\n- 검색 도우미 시범", "- 표준서 찾는 시간 10분 → 1분", "Python, Teams Copilot"),
    1: ("- 투입량 제어 규칙 설계\n- 시범 라인 적용", "", "Python, PLC"),
    3: ("- 라인별 조명 · 카메라 맞춤\n- 판정 결과 MES 연계", "", "PyTorch, MES"),
    4: ("- 연소 데이터 분석\n- 운전 조건 시험", "- 연료 원단위 1.32 → 1.27 Gcal/t(시험)", "Python, MATLAB"),
    7: ("- 진동 · 전류 신호 수집\n- 이상 기준 만들기", "", "Python"),
    9: ("- 실적 항목 정의\n- 대시보드 시안", "", "Power BI, SQL, MES"),
    11: ("- 보고 서식 분석\n- 초안 도우미 시범", "", "Teams Copilot"),
    16: ("- 정비 이력 정리\n- 고장 유형 분류", "", "Excel, Python"),
    17: ("- 계량기 데이터 연결", "", "Power BI"),
    18: ("- 검사 항목 정리\n- 판정 모델 시안", "", "PyTorch"),
}
PRAISE = {0: "끝까지 데이터를 챙겨 줘서 고마워요", 2: "현장 분들과 끝까지 맞춰 준 덕분입니다", 6: "모두의 시간을 돌려줬어요"}

# 경험 — (사람, 과제 번호, 제목, 역량 [(축, 이름)], 보유 기술, 정량 [(지표, 값, 기준, 종류)], 상태)
EXPERIENCES: list[tuple] = [
    ("김서연", 0, "전극봉 원단위 요인 분석과 표준 개정", [("기술", "최적화·시뮬레이션"), ("업무", "제조 공정 이해"), ("문제해결", "병목 진단")], ["Python", "Minitab"],
     [("전극봉 원단위", "2.10 → 1.85 kg/t", "개선 전 연평균", "비교")], "확정"),
    ("김서연", 17, "에너지 사용량 실시간 모니터링 설계", [("기술", "데이터 파이프라인"), ("업무", "요구사항 관리")], ["Power BI"], [], "구조화"),
    ("이준호", 5, "수요 예측 오차 절반으로 줄이기", [("기술", "예측 모델링"), ("문제해결", "성과 지표 재정의")], ["Python", "scikit-learn"],
     [("수요 예측 오차(MAPE)", "18% → 9%", "기존 이동평균 방식", "비교")], "확정"),
    ("이준호", 12, "공정 데이터 파이프라인 정비", [("기술", "데이터 파이프라인"), ("기술", "AI 인프라·플랫폼")], ["Python", "SQL", "Linux"], [], "구조화"),
    ("박지민", 2, "표면 결함 비전 AI 판정 모델", [("기술", "비전 AI 객체탐지"), ("기술", "평가 지표 설계·검증")], ["Python", "PyTorch"],
     [("결함 판정 정확도", "92.4%", "검증 데이터 3,000장", "조건")], "확정"),
    ("박지민", 16, "정비 이력으로 고장 유형 나누기", [("기술", "시계열 분석·이상탐지")], ["Excel", "Python"], [], "초안"),
    ("최민재", 4, "가열로 연소 조건 시험", [("기술", "최적화·시뮬레이션"), ("업무", "제조 공정 이해")], ["Python", "MATLAB"], [], "구조화"),
    ("최민재", 13, "산소 원단위 시험을 멈춘 판단", [("문제해결", "실패 원인 분석"), ("문제해결", "우선순위 기준 수립")], ["Excel"], [], "구조화"),
    ("정하은", 6, "시험 결과 집계 자동화", [("문제해결", "도구 자체 구축"), ("업무", "프로세스 표준화")], ["Excel", "VBA", "Python"],
     [("수기 작업 시간", "주 6시간 → 0.5시간", "기존 엑셀 수작업", "비교")], "확정"),
    ("정하은", 15, "현업 PBL 과정 멘토링", [("리더십", "육성·온보딩"), ("업무", "교육 과정 설계")], ["Teams Copilot"], [], "구조화"),
    ("강태윤", 7, "설비 이상 신호 기준 만들기", [("기술", "시계열 분석·이상탐지"), ("문제해결", "가설 검증·파일럿")], ["Python"], [], "초안"),
    ("강태윤", 12, "실시간 적재 품질 검사", [("기술", "데이터 파이프라인")], ["Python", "SQL"], [], "구조화"),
    ("조유나", 8, "품질 판정 기준서 디지털화", [("업무", "품질 관리"), ("업무", "프로세스 표준화")], ["Excel"],
     [("기준 문의 건수", "월 20 → 5건", "디지털화 전 6개월 평균", "비교")], "확정"),
    ("조유나", 19, "작업 표준서 검색 도우미 시범", [("기술", "생성형 AI 활용"), ("업무", "요구사항 관리")], ["Python", "Teams Copilot"], [], "초안"),
    ("윤성민", 11, "보고서 초안 도우미 프롬프트 설계", [("기술", "생성형 AI 활용")], ["Teams Copilot"], [], "초안"),
    ("윤성민", 1, "전극봉 투입 자동 제어 규칙", [("기술", "실시간 시스템 개발"), ("업무", "제조 공정 이해")], ["Python", "PLC"], [], "구조화"),
    ("임채원", 9, "MES 실적 항목 정의", [("기술", "ERP·MES 연계"), ("업무", "요구사항 관리")], ["SQL", "MES", "Power BI"], [], "초안"),
    ("임채원", 14, "재고 예측 PoC 를 접은 이유", [("문제해결", "지표의 함정 발견"), ("기술", "예측 모델링")], ["Python"], [], "구조화"),
    (LEADER, 15, "현업 AI 교육 과정 설계 · 운영", [("업무", "교육 과정 설계"), ("리더십", "학습 문화 운영"), ("업무", "경영층 커뮤니케이션")], ["Teams Copilot"],
     [("교육 수료 인원", "35명", "과정 누적 수료", "집계")], "확정"),
    (LEADER, 0, "원가 과제 포트폴리오 정리", [("업무", "과제 포트폴리오 관리"), ("리더십", "조직 간 조율")], ["Excel"], [], "초안"),
]


class SeedError(RuntimeError):
    pass


def _months(today: date, months: int) -> date:
    """오늘에서 months 달 뒤(음수면 앞) — 일은 15일로."""
    y, m = today.year, today.month + months
    while m <= 0:
        m += 12
        y -= 1
    while m > 12:
        m -= 12
        y += 1
    return date(y, m, 15)


def build(progress: Callable[[int, int, str], None] | None = None) -> dict[str, int]:
    """지금 연 데이터 폴더(체험 폴더)에 체험 자료를 만든다. 폴더는 비어 있어야 한다."""
    from fastapi.testclient import TestClient

    from ..main import app

    from .mode import SEED_HEADER, seed_token

    # 서버 PC(관리자)로 — 쓰기 권한. 바꾸는 중(297)에도 이 손님만 지나간다
    client = TestClient(app, client=("127.0.0.1", 50295), headers={SEED_HEADER: seed_token()})
    steps = 10
    say = progress or (lambda *_: None)
    today = clock.today()

    def call(method: str, url: str, **kw: Any) -> Any:
        response = client.request(method, url, **kw)
        if response.status_code >= 400:
            raise SeedError(f"{method} {url} → {response.status_code}: {response.text[:300]}")
        return response.json() if response.content else None

    def iso(d: date) -> str:
        return d.isoformat()

    meta = call("GET", "/api/meta")
    classes = {c["key"]: c["items"] for c in meta.get("classifications", [])}
    types = [t["key"] for t in meta.get("types", [])] or [None]
    kinds = [k if isinstance(k, str) else k.get("key") for k in meta.get("meeting_kinds", [])] or ["정기"]

    # 1 명부 · 작성자
    say(1, steps, "명부")
    people = [{"name": LEADER, "leader": True}] + [{"name": n} for n in MEMBERS] + [
        {"name": n, "left_on": iso(today - timedelta(days=days)), "left_reason": "퇴사"} for n, days in LEFT]
    call("PUT", "/api/people", json={"people": people})
    call("PUT", "/api/settings", json={"author": LEADER})

    # 2 접수 · 과제
    say(2, steps, "접수 · 과제 20건")
    ids: list[str] = []
    handed = dict(HANDOVER)
    for i, (title, status, owners, start, due, done, exp, ver, from_intake, pred, tags) in enumerate(PROJECTS):
        if i in handed:
            owners = [handed[i], *owners]      # 떠나기 전에는 함께 맡았다 — 담당과 역할을 남긴 뒤 담당에서 뺀다(3)
        pick = lambda key: (classes.get(key) or [None])[i % max(1, len(classes.get(key) or [None]))]  # noqa: E731
        start_d = _months(today, -start)
        due_d = _months(today, due)
        base = {"title": title, "start_date": iso(start_d), "due_date": iso(due_d), "nature": pick("nature"), "category": pick("category"),
                "delivery": pick("delivery"), "cost_kind": pick("cost_kind"), "tags": tags}
        if from_intake:
            intake = call("POST", "/api/intakes", json={**{k: base[k] for k in ("title", "nature", "category", "delivery", "cost_kind", "tags")},
                                                       "leader": owners[0], "received_on": iso(start_d - timedelta(days=20)),
                                                       "effect_request": exp, "priority": "상" if i % 2 else "중",
                                                       "body": f"## 요청 배경\n{title} — 현장에서 반복되는 어려움을 줄이고 싶습니다.\n"})
            made = call("POST", f"/api/intakes/{intake['id']}/promote", json={
                "owners": owners, "type": types[i % len(types)], "status": "in_progress", "start_date": base["start_date"], "due_date": base["due_date"],
                "effect_expected": exp, "tags": tags, "decision_note": "체험 자료 — 착수 판정"})
            pid = made["project_id"]
        else:
            made = call("POST", "/api/projects", json={**base, "owners": owners, "status": "in_progress", "type": types[i % len(types)],
                                                      "effect_expected": exp,
                                                      "body": f"## 배경\n{title}\n\n## 목표\n현장 지표를 개선한다.\n"})
            pid = made["id"]
        ids.append(pid)
    for i, (title, status, owners, start, due, done, exp, ver, _fi, pred, _tags) in enumerate(PROJECTS):
        patch: dict[str, Any] = {}
        if pred is not None:
            patch["predecessors"] = [ids[pred]]
        if status != "in_progress":
            patch["status"] = status
        if done is not None:
            patch["completed_at"] = iso(_months(today, -done))
        if ver is not None:
            patch["effect_verified"] = ver
        if patch:
            call("PATCH", f"/api/projects/{ids[i]}", json=patch)
    pending_ids: list[str] = []
    for title, leader in PENDING_INTAKES:
        made_intake = call("POST", "/api/intakes", json={"title": title, "leader": leader, "received_on": iso(today - timedelta(days=9)),
                                                         "body": f"## 요청 배경\n{title}\n"})
        pending_ids.append(made_intake["id"])

    # 3 담당과 역할 · 퇴사자 넘김
    say(3, steps, "담당과 역할")
    for i, (_t, status, owners, start, due, done, *_rest) in enumerate(PROJECTS):
        did, result, skills = RESULTS.get(i, ("- 현황 파악", "", "Excel"))
        for j, name in enumerate(owners):
            body: dict[str, Any] = {"role": "주관" if j == 0 else "참여", "did": did, "skills": skills}
            if result:
                body["result"] = result
            if j == 0 and i in PRAISE:
                body["praise"] = PRAISE[i]
            call("PUT", f"/api/projects/{ids[i]}/contributions/{name}", json=body)
    for index, leaver in HANDOVER:
        days = dict(LEFT)[leaver]
        call("PUT", f"/api/projects/{ids[index]}/contributions/{leaver}", json={
            "role": "주관", "from": iso(_months(today, -PROJECTS[index][3])), "to": iso(today - timedelta(days=days)),
            "did": "- 초기 분석 · 시험 계획", "skills": "Excel"})
        call("PATCH", f"/api/projects/{ids[index]}", json={"owners": PROJECTS[index][2]})

    # 4 진행일지
    say(4, steps, "진행일지")
    entry_titles = ["착수 · 현황 파악", "데이터 수집 · 분석", "시험 결과 공유", "현장 적용 협의", "결과 정리"]
    for i, (_t, status, owners, start, due, done, *_rest) in enumerate(PROJECTS):
        span = max(1, (start - (done or 0)) * 30)
        count = 2 if status == "dropped" else 4 if status in ("done", "in_progress") else 3
        for k in range(count):
            when = _months(today, -start) + timedelta(days=int(span * (k + 1) / (count + 1)))
            when = min(when, today - timedelta(days=1))
            call("POST", f"/api/projects/{ids[i]}/entries", json={
                "date": iso(when), "title": entry_titles[k % len(entry_titles)], "author": owners[k % len(owners)],
                "body": f"- {entry_titles[k % len(entry_titles)]} 진행\n- 다음: 결과 확인 후 공유"})

    # 5 보고(초안 → 확정) — 진행 중 넷
    say(5, steps, "보고 이력")
    for i in (1, 3, 4, 7):
        draft = call("POST", f"/api/projects/{ids[i]}/reports/draft", json={"report_date": iso(today - timedelta(days=14)), "audience": "본부장"})
        rid = (draft or {}).get("id")
        if rid:
            try:
                call("POST", f"/api/reports/{rid}/freeze")
            except SeedError:
                pass     # 확정 조건이 바뀌었어도 초안으로 남긴다

    # 6 경험 20
    say(6, steps, "경험")
    for n, (person, pindex, title, skills, tools, quants, status) in enumerate(EXPERIENCES):
        p = PROJECTS[pindex]
        start = _months(today, -p[3])
        end = _months(today, -(p[5] or 0)) if p[5] is not None else None
        made = call("POST", "/api/experiences", json={
            "person": person, "title": title, "project": ids[pindex], "kind": "업무", "role": "주관" if p[2][0] == person else "참여",
            "start": start.strftime("%Y-%m"), "end": end.strftime("%Y-%m") if end and p[1] in ("done", "dropped") else "",
            "situation": f"{p[0]} — 현장에서 반복되던 어려움", "goal": "지표를 개선하고 현장에 정착", "actions": [line.lstrip("- ") for line in RESULTS.get(pindex, ("- 현황 파악",))[0].split("\n")],
            "result_qual": "현장 담당과 함께 결과를 확인했다", "lesson": "현장 기준을 먼저 맞추면 이후가 빠르다",
            "skills": [{"axis": a, "name": nm} for a, nm in skills], "tools": tools,
            "quants": [{"metric": m, "value": v, "baseline": b, "baseline_kind": k, "when": str(today.year)} for m, v, b, k in quants]})
        eid = made["id"]
        if status in ("구조화", "확정"):
            # 구조화는 [AI 로 정리]로만, 확정은 정합성 확인과 함께 여는 단계라 API 로는 바로 못 간다 —
            # 체험 자료는 그 단계를 거친 **결과**를 보여 주려는 것이므로 상태 칸만 서비스로 바로 적는다(파일 모양은 같다)
            from ..db import connect
            from . import experiences as exp_svc

            conn = connect()
            try:
                extra = {"confirmed_at": exp_svc.now_iso(), "confirmed_by": LEADER} if status == "확정" else {}
                exp_svc._set_status(conn, eid, status, extra)
            finally:
                conn.close()
        if n % 5 == 4:
            say(6, steps, f"경험 {n + 1}/20")
        if n == 11:
            # 306 · 292 G — 경험이 반쯤 있을 때의 그림을 "지난해 말 기록" 으로(변화 카드의 "기준 지난해 말 기록 ↔ 지금" 이 보이게)
            call("POST", "/api/team-skills/snapshots", json={"year": str(today.year - 1)})

    # 7 교육 · 행사 · 면담
    say(7, steps, "교육 · 면담")
    # 306 · 292 E — 교육 넷에 관련 역량(그 뒤 경험이 생긴 사람 · 아직 · 1년 지남이 섞이게)
    acts = [("education", "현업 데이터 분석 기초", -150, 16, MEMBERS[:4], ["예측 모델링"]), ("seminar", "AI 비전 사례 세미나", -90, 3, ["박지민", "정하은", "조유나"], []),
            ("conference", "생산기술 학회", -60, 8, ["김서연", "최민재"], []), ("education", "생성형 AI 활용 과정", -40, 12, ["윤성민", "조유나", "임채원"], ["생성형 AI 활용"]),
            ("expo", "스마트공장 박람회", -25, 6, ["강태윤", "이준호"], []), ("certificate", "데이터 분석 자격", -200, 0, ["이준호"], []),
            ("education", "MES 데이터 구조 교육", -15, 4, ["임채원", "김서연"], ["ERP·MES 연계"]), ("seminar", "품질 혁신 공유회", -8, 2, MEMBERS, []),
            ("education", "공정 시뮬레이션 기초", -420, 8, ["최민재", "정하은"], ["최적화·시뮬레이션"]),
            ("education", "PyTorch 실습", 20, 12, ["박지민", "정하은"], []), ("conference", "AI 학회(예정)", 45, 8, ["이준호", "윤성민"], [])]
    for kind, title, offset, hours, names, act_skills in acts:
        for name in names:
            call("POST", "/api/activities", json={"person": name, "kind": kind, "title": title, "date": iso(today + timedelta(days=offset)),
                                                 "hours": hours or None, "host": "사내" if kind == "education" else "외부", "skills": act_skills})
    for k, name in enumerate(["김서연", "박지민", "최민재", "조유나"]):
        call("POST", "/api/meetings", json={"person": name, "date": iso(today - timedelta(days=20 + 15 * k)), "kind": kinds[k % len(kinds)],
                                           "summary": "올해 과제 진행과 내년에 키울 역량을 이야기함", "next_date": iso(today + timedelta(days=40 + 7 * k))})

    # 8 목표 · 연말 카드
    say(8, steps, "목표 · 연말 카드")
    call("PUT", "/api/team-skills/targets", json={"targets": [
        {"kind": "역량", "name": "비전 AI 객체탐지", "want": 3}, {"kind": "보유 기술", "name": "PyTorch", "want": 3},
        {"kind": "역량", "name": "생성형 AI 활용", "want": 4}]})
    call("PUT", "/api/yearcards/card", params={"name": "김서연", "year": str(today.year)},
         json={"message": "올 한 해 전극봉 과제를 끝까지 챙겨 줘서 고마웠어요. 데이터로 길을 내 준 덕분에 팀 전체가 힘을 얻었습니다. 내년에도 함께해요!",
               "headline": "데이터로 길을 낸 한 해", "projects": [ids[0], ids[17]]})

    # 9 · 306 — 292 2 · 3차: 육성 목표(C) · 승계 · 짝 계획(B) · 필요 역량(D)
    say(9, steps, "육성 목표 · 승계 계획 · 필요 역량")
    year = str(today.year)
    goals = {
        "김서연": [{"skill": "데이터 파이프라인", "way": "과제", "note": "MES 대시보드 과제에서"}, {"skill": "생성형 AI 활용", "way": "교육", "note": "사내 과정 신청"}],
        "이준호": [{"skill": "예측 모델링", "way": "과제", "note": "", "mark": "이룸"}, {"skill": "AI 인프라·플랫폼", "way": "짝", "note": "강태윤과 짝"}],
        "박지민": [{"skill": "시계열 분석·이상탐지", "way": "과제", "note": "정비 이력 분석 과제"}, {"skill": "비전 AI 객체탐지", "way": "과제", "mark": "이룸"}],
        "조유나": [{"skill": "생성형 AI 활용", "way": "교육", "note": ""}, {"skill": "프로세스 표준화", "way": "짝", "note": "정하은과 짝"},
                  {"skill": "요구사항 관리", "way": "과제", "note": "보고서 도우미 과제"}],
    }
    for name, items in goals.items():
        call("PUT", f"/api/growth/{name}/{year}", json={"goals": items})
    plans = [
        {"kind": "역량", "name": "비전 AI 객체탐지", "holders": ["박지민"], "learner": "정하은", "way": "짝 과제", "due": iso(_months(today, 4)), "note": "출하 검사 자동 판정 과제에서 함께"},
        {"kind": "역량", "name": "ERP·MES 연계", "holders": ["임채원"], "learner": "김서연", "way": "공유 세션", "due": iso(today - timedelta(days=10)), "note": "월 1회 공유 세션"},
        {"kind": "역량", "name": "제조 공정 이해", "holders": ["김서연", "최민재"], "learner": "윤성민", "way": "짝 과제", "due": iso(_months(today, 2))},
    ]
    for plan in plans:
        call("POST", "/api/team-skills/succession", json=plan)
    call("GET", "/api/team-skills/succession")          # 배울 사람에게 이미 경험이 있는 계획은 저절로 "됨"
    for index, need in ((1, ["최적화·시뮬레이션", "제조 공정 이해"]), (7, ["시계열 분석·이상탐지", "예측 모델링"]),
                        (18, ["비전 AI 객체탐지", "평가 지표 설계·검증"])):
        call("PATCH", f"/api/projects/{ids[index]}", json={"need_skills": need})
    if pending_ids:
        call("PATCH", f"/api/intakes/{pending_ids[0]}", json={"need_skills": ["실패 원인 분석", "데이터 파이프라인"]})

    say(10, steps, "마무리")
    return {"projects": len(ids), "people": len(people), "experiences": len(EXPERIENCES)}
