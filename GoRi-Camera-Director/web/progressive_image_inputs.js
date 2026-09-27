/**
 * (GoRi) Camera Director — 점진적 이미지 입력 공개
 *
 * image_2 ~ image_10 소켓은 기본으로 생성하지 않고, 연결 상황에 맞춰
 * 동적으로 추가/제거한다. 규칙: "연결된 마지막 단자 + 다음 빈칸 1개"까지만
 * 존재한다. 예: 1번 연결 → 2번 노출, 1~7번 연결 → 8번까지 노출.
 *
 * 왜 removeInput/addInput인가(Why): 현재 ComfyUI 프론트엔드(1.52.x)의
 * 캔버스 렌더러는 소켓의 `hidden` 플래그를 읽지 않는다(hidden은 위젯
 * 전용). 이 프론트엔드가 공식 지원하는 동적 소켓 API를 사용한다.
 *
 * 안전성 설계(Why): image_N 소켓은 node.inputs의 맨 뒤에 위치하므로,
 * (1) 제거는 항상 "배열에서 가장 뒤에 있는 image 소켓"만 하고, 그 대상은
 * 규칙상 항상 연결되지 않은 소켓이다. (2) 재추가는 addInput으로 맨 뒤에
 * 원래 이름·순서대로 붙인다. 즉 소켓의 상대 순서가 절대 변하지 않아 저장된
 * 워크플로의 링크(target_slot)가 어긋나지 않는다. 혹시 위젯 변환 등으로
 * image 소켓 뒤에 다른 소켓이 생겨도 removeInput이 남은 링크의
 * target_slot을 보정하므로 안전하다.
 *
 * Fail-safe: 어떤 오류가 나면 전체 소켓(1~10)을 다시 만든다. 이벤트 미지원
 * UI에서도 노드를 못 쓰게 되는 사태를 막는다.
 *
 * 추가 기능: 새 노드를 꺼내면 topic 위젯이 남는 공간을 전부 차지해 처음부터
 * 크게 나온다(h-full 구조 + 기본 높이 과다). 새 노드에 한해 노드 높이를
 * 최소치로 줄여 topic이 1줄 높이로 시작하게 한다. 이후 노드 크기는 사용자가
 * 우측 하단 코너로 직접 조절하는 유일한 수단이며, 텍스트가 넘치면 topic
 * 칸 안에서 마우스 휠로 스크롤한다(자동 확장 없음 → 여러 노드의 오자와
 * 열이 흐트러지지 않는다). 휠 이벤트는 노드 바깥(캔버스 줌)으로 새지 않게
 * 막는다. 워크플로 로드/붙여넣기 시에는 저장된 노드 크기를 존중한다.
 */
import { app } from "../../scripts/app.js";

const EXT_ID = "GoRi.CameraDirector.ProgressiveImageInputs";
const IMAGE_INPUT_RE = /^image_\d+$/;
const LOOKAHEAD = 1; // 마지막 연결 단자 다음에 미리 보여줄 빈칸 수
const SLOT_HEIGHT = 20; // 입력 소켓 1개의 세로 높이 (프론트엔드 1.52.x 실측)

function imageNumber(name) {
  const m = /^image_(\d+)$/.exec(name);
  return m ? Number(m[1]) : 0;
}

/** 현재 존재하는 image 소켓 개수 */
function countImageSockets(node) {
  let count = 0;
  for (const inp of node.inputs || []) {
    if (IMAGE_INPUT_RE.test(inp.name)) count++;
  }
  return count;
}

/** 연결된 마지막 image 소켓의 image 번호(1부터), 없으면 0 */
function lastLinkedImageNumber(node) {
  let last = 0;
  for (const inp of node.inputs || []) {
    if (IMAGE_INPUT_RE.test(inp.name) && inp.link != null) {
      const n = imageNumber(inp.name);
      if (n > last) last = n;
    }
  }
  return last;
}

