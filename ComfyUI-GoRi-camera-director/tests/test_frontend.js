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
/* 소켓 템플릿 정의 — 실제 노드 정의를 흉내 낸다 (image_1~3).
 * 3개만 둔다: 테스트는 "몇 칸이 필요한가" 를 세는 로직만 본다. */
const LIFECYCLE_NODE_DEF = {
  name: "GoRi_CameraDirectorEncodeSkills",
  input: {
    optional: {
      image_1: ["IMAGE", {}],
      image_2: ["IMAGE", {}],
      image_3: ["IMAGE", {}],
    },
  },
};

function loadRealModule() {
  let src = fs.readFileSync(JS_PATH, "utf8");
  const importLine = src.match(/^import \{ app \} from "[^"]+";$/m);
  if (!importLine) throw new Error("app import 줄을 찾지 못함 (형식 바뀜)");
  src = src.replace(importLine[0], "const app = globalThis.__goriAppStub;");
  // 소스 자체가 export 하고 있으면 덧붙이지 않는다(이미 있으면 SyntaxError).
  // 2026-10-02: 소스에 명시적 export 블록을 넣은 뒤 이 중복이 났다.
  if (!/^\s*export\s*\{/m.test(src)) {
    src += "\nexport { findApiKeyWidget, maskApiKeyWidget, "
        + "clearApiKeyWidget, hookSerializeBlankApiKey, "
        + "hookApiKeyPayloadGuard };\n";
  }
  const tmp = path.join(HERE, ".gori_frontend_under_test.mjs");
  fs.writeFileSync(tmp, src, "utf8");
  return import("file://" + tmp.replace(/\\/g, "/") + "?t=" + Date.now());
}

/* --- ComfyUI 전역 스텁 ---------------------------------------------------- */
const apiKeyRequests = [];
let dirtyCalls = 0;
/* 그래프 노드 목록을 테스트가 직접 만진다 — 소켓 갱신이 "노드가 아직 있는가"
 * 를 여기서 확인하므로(WeakMap 타이머 해제 후 안전망) 실제 배열이어야 한다. */
const graphNodes = [];
/* isDraggingLink() 가 읽는 경로. 링크 드래그 중일 때 비어 있지 않다. */
const linkConnector = { renderLinks: [] };
/* registerExtension 이 등록한 객체를 다시 꺼내 재등록 시나리오를 만든다. */
let capturedExtension = null;

globalThis.__goriAppStub = {
  api: { addEventListener() {} },
  canvas: { setDirty() { dirtyCalls++; }, linkConnector },
  graph: { _nodes: graphNodes },
  registerExtension(ext) { capturedExtension = ext; },
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

/* 표시등 드로잉이 ctx 를 어떻게 쓰는지 기록한다. */
function mkCtxRecorder() {
  const ops = [];
  const props = {};
  const ctx = {
    save() { ops.push("save"); },
    restore() { ops.push("restore"); },
    beginPath() { ops.push("beginPath"); },
    stroke() { ops.push("stroke"); },
    rect() { ops.push("rect"); },
    roundRect() { ops.push("roundRect"); },
  };
  for (const k of ["globalAlpha", "strokeStyle", "lineWidth", "shadowColor", "shadowBlur"]) {
    let v;
    Object.defineProperty(ctx, k, {
      get() { return v; },
      set(nv) { v = nv; props[k] = nv; },
    });
  }
  ctx.ops = ops;
  ctx.props = props;
  return ctx;
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

/* 표시등 드로잉 테스트용 노드.
 * model 위젯에 **y 좌표**가 있어야 그 줄에 표시등을 그린다(프런트엔드에서
 * 캔버스 위젯은 세로 위치가 있다). y 없이 두면 drawLlmLight 가 조용히
 * 아무것도 안 그리고 반환해서, 테스트가 "안 그려짐"을 통과로 오인한다. */
function makeNodeWithModel() {
  const w = mkWidget("model", "m");
  w.y = 40;
  const n = mkNode([w, mkWidget("api_key", "")]);
  n.size = [300, 200];
  return n;
}

/* 소켓 수명주기 테스트용 — 확장이 실제로 후킹하는 그 프로토타입을 쓴다.
 * (확장 모듈의 namespace 객체는 동결이라 헬퍼를 붙일 수 없다. 그래서
 *  beforeRegisterNodeDef 을 테스트 쪽에서 직접 부른다.)
 *
 * 확장은 nodeType.prototype 을 후킹하므로 nodeType 은 **클래스**여야 한다.
 * 우리가 검증하는 대상은 그 prototype 이다.
 *
 * baseCalls: 확장이 후킹하기 **전**의 순수 베이스가 실제로 불렸는지 센다.
 * "원본 보존"은 후킹 이후에야 의미가 있으므로 베이스를 미리 기록해 둔다. */
let lifecycleType = null;
let baseCalls = 0;
function ensurePatched() {
  if (!capturedExtension) throw new Error("registerExtension 이 호출되지 않음");
  if (!lifecycleType) {
    class FakeCameraDirector {}
    Object.assign(FakeCameraDirector.prototype, {
      onNodeCreated() {},
      onConfigure() {},
      onConnectionsChange() { baseCalls++; },
      getExtraMenuOptions() {},
    });
    lifecycleType = FakeCameraDirector;
    capturedExtension.beforeRegisterNodeDef(lifecycleType, LIFECYCLE_NODE_DEF);
  }
  return lifecycleType.prototype;
}
/* 프론트엔드가 노드 정의를 **재등록**하는 상황을 흉내낸다.
 * 같은 타입을 다시 넘겨 같은 prototype 을 다시 후킹하는 것이다.
 * (프런트엔드는 nodeType 자체를 새로 만들지만, 그 새 타입에도 같은
 *  beforeRegisterNodeDef 가 다시 불린다. 방치하면 매번 래퍼가 한 겹씩 쌓인다.) */
function reexecRegisterExtension() {
  ensurePatched();
  capturedExtension.beforeRegisterNodeDef(lifecycleType, LIFECYCLE_NODE_DEF);
}
function makeLifecycleNode() {
  const n = Object.create(ensurePatched());
  n.widgets = [mkWidget("topic", "t")];
  n.outputs = [];
  n.size = [300, 200];
  n.setSize = function (s) { this.size = s; };
  n.computeSize = function () { return [300, 120]; };
  return n;
}

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

console.log("-- F7: 소켓 판정은 빠진 입력을 견딘다 (2026-10-02) --");
// 왜(Why): inputs 배열에 null/구멍이 섞이면 `inp.name` 이 예외를 던진다.
// 예외는 updateVisibility 의 catch 에 걸려 Fail-safe(10칸 전부 복원)로
// 이어지므로 **조용히 소켓이 늘어나** 사용자는 이유를 모른다.
check("F7: null 소켓이 있어도 개수 계산",
      mod.countImageSockets({ inputs: [null, { name: "image_1" }, undefined] }) === 1);
check("F7: 빈 inputs 도 0",
      mod.countImageSockets({ inputs: [] }) === 0
      && mod.countImageSockets({}) === 0
      && mod.countImageSockets(null) === 0);
check("F7: null 소켓 뒤에서 마지막 연결 번호도 찾음",
      mod.lastLinkedImageNumber({
        inputs: [null, { name: "image_3", link: 1 }, undefined],
      }) === 3);
check("F7: null 소켓을 건너뛰고 뒤쪽 인덱스를 준다",
      mod.lastImageSocketIndex({
        inputs: [{ name: "image_1" }, null, { name: "image_2" }],
      }) === 2);
check("F7: image 소켓이 하나도 없으면 -1 (찾기 실패 규약)",
      mod.lastImageSocketIndex({ inputs: [{ name: "topic" }] }) === -1);
check("F7: name 이 없는 위젯도 예외를 내지 않음",
      mod.imageNumber(undefined) === 0 && mod.imageNumber("topic") === 0
      && mod.imageNumber("image_7") === 7);
check("F7: size 가 비어 있어도 크기 계산은 통과",
      mod.shrinkNewNode({ computeSize: () => [100, 50], size: undefined }) === undefined);

console.log("-- F8: LLM 상태 표는 상속값을 집어오지 않는다 (2026-10-02) --");
// 왜(Why): 상태 이름은 웹소켓 페이로드에서 온다. 일반 객체라
// state="toString" 이면 spec 가 **함수**가 되어 색이 undefined 로 그려진다.
const lln = makeNodeWithModel();
mod.applyLlmLight(lln, "toString");
check("F8: toString 을 상태로 받아도 표시등이 켜지지 않음",
      lln._goriLlmState === null, String(lln._goriLlmState));
mod.applyLlmLight(lln, "constructor");
check("F8: constructor 도 상태로 안 받음",
      lln._goriLlmState === null, String(lln._goriLlmState));
const llv = makeNodeWithModel();
mod.applyLlmLight(llv, "busy");
check("F8: 정상 상태는 그대로 반영",
      llv._goriLlmState === "busy", String(llv._goriLlmState));
const ctx8 = mkCtxRecorder();
llv.onDrawForeground(ctx8);
check("F8: 정상 상태는 지정된 색으로 그린다",
      ctx8.props.strokeStyle === "#35d07f", String(ctx8.props.strokeStyle));
check("F8: save/restore 로 감싸 그림 (ctx 오염 방지)",
      ctx8.ops[0] === "save" && ctx8.ops[ctx8.ops.length - 1] === "restore",
      ctx8.ops.join(","));
mod.applyLlmLight(llv, "unknown-state");
check("F8: 미등록 상태는 꺼짐으로 처리", llv._goriLlmState === null,
      String(llv._goriLlmState));
// 상속 키가 새 키로 새어나오지 않아야 한다(오염 방지)
mod.applyLlmLight(llv, "toString");
check("F8: 상속 키로 테이블이 오염되지 않음",
      mod.applyLlmLight(llv, "busy") === undefined
      && llv._goriLlmState === "busy", String(llv._goriLlmState));

console.log("-- F9: 디바운스가 한 번만 반영한다 (2026-10-02) --");
// 왜(Why): 코어는 링크를 하나씩 붙일 때마다 onConnectionsChange 를 부른다.
// 묶지 않으면 그 횟수만큼 입력 배열을 훑고 소켓을 더하거나 뺀다.
const n9 = makeLifecycleNode();
n9.inputs = [];
const calls9 = [];
n9.addInput = function (name) { this.inputs.push({ name }); calls9.push("add:" + name); };
n9.removeInput = function () { this.inputs.pop(); calls9.push("remove"); };
n9.size = [300, 200];
n9.setSize = function (s) { this.size = s; };
n9.addEventListener?.("change", () => {});
graphNodes.push(n9);
for (let i = 0; i < 5; i++) n9.onConnectionsChange("INPUT", i, true);
const before9 = calls9.length;
await new Promise((r) => setTimeout(r, mod.VISIBILITY_DEBOUNCE_MS + 120));
check("F9: 5회 연속 호출 → 갱신은 마지막에 1회만",
      calls9.length === before9 + 1,
      "before=" + before9 + " after=" + calls9.length
      + " [" + calls9.join(",") + "]");
check("F9: 1번 소켓만 노출 (연결 없으면 1칸)",
      n9.inputs.length === 1 && n9.inputs[0].name === "image_1",
      JSON.stringify(n9.inputs.map((x) => x.name)));

// 그래프에서 사라진 노드에는 아무것도 하지 않는다 (타이머 해제 후 안전)
const n9b = makeLifecycleNode();
n9b.inputs = [];
n9b.addInput = function () { throw new Error("removed node must not be touched"); };
n9b.removeInput = function () { throw new Error("removed node must not be touched"); };
graphNodes.push(n9b);
n9b.onConnectionsChange("INPUT", 0, true);
graphNodes.splice(graphNodes.indexOf(n9b), 1);
await new Promise((r) => setTimeout(r, mod.VISIBILITY_DEBOUNCE_MS + 120));
check("F9: 지워진 노드에는 소켓 갱신을 시도하지 않음", true);

console.log("-- F10: 드래그 중에는 소켓을 덜어내지 않는다 (2026-10-02) --");
// 왜(Why) 유지 검증: 이건 리팩터로 새로 넣은 게 아니라 **기존 안전장치**다.
// 경로만 바뀌었으므로 그대로 동작하는지 확인한다.
linkConnector.renderLinks = [{ id: 1 }];
const n10 = makeLifecycleNode();
n10.inputs = [];
n10.addInput = function (name) { this.inputs.push({ name }); };
n10.removeInput = function () { this.inputs.pop(); };
n10.size = [300, 200];
n10.setSize = function (s) { this.size = s; };
graphNodes.push(n10);
n10.onConnectionsChange("INPUT", 0, true);
await new Promise((r) => setTimeout(r, mod.VISIBILITY_DEBOUNCE_MS + 120));
const grewDuringDrag = n10.inputs.length;
linkConnector.renderLinks = [];
n10.onConnectionsChange("INPUT", 0, true);
await new Promise((r) => setTimeout(r, mod.VISIBILITY_DEBOUNCE_MS + 120));
check("F10: 드래그 중에는 늘리기만 (제거 보류)",
      grewDuringDrag >= 1, "inputs=" + grewDuringDrag);
check("F10: 드래그 종료 후 정상 반영", n10.inputs.length === 1,
      JSON.stringify(n10.inputs.map((x) => x.name)));

console.log("-- F11: 프로토타입 후킹은 한 번만 (2026-10-02) --");
// 왜(Why): 프론트엔드가 노드 정의를 재등록할 수 있다. 방치하면 후킹이
// 층층이 쌓여 setTimeout 이 N개 예약된다.
const patchedBefore = ensurePatched().onConnectionsChange;
reexecRegisterExtension();
const patchedAfter = ensurePatched().onConnectionsChange;
check("F11: 재등록해도 onConnectionsChange 후킹이 누적되지 않음",
      patchedBefore === patchedAfter,
      "before!==after = 두 번째 래퍼가 생김");
const nodeBefore = ensurePatched().onNodeCreated;
reexecRegisterExtension();
check("F11: onNodeCreated 도 1회만 후킹",
      nodeBefore === ensurePatched().onNodeCreated, "누적됨");
const confBefore = ensurePatched().onConfigure;
reexecRegisterExtension();
check("F11: onConfigure 도 1회만 후킹",
      confBefore === ensurePatched().onConfigure, "누적됨");

console.log("-- F12: 후킹은 원본을 그대로 호출한다 (2026-10-02) --");
// 왜(Why): 원본을 부르지 않는 후킹은 "확장끼리 공존"이 아니라 "확장이 원본을
// 대체"다. 다른 확장이 먼저 깔렸어도 그 호출이 빠지지 않아야 한다.
// ensurePatched() 가 후킹 전 베이스를 baseCalls 로 세도록 해뒀다.
ensurePatched();
const before12 = baseCalls;
const n12 = makeLifecycleNode();
n12.inputs = [];
n12.addInput = function (nm) { this.inputs.push({ name: nm }); };
graphNodes.push(n12);
const ret12 = n12.onConnectionsChange("INPUT", 0, true);
check("F12: 베이스 onConnectionsChange 가 실제로 불림",
      baseCalls === before12 + 1, "baseCalls=" + baseCalls);
check("F12: 원본 반환값을 그대로 통과시킴", ret12 === undefined,
      String(ret12));
await new Promise((r) => setTimeout(r, mod.VISIBILITY_DEBOUNCE_MS + 120));
check("F12: 후킹이 끝까지 동작 (소켓 반영)", n12.inputs.length === 1,
      JSON.stringify(n12.inputs.map((x) => x.name)));

try {
  fs.unlinkSync(path.join(HERE, ".gori_frontend_under_test.mjs"));
} catch (_) { /* 임시파일 정리는 무시 */ }

console.log("");
console.log("  합계: PASS=" + PASS + "  FAIL=" + FAIL);
process.exit(FAIL ? 1 : 0);
