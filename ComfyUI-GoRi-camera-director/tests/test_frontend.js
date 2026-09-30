/**
 * 프론트엔드 api_key 보호 로직 실행 테스트 (GoRi Camera Director)
 *
 * 왜(Why) 이 파일이 있는가: api_key 유출 방지는 대개 서버(Python) 쪽에서
 * 검증되고, **화면 가림·저장 직렬화·페이로드 가드는 JS 에만 있다**. 그 JS 는
 * 2026-09-30 기준 테스트가 하나도 없었고, 그래서 보호가 "있어 보인다"만 하고
 * 실제로 도는지 아무도 확인하지 못했다. 이 파일은 소스를 그대로 로드해
 * **진짜 실행**해서 확인한다.
 *
 * 검증하는 세 가지 공유 경로:
 *   1) 워크플로우 파일 공유  → hookSerializeBlankApiKey
 *   2) 이미지로 워크플로우 공유 → 위 직렬화 + 서버 scrub
 *   3) 화면 녹화·방송       → maskApiKeyWidget (_displayValue) + password
 *
 * 실행: node tests/test_frontend.js  [web JS 경로]
 * node 가 없으면 Python 테스트가 이 파일을 건너뛴다(설치 강제하지 않음).
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const JS_PATH = process.argv[2] || path.join(HERE, "..", "web",
                                           "progressive_image_inputs.js");

let PASS = 0;
let FAIL = 0;
function check(name, ok, extra = "") {
  if (ok) {
    PASS++;
    console.log("  PASS  " + name);
  } else {
    FAIL++;
    console.log("  FAIL  " + name + (extra ? "  -> " + extra : ""));
  }
}

/* --------------------------------------------------------------------------
 * 실제 소스를 그대로 실행한다.
 *
 * 왜 이렇게 하나: 소스를 복사해 재구성하면 "원본과 테스트가 다르다"는
 *Cls 안내가 생기고, 어느 쪽이 썼는지 알 수 없게 된다. 여기서는 import 한 줄
 *만 스텁으로 바꿔 붙이고 나머지는 100% 원본 바이트다. 함수를 하나 지우면
 * export 에서 깨져 테스트가 즉시 실패한다(문자열 검사로는 못 잡는 종류).
 * ------------------------------------------------------------------------ */
function loadRealModule() {
  let src = fs.readFileSync(JS_PATH, "utf8");
  const importLine = src.match(/^import \{ app \} from "[^"]+";$/m);
  if (!importLine) throw new Error("app import 줄을 찾지 못함 (형식 바뀜)");
  src = src.replace(importLine[0], "const app = globalThis.__goriAppStub;");
  src += "\nexport { findApiKeyWidget, maskApiKeyWidget, "
      + "clearApiKeyWidget, hookSerializeBlankApiKey, "
      + "hookApiKeyPayloadGuard };\n";
  const tmp = path.join(HERE, ".gori_frontend_under_test.mjs");
  fs.writeFileSync(tmp, src, "utf8");
  return import("file://" + tmp.replace(/\\/g, "/") + "?t=" + Date.now());
}

/* --- ComfyUI 전역 스텁 ---------------------------------------------------- */
const apiKeyRequests = [];
let dirtyCalls = 0;
globalThis.__goriAppStub = {
  api: { addEventListener() {} },
  canvas: { setDirty() { dirtyCalls++; } },
  graph: { _nodes: [] },
  registerExtension() {},
};
let fetchCalls = [];
globalThis.fetch = (url, opts) => {
  fetchCalls.push({ url, body: opts && opts.body });
  return Promise.resolve({ ok: true });
};
/* 소스 최상위에서 window.addEventListener("wheel") 를 등록한다(테마 스크롤
 * 억제). node 에는 브라우저 전역이 없으니 등록만 받는 스텁을 둔다. */
globalThis.window = { addEventListener() {} };

/* --- 최소 위젯/노드 doubles ------------------------------------------------ */
function mkWidget(name, value, opts = {}) {
  const w = { name, value, type: opts.type || "text", computedDisabled: !!opts.disabled };
  if (opts.noSerializeValue === false) delete w.serializeValue;
  return w;
}

function mkNode(widgets, opts = {}) {
  const node = {
    widgets,
    outputs: opts.outputs || [],
    size: [300, 200],
    _goriImageTemplate: null,
  };
  node.serialize = function () {
    const values = [];
    for (const w of this.widgets || []) {
      if (w && w.serialize === false) continue;
      values.push(w && w.value !== undefined ? w.value : null);
    }
    const named = {};
    for (const w of this.widgets || []) named[w.name] = w.value;
    return { id: opts.id ?? 285, type: opts.type || "GoRi_CameraDirectorEncodeSkills",
             widgets_values: values, widgets_values_named: named };
  };
  return node;
}

