from harness import *
import os, stat

def judge(name, req, r, accept_2xx=False, extra=""):
    st = r.status_code
    if st >= 500: rec(name, req, r, "PROBLEM", "500 " + extra, "⛔")
    elif st >= 400:
        d = detail(r)
        if st == 422: rec(name, req, r, "note", "422 english: " + d[:90] + extra)
        elif not is_korean(d): rec(name, req, r, "PROBLEM", "non-Korean " + d[:80], "🟡")
        else: rec(name, req, r, "ok", d[:80] + extra)
    else: rec(name, req, r, "ok" if accept_2xx else "note", f"{st} " + extra)
    return r

with fresh() as (c, vault):
    S = "/api/settings"
    for body in [{"report_weekday": 7}, {"report_weekday": -1}, {"report_weekday": "월"}, {"report_weekday": 3.5}, {"report_weekday": None},
                 {"author": ""}, {"author": "   "}, {"author": "x" * 1000}, {"author": "a\nb"},
                 {"project_code": "abc"}, {"project_code": "소재"}, {"project_code": "a b"}, {"project_code": "a/b"}, {"project_code": "123"}, {"project_code": "CON"}, {"project_code": "x" * 50}, {"project_code": "소재."}, {"project_code": None},
                 {"backup_dir": str(vault)}, {"backup_dir": str(vault / "sub")}, {"backup_dir": str(vault / "projects")}, {"backup_dir": "/nonexistent/zzz/yyy"}, {"backup_dir": "/"}, {"backup_dir": "/etc"}, {"backup_dir": "relative/dir"}, {"backup_dir": str(vault.parent)}, {"backup_dir": ""},
                 {"backup_keep": 0}, {"backup_keep": -1}, {"backup_keep": 10**9}, {"backup_every_hours": 0}, {"backup_every_hours": -5}, {"backup_keep_weekly": "x"},
                 {"entry_templates": {"": "x" * 100000}}, {"entry_templates": {"../x": "a"}}, {"entry_templates": "text"}, {"report_template": "{summary}{summary}{bogus}"}, {"report_template": "{"},
                 {"classifications": {"nature": ["a"] * 500}}, {"classifications": {"bogus": ["a"]}}, {"classifications": "x"}, {"classifications": {"nature": [1, 2]}},
                 {"intake_stale_days": -1}, {"intake_stale_days": 0}, {"meeting_cycle_days": 0}, {"meeting_cycle_days": -1}, {"meeting_kinds": ["a"] * 200}, {"meeting_kinds": [""]},
                 {"precheck_items": "bogus text\n\n"}, {"precheck_items": [{"x": 1}]}, {"precheck_thresholds": [5, 1]}, {"precheck_thresholds": [-1]}, {"precheck_thresholds": [1, 2, 3, 4, 5]}, {"precheck_thresholds": "x"},
                 {"ai_prompt_prefix": "x" * 200000}, {"unknown_key": 1}, {}]:
        r = c.put(S, json=body)
        tag = str(body)[:70]
        if r.status_code == 200:
            cur = c.get(S).json()
            k = next(iter(body), None)
            rec("settings", f"PUT {tag}", r, "note", f"accepted → {k}={str(cur.get(k))[:80]!s}" if k else "accepted")
        else: judge("settings", f"PUT {tag}", r)
    print("backup status:", c.get(f"{S}/backup/status").json())
    # backup run with vault as backup dir → zip inside vault?
    c.put(S, json={"backup_dir": str(vault / "backups")})
    judge("backup", "run backup to vault/backups", c.post(f"{S}/backup/run"), accept_2xx=True)
    print("backups:", tree(vault / "backups") if (vault / "backups").exists() else "none")
    c.put(S, json={"backup_dir": ""})
    judge("backup", "run backup with backup_dir=''", c.post(f"{S}/backup/run"))
    # unwritable backup dir
    ro = vault.parent / "ro"; ro.mkdir(); os.chmod(ro, 0o555)
    r = c.put(S, json={"backup_dir": str(ro)}); print("set ro dir:", r.status_code, r.text[:150])
    if r.status_code == 200: judge("backup", "run backup to read-only dir", c.post(f"{S}/backup/run"))
    os.chmod(ro, 0o755)
    # people
    PP = "/api/people"
    for body in [{"people": [{"name": "홍길동"}, {"name": "홍길동"}]}, {"people": [{"name": ""}]}, {"people": [{"name": "  "}]}, {"people": [{"name": "홍길동", "left_on": "2020-01-01", "joined_on": "2025-01-01"}]},
                 {"people": [{"name": "홍길동", "left_on": "2026-13-01"}]}, {"people": [{"name": "홍길동", "left_on": "x"}]}, {"people": [{"name": "홍길동", "employee_id": "../x"}]}, {"people": [{"name": "a, b"}]},
                 {"people": [{"name": "x" * 500}]}, {"people": []}, {"people": [{"name": f"사람{i}"} for i in range(500)]}]:
        r = c.put(PP, json=body)
        if r.status_code == 200: rec("people", f"PUT people {str(body)[:60]}", r, "note", f"accepted → n={len(r.json()['people'])} {str(r.json()['people'])[:100]}")
        else: judge("people", f"PUT people {str(body)[:60]}", r)
    judge("people", "POST add '' ", c.post(PP, json={"name": ""}))
    judge("people", "POST add dup", c.post(PP, json={"name": "사람1"}) if False else c.post(PP, json={"name": "중복"}), accept_2xx=True)
    judge("people", "POST add dup again", c.post(PP, json={"name": "중복"}))
    judge("people", "POST add 'a, b'", c.post(PP, json={"name": "a, b"}), accept_2xx=True)
    judge("people", "rename old==new", c.post(f"{PP}/rename", json={"old": "중복", "new": "중복"}))
    judge("people", "rename to ''", c.post(f"{PP}/rename", json={"old": "중복", "new": ""}))
    judge("people", "handover old==new", c.post(f"{PP}/handover", json={"old": "중복", "new": "중복"}))
    judge("people", "handover to ''", c.post(f"{PP}/handover", json={"old": "중복", "new": ""}))
    pid = c.post("/api/projects", json={"title": "담당", "owners": ["중복", "다른이"]}).json()["id"]
    judge("people", "rename 중복→다른이 (merge owners)", c.post(f"{PP}/rename", json={"old": "중복", "new": "다른이"}), accept_2xx=True)
    print("owners after rename:", c.get(f"/api/projects/{pid}").json()["owners"])
    judge("people", "GET people", c.get(PP), accept_2xx=True)
    # project types
    PT = f"{S}/project-types"
    judge("types", "PUT types=[] (empties everything)", c.put(PT, json={"types": []}), accept_2xx=True, extra=f"meta types={c.get('/api/meta').json()['types']}")
    judge("types", "create project type=smart after emptied", c.post("/api/projects", json={"title": "x", "type": "smart"}))
    judge("types", "PUT types key '../x'", c.put(PT, json={"types": [{"key": "../x", "label": "a"}]}), accept_2xx=True)
    judge("types", "PUT types key with space/korean", c.put(PT, json={"types": [{"key": "한 글", "label": "a"}]}), accept_2xx=True)
    judge("types", "PUT types 100", c.put(PT, json={"types": [{"key": f"k{i}", "label": f"l{i}"} for i in range(100)]}))
    judge("types", "PUT types restore default-ish", c.put(PT, json={"types": [{"key": "smart", "label": "스마트과제"}]}), accept_2xx=True)
    pid2 = c.post("/api/projects", json={"title": "y", "type": "smart"}).json()["id"]
    judge("types", "PUT remove in-use type", c.put(PT, json={"types": [{"key": "other", "label": "기타"}]}))
    judge("types", "PUT rename in-use key label", c.put(PT, json={"types": [{"key": "smart", "label": "새이름"}]}), accept_2xx=True)
    # settings.json on disk corrupt → GET
    (vault / "settings.json").write_text("{not json", encoding="utf-8")
    judge("settings", "GET settings with corrupt settings.json", c.get(S), accept_2xx=True)
    judge("settings", "PUT settings with corrupt settings.json", c.put(S, json={"author": "복구"}), accept_2xx=True)
    print("settings.json now:", (vault / "settings.json").read_text()[:200])
    judge("settings", "GET meta with corrupt-then-fixed", c.get("/api/meta"), accept_2xx=True)
finish("p7_settings")