/** node.inputs 배열에서 가장 뒤에 있는 image 소켓 인덱스 */
function lastImageSocketIndex(node) {
  for (let i = (node.inputs || []).length - 1; i >= 0; i--) {
    if (IMAGE_INPUT_RE.test(node.inputs[i].name)) return i;
  }
  return -1;
}

/** 링크 드래그 중인지 확인 (드래그 중 소켓이 사라지는 사고를 막는다) */
function isDraggingLink() {
  try {
    const renderLinks = app.canvas?.linkConnector?.renderLinks;
    return Array.isArray(renderLinks) && renderLinks.length > 0;
  } catch (_) {
    return false;
  }
}

function updateVisibility(node) {
  try {
    const template = node._goriImageTemplate;
    if (!Array.isArray(template) || !template.length) return;

    const lastLinked = lastLinkedImageNumber(node);
    const desired = lastLinked === 0
      ? 1
      : Math.min(template.length, lastLinked + LOOKAHEAD);

    let count = countImageSockets(node);
    if (count === desired) return;

    // 소켓 수 변화만큼 노드 높이도 같이 조정한다(연결 시 +, 해제 시 -).
    // 소켓이 사라져도 노드 높이가 그대로면 남는 공간을 topic 위젯(h-full)이
    // 다 차지해 세로로 부풀어 오른다.
    //
    // 높이 계산은 computeSize()를 쓰지 않는다(Why): topic 위젯(h-full)의
    // computedHeight가 노드 크기 변화에 따라 ±20px로 요동쳐 computeSize도
    // 함께 흔들리고, 하한 보호(max)가 축소를 무효화하는 사례가 실측됐다.
    // 대신 "제거한 소켓 개수 × 슬롯 높이(20px, 이 프론트엔드 실측)"로
    // 정확히 줄인다. 늘리는 쪽은 addInput(expandToFitContent)이 코어에서
    // 이미 처리하므로 건드리지 않는다.
    const countBefore = count;

    // 늘리기: 항상 안전(맨 뒤에 원래 이름으로 추가)
    while (count < desired) {
      const spec = template[count];
      node.addInput(spec.name, spec.type, spec);
      count++;
    }

    // 줄이기: 드래그 중에는 미루고, 대상은 항상 가장 뒤의 image 소켓(미연결)
    if (count > desired && !isDraggingLink()) {
      while (count > desired) {
        const idx = lastImageSocketIndex(node);
        if (idx < 0) break;
        node.removeInput(idx);
        count--;
      }
    }

    const removed = countBefore - count;
    if (removed > 0) {
      node.setSize([node.size[0], node.size[1] - removed * SLOT_HEIGHT]);
    }
  } catch (err) {
    restoreAll(node);
  }
}

/** Fail-safe: 전체 소켓(1~10) 복원 */
function restoreAll(node) {
  try {
    const template = node._goriImageTemplate;
    if (!Array.isArray(template) || !template.length) return;
    if (isDraggingLink()) return;
    let count = countImageSockets(node);
    while (count < template.length) {
      node.addInput(template[count].name, template[count].type, template[count]);
      count++;
    }
  } catch (_) {
    /* 이마저 실패하면 조용히 포기 — 노드 정의 자체는 정상 */
  }
}

// ----- topic 위젯 초기 축소 + 휠 스크롤 -----------------------------------
// 새 노드의 기본 높이가 필요치보다 크고, topic textarea는 h-full(남는 공간
// 전부 차지) 구조라 처음부터 수십 px 높게 나온다. 새 노드에 한해 높이를
// 최소치로 줄인다. 이후 크기 조절은 노드 코너 드래그만 가능하고(위젯 자체는
// resize:none), 텍스트가 넘치면 칸 안에서 휠 스크롤한다. 자동 확장은
// 의도적으로 하지 않는다 — 여러 노드를 오자와 열에 맞춰 정돈해 두면 자동
// 크기 변화가 배치를 흐트러뜨린다.

/** topic textarea의 DOM 요소 (없으면 null) */
function topicElement(node) {
  const w = (node.widgets || []).find((x) => x.name === "topic");
  return w?.element ?? null;
}

