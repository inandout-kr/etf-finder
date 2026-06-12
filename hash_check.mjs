// JS FNV-1a가 Python 빌드와 동일한 샤드를 가리키는지 검증
import { readFileSync } from "fs";

function fnv1a(s) {
  const b = new TextEncoder().encode(s);
  let h = 2166136261;
  for (const x of b) { h ^= x; h = Math.imul(h, 16777619) >>> 0; }
  return h >>> 0;
}

const tests = ["삼성전자", "한미반도체", "NVIDIA CORP", "삼성전자우", "AT&T INC", "2026-07 한미반도체개별선물"];
let ok = 0;
for (const name of tests) {
  const sh = (fnv1a(name) % 256).toString(16).padStart(2, "0");
  const shard = JSON.parse(readFileSync(`dist/shard/${sh}.json`, "utf-8"));
  const found = name in shard;
  console.log(`${found ? "OK " : "FAIL"} shard=${sh} ${name}${found ? " -> " + shard[name].length + " ETFs" : ""}`);
  if (found) ok++;
}
process.exit(ok === tests.length ? 0 : 1);
