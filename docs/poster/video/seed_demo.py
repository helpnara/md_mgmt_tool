"""포스터·썸네일·소개 영상에 쓸 **데모 자료** 만들기.

실제 과제 데이터는 쓰지 않는다. 화면이 비어 있으면 볼 것이 없고, 진짜 자료를 쓰면
사내 내용이 발표물에 그대로 실린다. 그래서 **팀원 8명 · 과제 14건 · 보고 23건 ·
역량 기록 8건**짜리 가짜 팀을 만든다 — 실제로 쓰는 모양에 가깝게, 다만 전부 지어낸 것으로.

    # 1) 빈 vault 로 서버를 띄운다 (경로는 화면 머리글에 그대로 보이므로 짧게)
    MD_MGMT_VAULT=~/과제이력관리 python -m uvicorn app.main:app --app-dir backend --port 8094

    # 2) 채운다
    python docs/poster/video/seed_demo.py

이 자료로 갈무리한 화면이 `docs/poster/screen-*.png` 이고, 녹화한 것이 `clips/*.webm` 이다.
"""
from __future__ import annotations

import json
import random
import urllib.error
import urllib.request

# 같은 자료가 다시 나오게 씨앗을 박아 둔다 — 갈무리를 다시 찍어도 화면이 흔들리지 않는다.
random.seed(7)
BASE = "http://127.0.0.1:8094"


def call(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        BASE + path, data=data, headers={"Content-Type": "application/json"}, method=method
    )
    try:
        raw = urllib.request.urlopen(request).read()
    except urllib.error.HTTPError as error:
        print(method, path, error.code, error.read()[:200].decode())
        raise
    return json.loads(raw) if raw else {}
roster=["권경락","김현우","박서연","이도윤","최민서","정하준","윤지호","강예린"]
call("PUT","/api/people",{"people":[{"name":n} for n in roster]})
call("PUT","/api/settings",{"author":"권경락"})
P=[("리튬전지 장수명 셀 설계","in_progress","rnd","차세대전지",["김현우","박서연"],"2026-12-20",4.5,2.8,["설계"]),
   ("차세대 양극재 스케일업 검토","reviewing","smart","소재",["이도윤"],"2026-09-30",3.2,None,["스케일업"]),
   ("전해액 첨가제 신규 조성 제안","planned","investment","소재",["최민서","윤지호"],"2026-11-30",1.75,None,[]),
   ("2027년 국책과제 기획","planned","plan_report","기획",["정하준"],"2026-10-15",None,None,[]),
   ("셀 팽창 원인 분석","on_hold","rnd","차세대전지",["박서연"],"2026-08-31",2.0,None,[]),
   ("2025년 수명평가 표준화","done","national","표준",["강예린","권경락"],"2026-06-30",6.4,5.9,[]),
   ("열폭주 억제 분리막 평가","done","rnd","안전",["윤지호"],"2026-07-31",2.25,1.8,[]),
   ("충방전 데이터 자동 수집","reviewing","smart","스마트팩토리",["정하준","최민서"],"2026-12-31",1.1,None,[]),
   ("건식 전극 공정 실증","in_progress","rnd","공정",["김현우"],"2026-11-15",5.0,None,[]),
   ("실리콘 음극 팽창 억제","in_progress","rnd","차세대전지",["박서연","이도윤"],"2027-03-31",3.8,None,[]),
   ("협력사 품질 이슈 대응","dropped","smart","품질",["강예린"],"2026-05-31",None,None,[]),
   ("시험실 장비 가동 현황","in_progress","smart","운영",["최민서"],None,None,None,[]),
   ("전고체 파일럿 라인 검토","planned","investment","차세대전지",["권경락","김현우"],"2027-06-30",12.0,None,[]),
   ("사내 소재 DB 구축","in_progress","smart","스마트팩토리",["정하준"],"2026-12-31",0.9,None,[])]
ids=[]
for t,st,ty,gr,ow,due,ee,ev,tags in P:
    d={"title":t,"status":st,"type":ty,"group":gr,"owners":ow,"tags":tags}
    if due: d["due_date"]=due
    if ee is not None: d["effect_expected"]=ee
    if ev is not None: d["effect_verified"]=ev
    ids.append(call("POST","/api/projects",d)["id"])