/** 새 노드의 높이를 최소치로 맞춘다 (폭은 유지) */
function shrinkNewNode(node) {
  if (typeof node.computeSize !== "function") return;
  const min = node.computeSize();
  if (node.size[1] > min[1]) {
    node.setSize([Math.max(node.size[0], min[0]), min[1]]);
  }
}

/** topic 위젯 휠 스크롤 지원.
 * 이 프론트엔드는 window 레벨(capture)에서 휠을 가로채 캔버스 줌으로 바꾸므로
 * 노드/위젯의 버블 리스너로는 늦고, document capture보다도 늦다(window →
 * document 순서). 그래서 모듈 로드 즉시 window capture로 1회 등록해 코어 줌
 * 핸들러보다 먼저 실행되게 한다. 확장 스크립트는 코어 캔버스 초기화보다
 * 먼저 import되므로 등록 순서상 앞선다. 넘친 topic 위에서의 휠만 가로채
 * preventDefault + stopImmediatePropagation으로 줌·버블을 모두 차단하고
 * 남는 높이만큼 직접 스크롤한다. 그 밖의 휠은 건드리지 않는다. */
const TOPIC_ELS = new Set();
window.addEventListener("wheel", (e) => {
  try {
    const t = e.target;
    if (!(t instanceof HTMLTextAreaElement) || !TOPIC_ELS.has(t)) return;
    if (t.scrollHeight <= t.clientHeight + 1) return; // 넘침 없음
    e.preventDefault();
    e.stopImmediatePropagation();
    t.scrollTop += e.deltaY;
  } catch (_) {
    /* 실패 시 기본 동작 유지 */
  }
}, { capture: true, passive: false });

/** 각 노드의 topic textarea를 전역 감시 목록에 등록 (1회) */
function attachTopicScroll(node) {
  const el = topicElement(node);
  if (!el || el._goriWheelDoc === true) return;
  el._goriWheelDoc = true;
  // 넘침 스크롤 보장 (ComfyUI 기본값이 auto라 보통 이미 설정됨)
  el.style.overflowY = "auto";
  // 가독성: 프론트엔드 기본 10px는 너무 작아 13px로 키운다.
  // 프론트엔드 CSS가 !important로 10px를 강제하므로 inline !important로 이긴다.
  el.style.setProperty("font-size", "13px", "important");
  el.style.setProperty("line-height", "1.45", "important");
  TOPIC_ELS.add(el);
  // 노드 제거 시 감시 목록에서 정리 (메모리 누수 방지)
  const prevRemoved = node.onRemoved;
  node.onRemoved = function (...args) {
    try {
      TOPIC_ELS.delete(el);
    } catch (_) {
      /* 정리 실패는 무시 */
    }
    return prevRemoved?.apply(this, args);
  };
}

/* ---------------------------------------------------------------------------
 * LLM 상태 표시등
 *
 * Python 노드가 LLM 판정을 시작/완료하면 웹소켓 이벤트(gori_llm_status)를
 * 보내고, 이 확장이 받아 model 위젯에 표시등을 켠다.
 *
 *   busy → 초록 점멸 (LLM이 지금 구동 중 — 로컬/Ollama는 수십 초 걸릴 수 있어
 *          "멈춘 건지, 계산 중인지"를 구분할 수 있게 해주는 게 핵심 목적)
 *   on   → 초록 켜짐 (판정 성공, 몇 초 뒤 자동 소등)
 *   fail → 빨강 켜짐 (규칙 폴백 — 겉보기엔 성공과 같아서 사용자가 모른다)
 *   off  → 즉시 소등 (규칙/수동 티어, 새 실행 시작)
 *
 * 구현 방식(중요): 한 줄 STRING 위젯(model)은 이 프론트엔드에서 DOM 위젯이
 * 아니라 **캔버스에 그려지는 위젯**이라 element/inputEl이 없다(실측 확인).
 * 따라서 CSS 테두리가 아니라 onDrawForeground 오버레이로 위젯 줄에
 * 직접 그린다. topic처럼 여러 줄 텍스트박스 위젯만 DOM 방식이 가능하다.
 * ------------------------------------------------------------------------- */