const KEY = "sk-or-v1-" + "a".repeat(64);

console.log("-- F1: api_key 캔버스 마스킹 (화면 녹화·방송 경로) --");
const mod = await loadRealModule();

const w1 = mkWidget("api_key", KEY);
const n1 = mkNode([mkWidget("topic", "고양이"), w1, mkWidget("model", "space-bunny-alpha")]);
mod.maskApiKeyWidget(n1);
check("F1: 표시값이 마스크로 바뀜", w1._displayValue === "●●●●●●●●", w1._displayValue);
check("F1: 실행용 value 는 원본 그대로 (가린 게 아니라 표시만)",
      w1.value === KEY);
check("F1: 키 길이를 노출하지 않음 (고정 8자)",
      w1._displayValue.length === 8);
check("F1: 다른 위젯은 안 가림", n1.widgets[0]._displayValue === undefined);
check("F1: 캔버스 다시 그리기 요청", dirtyCalls > 0);

const wEmpty = mkWidget("api_key", "");
const nEmpty = mkNode([wEmpty]);
mod.maskApiKeyWidget(nEmpty);
check("F1: 빈 값은 빈 표시 (키 없음이 드러남)", wEmpty._displayValue === "");

const wDisabled = mkWidget("api_key", KEY, { disabled: true });
const nDisabled = mkNode([wDisabled]);
mod.maskApiKeyWidget(nDisabled);
check("F1: 비활성 위젯은 표시하지 않음", wDisabled._displayValue === "");

mod.maskApiKeyWidget(n1);
check("F1: 두 번 걸어도 중복 후킹 없음", w1._goriMasked === true);
mod.maskApiKeyWidget({ widgets: [] });
mod.maskApiKeyWidget(null);
check("F1: 위젯 없음/노드 null 에서 예외 없이 통과", true);

console.log("-- F2: 편집 다이얼로그 가림 + .env 동기화 --");
function mkPromptBox(withButton = true) {
  const listeners = {};
  const input = {
    type: "text", value: KEY,
    addEventListener(ev, fn) { (listeners[ev] = listeners[ev] || []).push(fn); },
  };
  const box = {
    _listeners: listeners,
    querySelector(sel) {
      if (sel === "input.value") return input;
      if (sel === "button" && withButton) {
        return { addEventListener(ev, fn) { (listeners[ev] = listeners[ev] || []).push(fn); } };
      }
      return null;
    },
  };
  box.input = input;
  return box;
}

const w2 = mkWidget("api_key", KEY);
w2.onClick = function () { return "orig-return"; };
const wProv = mkWidget("provider", "OpenRouter");
const n2 = mkNode([wProv, w2]);
mod.maskApiKeyWidget(n2);
const box2 = mkPromptBox();
const ret2 = w2.onClick({ canvas: { prompt_box: box2 } });
check("F2: 원래 onClick 반환값 보존", ret2 === "orig-return");
check("F2: 입력창이 password 로 바뀜 (입력 중 노출 방지)",
      box2.input.type === "password");
fetchCalls = [];
box2._listeners.click[0]();
check("F2: OK 클릭 → .env 동기화 요청 1건", fetchCalls.length === 1);
check("F2: provider 기준으로 전송",
      fetchCalls[0].url === "/gori_api_key"
      && JSON.parse(fetchCalls[0].body).provider === "OpenRouter");
check("F2: 키 본문 그대로 전송 (마스크 아님)",
      JSON.parse(fetchCalls[0].body).key === KEY);
fetchCalls = [];
box2._listeners.keydown.forEach((fn) => fn({ key: "Enter" }));
check("F2: Enter 확정도 동기화", fetchCalls.length === 1);
fetchCalls = [];
box2._listeners.keydown.forEach((fn) => fn({ key: "Escape" }));
check("F2: Esc 는 동기화 안 함 (취소)", fetchCalls.length === 0);
box2.input.value = "";
fetchCalls = [];
box2._listeners.click[0]();
check("F2: 빈 값 확정은 삭제 (.env 에서 키 제거)",
      fetchCalls.length === 1 && JSON.parse(fetchCalls[0].body).key === "");

const wNoFn = mkWidget("api_key", KEY);
const nNoFn = mkNode([wNoFn]);
mod.maskApiKeyWidget(nNoFn);
check("F2: onClick 없는 위젯도 마스킹은 적용", wNoFn._displayValue === "●●●●●●●●");

console.log("-- F3: 워크플로우 저장 시 api_key 제외 (파일 공유 경로) --");
const w3 = mkWidget("api_key", KEY);
const wTopic = mkWidget("topic", "창가 고양이");
const wModel = mkWidget("model", "space-bunny-alpha");
const n3 = mkNode([wTopic, wModel, w3], { id: 285 });
mod.hookSerializeBlankApiKey(n3);
const ser = n3.serialize();
check("F3: widgets_values_named.api_key 가 빈칸",
      ser.widgets_values_named.api_key === "");
