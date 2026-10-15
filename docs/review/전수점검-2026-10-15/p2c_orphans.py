from harness import *
import unicodedata

def judge(name, req, r, expect_4xx=True, extra=""):
    st = r.status_code
    if st >= 500:
        rec(name, req, r, "PROBLEM", "500 " + extra, "⛔")
    elif st >= 400:
        d = detail(r)
        if st == 422:
            rec(name, req, r, "note", "422 english: " + d[:90] + extra)
        elif not is_korean(d):
            rec(name, req, r, "PROBLEM", "non-Korean msg " + d[:80], "🟡")
        else:
            rec(name, req, r, "ok", d[:80] + extra)
    else:
        rec(name, req, r, "ok" if not expect_4xx else "note", f"{st} accepted " + extra)
    return r

with fresh(keep=True) as (c, vault):
    P = "/api/projects"
    # names
    for title in ["", "   ", "\t\n", 'a/b\\c:d*e?f"g<h>i|j', "끝점.", "끝공백 ", "CON", "PRN", "NUL", "COM1", "con.txt", "x" * 300,
                  "😀 이모지 과제", unicodedata.normalize("NFD", "한글과제"), "...", "---", "___", "  양쪽  공백  ", "a\x00b", "​", "ﾊﾝｶｸ 半角 全角"]:
        r = c.post(P, json={"title": title})
        if r.status_code == 201:
            pid = r.json()["id"]
            got = c.get(f"{P}/{pid}").json()
            dn = got["dir_name"]
            fs = project_dirs(vault)
            ok_fs = dn in fs
            rec("create-title", f"POST {P} title={title!r}", r, "ok" if ok_fs else "PROBLEM",
                f"id={pid} dir={dn!r} title_back={got['title']!r} in_fs={ok_fs}", "" if ok_fs else "🔴")
        else:
            judge("create-title", f"POST {P} title={title!r}", r)
    # duplicates
    r1 = c.post(P, json={"title": "중복 과제"}); r2 = c.post(P, json={"title": "중복 과제"}); r3 = c.post(P, json={"title": "중복 과제".upper()})
    r4 = c.post(P, json={"title": "Dup Name"}); r5 = c.post(P, json={"title": "dup name"})
    rec("create-dup", "same title twice", r2, "note", f"{r1.status_code},{r2.status_code} — duplicates allowed (ids differ: {r1.json().get('id')} / {r2.json().get('id')})")
    rec("create-dup", "case-different title", r5, "note", f"{r4.status_code},{r5.status_code} dirs={[d for d in project_dirs(vault) if 'Dup' in d or 'dup' in d]}")
    # dates
    for sd, dd, cd in [("2026-03-01", "2026-01-01", None), ("2026-13-01", None, None), ("2026/01/01", None, None), ("", "", ""),
                       ("2025-12-31", "2026-01-01", None), ("2026-1-1", None, None), ("20260101", None, None), ("2026-02-30", None, None),
                       (None, None, "2026-13-40"), ("0001-01-01", None, None), ("9999-12-31", None, None), ("2026-01-01T00:00:00", None, None),
                       (" 2026-01-01 ", None, None), ("2026-W01", None, None)]:
        body = {"title": f"날짜 {sd} {dd} {cd}", "start_date": sd, "due_date": dd, "completed_at": cd}
        r = c.post(P, json=body)
        if r.status_code == 201:
            got = c.get(f"{P}/{r.json()['id']}").json()
            rec("create-dates", f"POST start={sd!r} due={dd!r} done={cd!r}", r, "note", f"accepted → id={got['id']} start={got['start_date']} due={got['due_date']} completed={got.get('completed_at')}")
        else:
            judge("create-dates", f"POST start={sd!r} due={dd!r} done={cd!r}", r)
    # effects
    for ev in [-1, 1e308, "abc", "1,000", float("nan") if False else "nan", "inf", "", None, 0, 1e-300, 12345678901234567890]:
        r = c.post(P, json={"title": f"효과 {ev}", "effect_expected": ev, "effect_verified": ev})
        if r.status_code == 201:
            got = c.get(f"{P}/{r.json()['id']}").json()
            rec("create-effect", f"effect_expected={ev!r}", r, "note", f"accepted → stored {got['effect_expected']!r}/{got['effect_verified']!r}")
        else:
            judge("create-effect", f"effect_expected={ev!r}", r)
    # raw JSON with NaN / Infinity
    for raw in ['{"title":"nan","effect_expected":NaN}', '{"title":"inf","effect_expected":Infinity}', '{"title":"big","effect_expected":1e999}']:
        r = c.post(P, content=raw, headers={"content-type": "application/json"})
        judge("create-effect-raw", raw, r)
    # status/type
    for st, ty in [("bogus", None), (None, "bogus"), ("", ""), ("DONE", None), (None, "SMART"), ("plan_report", None), ("proposal", None)]:
        r = c.post(P, json={"title": f"상태 {st} {ty}", "status": st, "type": ty})
        if r.status_code == 201:
            got = c.get(f"{P}/{r.json()['id']}").json()
            rec("create-status", f"status={st!r} type={ty!r}", r, "note", f"accepted → status={got['status']} type={got['type']}")
        else:
            judge("create-status", f"status={st!r} type={ty!r}", r)
    # owners
    for owners in [["김철수", "김철수"], ["", " ", "김철수"], [f"사람{i}" for i in range(100)], ["a, b"], ["x" * 500], ["../x"], [None] if False else ["권경락 책임"]]:
        r = c.post(P, json={"title": "담당자", "owners": owners})
        if r.status_code == 201:
            got = c.get(f"{P}/{r.json()['id']}").json()
            rec("create-owners", f"owners={str(owners)[:60]}", r, "note", f"stored owners={str(got['owners'])[:120]} n={len(got['owners'])}")
        else:
            judge("create-owners", f"owners={str(owners)[:60]}", r)
    r = c.post(P, json={"title": "담당자", "owners": "홍길동"}); judge("create-owners", "owners='홍길동' (string)", r)
    r = c.post(P, json={"title": "담당자", "owners": [1, 2]}); judge("create-owners", "owners=[1,2]", r)
    # tags
    for tags in [["a,b", "c d"], ["#태그"], [""], ["x" * 300], ["a", "a"], ["태그/슬래시", "콜론:태그"]]:
        r = c.post(P, json={"title": "태그", "tags": tags})
        if r.status_code == 201:
            got = c.get(f"{P}/{r.json()['id']}").json()
            rec("create-tags", f"tags={tags}", r, "note", f"stored tags={got['tags']}")
            m = c.get("/api/meta").json()
        else:
            judge("create-tags", f"tags={tags}", r)
    # partners odd
    for partners in [[{"team": "", "people": ""}], [{"team": "팀", "people": "a, b"}], [{"team": "팀", "people": ["a", "a"]}], [{"team": "x" * 400, "people": []}], [{"team": "팀"}] * 3]:
        r = c.post(P, json={"title": "유관", "partners": partners})
        if r.status_code == 201:
            got = c.get(f"{P}/{r.json()['id']}").json()
            rec("create-partners", f"partners={str(partners)[:60]}", r, "note", f"stored={str(got['partners'])[:120]}")
        else:
            judge("create-partners", f"partners={str(partners)[:60]}", r)
    # predecessors
    a = c.post(P, json={"title": "A선행"}).json()["id"]
    b = c.post(P, json={"title": "B후속", "predecessors": [a]}).json()["id"]
    judge("predecessor", f"PATCH {a} predecessors=[{a}] (self)", c.patch(f"{P}/{a}", json={"predecessors": [a]}))
    judge("predecessor", f"PATCH {a} predecessors=[{b}] (cycle)", c.patch(f"{P}/{a}", json={"predecessors": [b]}))
    judge("predecessor", "POST predecessors=['2099-999'] (missing)", c.post(P, json={"title": "C", "predecessors": ["2099-999"]}))
    judge("predecessor", "POST predecessors=[''] ", c.post(P, json={"title": "C", "predecessors": [""]}))
    judge("predecessor", "POST predecessors=['../x']", c.post(P, json={"title": "C", "predecessors": ["../x"]}))
    cc = c.post(P, json={"title": "C후후속", "predecessors": [b]}).json()["id"]
    judge("predecessor", f"PATCH {a} predecessors=[{cc}] (3-cycle)", c.patch(f"{P}/{a}", json={"predecessors": [cc]}))
    r = c.post(P, json={"title": "D", "predecessors": [a, a]}); 
    if r.status_code == 201:
        rec("predecessor", "POST predecessors=[a,a] dup", r, "note", f"stored={c.get(P+'/'+r.json()['id']).json().get('predecessors')}")
    # roadmap + folder sanity after cycle attempts
    judge("roadmap", "GET /api/roadmap after predecessor attempts", c.get("/api/roadmap"), expect_4xx=False)
    # PATCH edge: rename to empty / title with slash → dir rename
    pid = c.post(P, json={"title": "이름바꾸기"}).json()["id"]
    judge("patch-title", "PATCH title=''", c.patch(f"{P}/{pid}", json={"title": ""}))
    judge("patch-title", "PATCH title='   '", c.patch(f"{P}/{pid}", json={"title": "   "}))
    r = c.patch(f"{P}/{pid}", json={"title": "NUL"}); judge("patch-title", "PATCH title='NUL'", r, expect_4xx=False)
    got = c.get(f"{P}/{pid}").json(); rec("patch-title", "dir after rename to NUL", r, "ok" if got["dir_name"] in project_dirs(vault) else "PROBLEM", f"dir={got['dir_name']}")
    judge("patch-dates", "PATCH start>due", c.patch(f"{P}/{pid}", json={"start_date": "2026-05-01", "due_date": "2026-01-01"}))
    judge("patch-dates", "PATCH completed_at with status in_progress", c.patch(f"{P}/{pid}", json={"completed_at": "2026-01-01"}), expect_4xx=False)
    judge("patch-dates", "PATCH status=done completed_at=''", c.patch(f"{P}/{pid}", json={"status": "done", "completed_at": ""}), expect_4xx=False)
    print("after:", c.get(f"{P}/{pid}").json().get("completed_at"), c.get(f"{P}/{pid}").json().get("status"))
    judge("patch-effect", "PATCH effect_expected=null", c.patch(f"{P}/{pid}", json={"effect_expected": None}), expect_4xx=False)
    judge("patch-effect", "PATCH effect_expected=-5", c.patch(f"{P}/{pid}", json={"effect_expected": -5}))
    judge("patch-unknown", "PATCH unknown field", c.patch(f"{P}/{pid}", json={"zzz": 1}), expect_4xx=False)
    judge("patch-empty", "PATCH {}", c.patch(f"{P}/{pid}", json={}), expect_4xx=False)
    judge("patch-raw", "PATCH body=[]", c.patch(f"{P}/{pid}", json=[]))
    judge("patch-raw", "PATCH body='x'", c.patch(f"{P}/{pid}", content=b"x", headers={"content-type": "application/json"}))
    judge("patch-raw", "PATCH body=null", c.patch(f"{P}/{pid}", content=b"null", headers={"content-type": "application/json"}))
    judge("create-raw", "POST body=null", c.post(P, content=b"null", headers={"content-type": "application/json"}))
    judge("create-raw", "POST no body", c.post(P))
    judge("create-raw", "POST 5MB body", c.post(P, json={"title": "big", "body": "x" * 5_000_000}), expect_4xx=False)
    # next-id with odd start_date
    for sd in ["2026-13-01", "abc", "0000-01-01", "99999-01-01", "'; DROP"]:
        judge("next-id", f"GET next-id?start_date={sd}", c.get(f"{P}/next-id", params={"start_date": sd}), expect_4xx=False)
    # status log / year-fix
    judge("year-fix", "GET year-fix", c.get(f"{P}/{pid}/year-fix"), expect_4xx=False)
    judge("year-fix", "POST year-fix (no change needed)", c.post(f"{P}/{pid}/year-fix"), expect_4xx=False)
    judge("clone", "GET clone", c.get(f"{P}/{pid}/clone"), expect_4xx=False)
    judge("to-intake", "GET to-intake plan", c.get(f"{P}/{pid}/to-intake"), expect_4xx=False)
    # archive twice
    judge("archive", "POST archive", c.post(f"{P}/{pid}/archive"), expect_4xx=False)
    judge("archive", "POST archive twice", c.post(f"{P}/{pid}/archive"))
    judge("archive", "GET after archive", c.get(f"{P}/{pid}"))
    judge("archive", "PATCH after archive", c.patch(f"{P}/{pid}", json={"title": "x"}))
    # consistency
    n_db = len(c.get(P, params={"status": ""}).json())
    all_rows = c.get(P).json()
    fs = project_dirs(vault)
    rec("consistency", "projects count vs folders", 200, "ok" if len(all_rows) == len(fs) else "PROBLEM", f"api={len(all_rows)} fs={len(fs)}", "🔴")
    ri = c.post("/api/reindex").json()
    rec("consistency", "reindex count", 200, "ok" if ri["indexed"] == len(fs) else "PROBLEM", f"reindex={ri['indexed']} fs={len(fs)} problems={ri['problems']}", "🔴")
    api_ids={p["id"] for p in c.get(P).json()}; print("ORPHAN DIRS:", [d for d in project_dirs(vault) if d[:8] not in api_ids]); print("API-only:", sorted(api_ids - {d[:8] for d in project_dirs(vault)})); print("VAULT", vault)
finish("p2c")
