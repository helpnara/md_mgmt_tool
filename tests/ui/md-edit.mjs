// 마크다운 편집 규칙 시험 (TODO 321) — frontend/src/mdEdit.ts 를 esbuild 로 묶어 node 로 돌린다.
// 사용: node tests/ui/md-edit.mjs   (화면 없이 몇 초)
import { createRequire } from "node:module";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const front = join(here, "..", "..", "frontend");
const require = createRequire(join(front, "package.json"));
const esbuild = require("esbuild");
const out = join(mkdtempSync(join(tmpdir(), "md-edit-")), "mdEdit.mjs");
await esbuild.build({ entryPoints: [join(front, "src", "mdEdit.ts")], bundle: true, format: "esm", outfile: out, logLevel: "silent" });
const md = await import(out);

let pass = 0, fail = 0;
const apply = (text, e) => text.slice(0, e.from) + e.insert + text.slice(e.to);
function eq(name, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (ok) pass += 1; else { fail += 1; console.log(`  ✗ ${name}\n      기대 ${JSON.stringify(want)}\n      실제 ${JSON.stringify(got)}`); }
}
/** "|" 로 커서, "[" "]" 로 고른 범위를 적은 글 → [글, 처음, 끝] */
function at(s) {
  if (s.includes("[")) { const a = s.indexOf("["); const b = s.indexOf("]") - 1; return [s.replace("[", "").replace("]", ""), a, b]; }
  const c = s.indexOf("|"); return [s.replace("|", ""), c, c];
}
function show(text, e) { const t = apply(text, e); return t.slice(0, e.selStart) + (e.selStart === e.selEnd ? "|" : "[" + t.slice(e.selStart, e.selEnd) + "]") + t.slice(e.selEnd); }

// 서식 걸기 · 풀기
let [t, s, e] = at("가나 [다라] 마");
eq("굵게 걸기", show(t, md.toggleWrap(t, s, e, "**")), "가나 **[다라]** 마");
[t, s, e] = at("가나 **[다라]** 마");
eq("굵게 풀기(바깥 표시)", show(t, md.toggleWrap(t, s, e, "**")), "가나 [다라] 마");
[t, s, e] = at("가나 [**다라**] 마");
eq("굵게 풀기(고른 글 안 표시)", show(t, md.toggleWrap(t, s, e, "**")), "가나 [다라] 마");
[t, s, e] = at("가[나다 ]라");
eq("앞뒤 빈칸은 표시 밖", show(t, md.toggleWrap(t, s, e, "**")), "가**[나다]** 라");
[t, s, e] = at("가|나");
eq("고른 것 없으면 자리 글", show(t, md.toggleWrap(t, s, e, "~~")), "가~~[글]~~나");
[t, s, e] = at("가 **[나]** 다");
eq("굵게 안의 기울임은 굵게를 안 푼다", show(t, md.toggleWrap(t, s, e, "*")), "가 ***[나]*** 다");

// 줄 앞 표시
[t, s, e] = at("[가\n나\n\n다]");
eq("번호 목록 — 1. 2. 3. 다시 셈, 빈 줄 그대로", apply(t, md.toggleLine(t, s, e, "number")), "1. 가\n2. 나\n\n3. 다");
[t, s, e] = at("[- 가\n- 나]");
eq("글머리 목록 풀기", apply(t, md.toggleLine(t, s, e, "bullet")), "가\n나");
[t, s, e] = at("[- 가\n  - 나]");
eq("글머리 → 할 일(들여쓰기 그대로)", apply(t, md.toggleLine(t, s, e, "task")), "- [ ] 가\n  - [ ] 나");
[t, s, e] = at("## 제|목");
eq("제목2 → 제목1 갈아 끼우기", apply(t, md.toggleLine(t, s, e, "h1")), "# 제목");
[t, s, e] = at("인|용");
eq("인용", apply(t, md.toggleLine(t, s, e, "quote")), "> 인용");

// 목록에서 Enter
[t] = at("1. 가나|");
eq("번호 다음", show(t, md.enterInList(t, t.length)), "1. 가나\n2. |");
t = "- [x] 했음";
{ const e1 = md.enterInList(t, t.length); eq("할 일 다음은 빈 칸", [apply(t, e1), e1.selStart], ["- [x] 했음\n- [ ] ", t.length + 7]); }
[t] = at("- 가\n  - |");
eq("겹친 빈 항목 → 한 단계 위로", show(t, md.enterInList(t, t.length)), "- 가\n- |");
[t] = at("- 가\n- |");
eq("맨 위 빈 항목 → 표시 지움", show(t, md.enterInList(t, t.length)), "- 가\n|");
eq("목록이 아니면 null", md.enterInList("보통 글", 5), null);
[t, s] = at("- 가|나");
eq("글 가운데서 Enter — 뒤 글이 새 항목으로", show(t, md.enterInList(t, s)), "- 가\n- |나");

// 들여쓰기 · 내어쓰기
[t, s] = at("1. 가\n- |나");
eq("번호 아래는 세 칸", apply(t, md.shiftLines(t, s, s, true)), "1. 가\n   - 나");
[t, s] = at("1. 가\n2. |나");
eq("번호를 들이면 그 단계 1. 부터", apply(t, md.shiftLines(t, s, s, true)), "1. 가\n   1. 나");
[t, s] = at("1. 가\n   1. |나");
eq("내어 쓰면 위 번호 + 1", apply(t, md.shiftLines(t, s, s, false)), "1. 가\n2. 나");
[t, s] = at("- 가\n- |나");
eq("글머리 아래는 두 칸", apply(t, md.shiftLines(t, s, s, true)), "- 가\n  - 나");
[t, s] = at("- 가\n  - |나");
eq("내어쓰기", apply(t, md.shiftLines(t, s, s, false)), "- 가\n- 나");

// 표 · 링크
[t] = at("|");
eq("표 넣기", apply(t, md.insertTable(t, 0, 2, 2)), "| 제목1 | 제목2 |\n| --- | --- |\n|    |    |\n");
[t, s, e] = at("[사이트]");
eq("링크 — 주소 자리를 고름", show(t, md.insertLink(t, s, e)), "[사이트]([https://])");

// 줄바꿈 고치기
eq("U+2028 · 줄 앞 붙는 빈칸", md.repairLineBreaks("가\u2028\u00a0 - 나\u2029다 \u00a0라"), "가\n  - 나\n다 \u00a0라");
eq("고칠 것 없으면 null", md.repairLineBreaks("가\n나"), null);

// 눌린 모습
eq("커서가 굵게 안", md.activeAt("가 **나다** 라", 5).wraps, ["**"]);
eq("줄 종류", md.activeAt("- [ ] 할 일", 3).line, "task");

console.log(`\n마크다운 편집 규칙 ${pass}건 통과, ${fail}건 실패`);
process.exit(fail ? 1 : 0);