check("F3: 위치 배열의 키도 빈칸",
      ser.widgets_values[2] === "", JSON.stringify(ser.widgets_values));
check("F3: topic 값은 보존", ser.widgets_values_named.topic === "창가 고양이");
check("F3: model 값은 보존", ser.widgets_values_named.model === "space-bunny-alpha");
check("F3: 직렬화 전체에 키 문자열 없음", !JSON.stringify(ser).includes(KEY));
check("F3: live value 는 그대로 (실행은 정상)", w3.value === KEY);

const skipW = mkWidget("image_1", null);
skipW.serialize = false;
const w4 = mkWidget("api_key", KEY);
const n4 = mkNode([mkWidget("topic", "t"), skipW, w4], { id: 7 });
mod.hookSerializeBlankApiKey(n4);
const ser4 = n4.serialize();
check("F3: serialize:false 위젯을 코어와 동일하게 건너뛰고 위치 계산",
      ser4.widgets_values_named.api_key === "" && ser4.widgets_values[1] === "",
      JSON.stringify(ser4.widgets_values));

const n5 = mkNode([mkWidget("api_key", KEY)], { id: 9 });
mod.hookSerializeBlankApiKey(n5);
const first = n5.serialize;
mod.hookSerializeBlankApiKey(n5);
check("F3: 두 번 걸어도 후킹 중첩 없음", n5.serialize === first);
mod.hookSerializeBlankApiKey({ widgets: [] });
mod.hookSerializeBlankApiKey(null);
mod.hookSerializeBlankApiKey({ widgets: [mkWidget("api_key", KEY)] });
check("F3: serialize 없는 노드에서도 예외 없이 통과", true);

console.log("-- F4: 실행 페이로드 가드 (방치 노드 키 미전송) --");
const w5 = mkWidget("api_key", KEY);
const nLoose = mkNode([w5], { outputs: [{ links: null }, { links: null }] });
mod.hookApiKeyPayloadGuard(nLoose);
check("F4: 출력 미연결 노드는 키를 보내지 않음",
      nLoose.widgets[0].serializeValue() === "");
check("F4: 그래도 live value 는 유지 (뮤트 해제 시 즉시 복구)",
      nLoose.widgets[0].value === KEY);

const w6 = mkWidget("api_key", KEY);
const nLinked = mkNode([w6], { outputs: [{ links: [3] }, { links: null }] });
mod.hookApiKeyPayloadGuard(nLinked);
check("F4: 출력 연결 노드는 실값 그대로 (정상 실행)",
      nLinked.widgets[0].serializeValue() === KEY);

const w7 = mkWidget("api_key", KEY);
const nNoOut = mkNode([w7], { outputs: [] });
mod.hookApiKeyPayloadGuard(nNoOut);
check("F4: 출력 배열이 비면 실값 (과잉 보호로 실행 안 깨지게)",
      nNoOut.widgets[0].serializeValue() === KEY);

mod.hookApiKeyPayloadGuard({ widgets: [] });
check("F4: 위젯 없음에서 예외 없이 통과", true);

console.log("-- F5: 공유용 수동 지우기 --");
const w8 = mkWidget("api_key", KEY);
const n8 = mkNode([w8]);
check("F5: 값이 있으면 비우고 true", mod.clearApiKeyWidget(n8) === true
      && w8.value === "");
check("F5: 이미 빈 값이면 false (메뉴 비활성화용)",
      mod.clearApiKeyWidget(n8) === false);
check("F5: 위젯 없음이면 false", mod.clearApiKeyWidget({ widgets: [] }) === false);
check("F5: null 노드에도 false", mod.clearApiKeyWidget(null) === false);

console.log("-- F6: 실패해도 조용히 죽지 않는가 --");
const boomNode = mkNode([mkWidget("api_key", KEY)]);
boomNode.serialize = function () { return null; };
mod.hookSerializeBlankApiKey(boomNode);
check("F6: serialize 가 null 을 돌려도 예외 없이 통과",
      boomNode.serialize() === null);
const frozen = Object.freeze(mkNode([mkWidget("api_key", KEY)]));
mod.hookSerializeBlankApiKey(frozen);
mod.maskApiKeyWidget(frozen);
check("F6: 동결된 노드에서도 예외 없이 통과", true);

try {
  fs.unlinkSync(path.join(HERE, ".gori_frontend_under_test.mjs"));
} catch (_) { /* 임시파일 정리는 무시 */ }

console.log("");
console.log("  합계: PASS=" + PASS + "  FAIL=" + FAIL);
process.exit(FAIL ? 1 : 0);