const LLM_LIGHT_STYLE = {
  busy: { color: "#35d07f", blink: true, fadeMs: 0 },
  on: { color: "#35d07f", blink: false, fadeMs: 6000 },
  fail: { color: "#e05555", blink: false, fadeMs: 9000 },
};

// 점멸/소등 시점에 캔버스를 다시 그리게 하는 타이머 (전역 1개)
let llmBlinkTimer = null;
let llmFadeTimer = null;

function setCanvasDirty() {
  try {
    app.canvas?.setDirty?.(true, true);
  } catch (_) {
    /* 무시 */
  }
}

function anyNodeBlinking() {
  try {
    const nodes = app.graph?._nodes || [];
    return nodes.some((n) => n._goriLlmState === "busy");
  } catch (_) {
    return false;
  }
}

function updateBlinkTimer() {
  if (anyNodeBlinking() && !llmBlinkTimer) {
    llmBlinkTimer = setInterval(setCanvasDirty, 60);
  } else if (!anyNodeBlinking() && llmBlinkTimer) {
    clearInterval(llmBlinkTimer);
    llmBlinkTimer = null;
  }
}

function ensureLlmDrawHook(node) {
  if (node._goriLlmHooked) return;
  node._goriLlmHooked = true;
  const prev = node.onDrawForeground;
  node.onDrawForeground = function (ctx) {
    prev?.apply(this, arguments);
    drawLlmLight(this, ctx);
  };
}

/** model 위젯 줄에 표시등을 캔버스로 그린다 (node 로컬 좌표) */
function drawLlmLight(node, ctx) {
  const state = node._goriLlmState;
  if (!state) return;
  const spec = LLM_LIGHT_STYLE[state];
  if (!spec) return;
  if (spec.fadeMs && Date.now() > (node._goriLlmUntil || 0)) {
    node._goriLlmState = null;
    return;
  }
  const w = (node.widgets || []).find((x) => x.name === "model");
  if (!w || typeof w.y !== "number") return;
  let alpha = 1;
  if (spec.blink) {
    alpha = 0.35 + 0.65 * Math.abs(Math.sin(Date.now() / 180));
  }
  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.strokeStyle = spec.color;
  ctx.lineWidth = 2;
  ctx.shadowColor = spec.color;
  ctx.shadowBlur = 9;
  ctx.beginPath();
  const bx = 4;
  const bw = Math.max(20, node.size[0] - 8);
  const bh = 24;
  if (typeof ctx.roundRect === "function") {
    ctx.roundRect(bx, w.y, bw, bh, 6);
  } else {
    ctx.rect(bx, w.y, bw, bh);
  }
  ctx.stroke();
  ctx.restore();
}

function applyLlmLight(node, state) {
  try {
    if (!node) return;
    const spec = LLM_LIGHT_STYLE[state];
    node._goriLlmState = spec ? state : null;
    node._goriLlmUntil = spec?.fadeMs ? Date.now() + spec.fadeMs : 0;
    ensureLlmDrawHook(node);
    if (spec?.fadeMs) {
      // 소등 시점에 캔버스가 멈춰 있으면 잔광이 남으므로 강제로 다시 그린다
      if (llmFadeTimer) clearTimeout(llmFadeTimer);
      llmFadeTimer = setTimeout(setCanvasDirty, spec.fadeMs + 60);
    }
    updateBlinkTimer();
    setCanvasDirty();
  } catch (_) {
    /* 표시등 실패는 노드 동작에 영향을 주지 않는다 */
  }
}

function clearAllLlmLights() {
  try {
    const graph = app.graph;
    if (!graph?._nodes) return;
    for (const node of graph._nodes) {
      if (node.type === "GoRi_CameraDirectorEncodeSkills") applyLlmLight(node, "off");
    }
  } catch (_) {
    /* 무시 */
  }
}

