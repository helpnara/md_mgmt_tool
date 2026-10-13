// 빌드 결과(dist/assets)의 JS · CSS 를 gzip 으로 한 벌 더 둔다 (TODO 190).
// 서버가 브라우저의 Accept-Encoding 을 보고 .gz 를 그대로 보낸다 — 요청마다 압축하지 않는다.
import { readdirSync, readFileSync, writeFileSync, statSync } from "node:fs";
import { gzipSync } from "node:zlib";
import { join } from "node:path";
const dir = new URL("../dist/assets/", import.meta.url).pathname;
for (const name of readdirSync(dir)) {
  if (!/\.(js|css)$/.test(name)) continue;
  const raw = readFileSync(join(dir, name));
  const gz = gzipSync(raw, { level: 9 });
  writeFileSync(join(dir, name + ".gz"), gz);
  console.log(`${name}: ${Math.round(statSync(join(dir, name)).size / 1024)}KB → ${Math.round(gz.length / 1024)}KB`);
}