call("PATCH",f"/api/projects/{ids[11]}",{"no_report":True})
BODIES=["## 내용\n\n- 1차 시제품 제작 완료, 인장강도 780MPa 확보\n- 협력사 미팅 진행\n\n## 다음\n\n2차 시제품 착수",
        "## 내용\n\n샘플 5종 평가 결과 정리.\n\n| 구분 | 용량 |\n|---|---|\n| A | 210 |\n\n초기 용량은 A 가 우세.",
        "## 내용\n\n- 설비 셋업 완료\n- 조건 3수준 예비 실험 착수"]
plan={"2026-001":[(2,3),(3,11),(4,7),(5,19),(6,2),(7,14),(8,4),(8,26),(9,3)],
 "2026-002":[(3,5),(4,21),(6,9),(8,18)],"2026-003":[(5,12),(7,7)],"2026-004":[(6,15),(8,20)],
 "2026-005":[(2,17),(3,24)],"2026-006":[(1,20),(2,10),(3,17),(5,6),(6,24)],
 "2026-007":[(2,26),(4,14),(6,11),(7,22)],"2026-008":[(4,9),(6,3),(8,11),(9,1)],
 "2026-009":[(3,2),(4,28),(5,26),(7,9),(8,13),(9,2)],"2026-010":[(5,4),(6,30),(8,6)],
 "2026-011":[(2,5)],"2026-012":[(6,18)],"2026-013":[(7,1)],"2026-014":[(4,16),(6,22),(8,28)]}
for pid,days in plan.items():
    for m,d in days:
        call("POST",f"/api/projects/{pid}/entries",{"date":f"2026-{m:02d}-{d:02d}",
             "title":random.choice(["1차 시제품","중간 점검","조건 실험","분석 결과 회신"]),"body":random.choice(BODIES)})
MEET=["전사 주요업무 보고","팀 주간회의","연구소 월간회의","본부 실적 점검"]
rep={"2026-001":[(3,10),(4,14),(5,26),(7,7),(8,25)],"2026-002":[(4,14),(6,16),(8,25)],
 "2026-006":[(2,10),(3,10),(5,12),(6,30)],"2026-007":[(3,10),(5,12),(7,7)],
 "2026-008":[(5,12),(8,25)],"2026-009":[(4,14),(6,16),(7,7),(9,1)],"2026-010":[(6,16)],"2026-014":[(5,12)]}
n=0
for pid,days in rep.items():
    for m,d in days:
        r=call("POST",f"/api/projects/{pid}/reports/draft",{"report_date":f"2026-{m:02d}-{d:02d}","audience":random.choice(MEET)})
        call("POST",f"/api/reports/{r['id']}/freeze"); n+=1
acts=[("2026-03-12","2026-03-13","education","김현우, 박서연","이차전지 소재 심화 과정","한국전지산업협회",16,480000),
 ("2026-04-08",None,"seminar","이도윤","전고체 전지 기술 동향 세미나","전자부품연구원",4,0),
 ("2026-05-21","2026-05-23","expo","최민서, 윤지호, 정하준","InterBattery 2026","코엑스",8,0),
 ("2026-06-17","2026-06-19","conference","강예린","한국전기화학회 춘계 학술대회","제주",24,650000),
 ("2026-07-02","2026-07-04","education","정하준","데이터 분석 실무 (Python)","사내 교육센터",24,None),
 ("2026-08-19",None,"seminar","권경락, 김현우","AI 활용 업무혁신 워크숍","사내",6,0),
 ("2025-09-10","2025-09-11","conference","김현우","한국세라믹학회 추계","여수",16,540000),
 ("2026-02-05",None,"certificate","윤지호","품질경영기사","한국산업인력공단",None,None)]
for date,end,kind,who,title,place,hours,cost in acts:
    p={"date":date,"kind":kind,"person":who,"title":title,"place":place}
    if end: p["end_date"]=end
    if hours is not None: p["hours"]=hours
    if cost is not None: p["cost"]=cost
    call("POST","/api/activities",p)
print("보고",n,"건 확정")