app.api?.addEventListener?.("gori_llm_status", (event) => {
  try {
    const detail = event.detail || {};
    const state = String(detail.state || "off");
    const id = Number(detail.node);
    const node = Number.isFinite(id) ? app.graph?.getNodeById?.(id) : null;
    if (!node) return;
    applyLlmLight(node, state);
  } catch (_) {
    /* 무시 */
  }
});

// 새 실행이 시작되면 모든 표시등을 초기화 (직전 실행의 잔광 제거)
app.api?.addEventListener?.("execution_start", clearAllLlmLights);

app.registerExtension({
  name: EXT_ID,
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== "GoRi_CameraDirectorEncodeSkills") return;

    // 노드 정의에서 image_1~10 소켓 템플릿 확보 (이름·타입·툴팁 보존)
    const template = [];
    const optional = nodeData.input?.optional ?? {};
    for (const [name, spec] of Object.entries(optional)) {
      if (!IMAGE_INPUT_RE.test(name)) continue;
      const info = spec?.[1] ?? {};
      template.push({
        name,
        type: spec?.[0] ?? "IMAGE",
        localized_name: info.label,
        label: info.label,
        tooltip: info.tooltip,
      });
    }
    template.sort((a, b) => imageNumber(a.name) - imageNumber(b.name));

    /** 공통 지연 처리: 소켓 정리 + (새 노드면) 높이 축소 + 휠 스크롤 훅.
     * 소켓 오류와 topic 오류는 서로에게 영향을 주지 않게 분리한다.
     * DOM 위젯은 첫 드로잉 때 마운트되므로 여러 시점에 재시도한다. */
    const afterLifecycle = (node) => {
      try {
        if (!node._goriImageTemplate?.length) node._goriImageTemplate = template;
        updateVisibility(node);
      } catch (_) {
        restoreAll(node);
      }
      try {
        attachTopicScroll(node);
      } catch (_) {
        /* 휠 스크롤 훅 실패는 조용히 무시 */
      }
      if (!node._goriLoaded && !node._goriShrinkScheduled) {
        node._goriShrinkScheduled = true;
        const pass = () => {
          try {
            if (node._goriLoaded) return; // 로드가 끼어들면 즉시 중단
            shrinkNewNode(node);
            attachTopicScroll(node);
          } catch (_) {
            /* 축소 실패는 조용히 무시 — 기본 크기로 사용 가능 */
          }
        };
        pass();
        if (typeof requestAnimationFrame === "function") requestAnimationFrame(pass);
        setTimeout(pass, 300);
      }
    };

    const patchLifecycle = (name) => {
      const original = nodeType.prototype[name];
      nodeType.prototype[name] = function (...args) {
        const result = original?.apply(this, args);
        // 소켓 구성이 마무리된 뒤 한 번 더 실행 (코어가 뒤에 소켓을
        // 추가하는 경우 대비). configure 루프 도중 소켓을 건드리지 않도록
        // 반드시 setTimeout으로 미룬다.
        if (name === "onConfigure") {
          // 워크플로 로드/붙여넣기: 사용자가 저장한 크기를 존중한다.
          // configure는 createNode 직후 동기 호출되므로, 아래 setTimeout
          // 시점엔 이 플래그가 이미 설정되어 있다.
          this._goriLoaded = true;
        }
        setTimeout(() => afterLifecycle(this), 0);
        return result;
      };
    };

    patchLifecycle("onNodeCreated");
    patchLifecycle("onConfigure");

    const originalConnections = nodeType.prototype.onConnectionsChange;
    nodeType.prototype.onConnectionsChange = function (...args) {
      const result = originalConnections?.apply(this, args);
      setTimeout(() => {
        try {
          if (!this._goriImageTemplate?.length) this._goriImageTemplate = template;
          updateVisibility(this);
        } catch (_) {
          restoreAll(this);
        }
      }, 0);
      return result;
    };
  },
});
