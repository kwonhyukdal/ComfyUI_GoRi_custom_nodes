/**
 * (GoRi) Consistency Keeper — progressive image input reveal.
 *
 * The keeper has one fixed image socket (`image_1` = slot 1, the main
 * subject) plus progressive sockets `image_2` .. `image_10` that mirror the
 * camera node's slot order (2-8 helpers, 9-10 appearance refs).
 *
 * Only image_2..image_10 are managed here. `image_1` is never added
 * or removed by this extension, but its **link state gates the rest**.
 * Rule (2026-10-12 사용자 지시): a brand-new node shows **image_1 alone**;
 * `image_2` appears once image_1 is linked; from there the camera node's
 * "last linked socket + one empty lookahead" rule takes over. Example:
 * image_1 unlinked -> no managed sockets; image_1 linked -> image_2 exists;
 * image_2 linked -> image_3 appears; image_2..image_9 linked -> up to
 * image_10 exists.
 *
 * Why removeInput/addInput (same reason as camera): the current ComfyUI
 * frontend canvas renderer does not read a socket `hidden` flag (hidden is
 * widgets-only). The dynamically supported API is used instead.
 *
 * Safety design (same as camera): image_N sockets sit at the tail of
 * node.inputs, so (1) removal always targets the last image socket in the
 * array, which by the rule is always unlinked, and (2) re-adding appends
 * with the original name/order at the tail. Relative socket order never
 * changes, so stored workflow links (target_slot) stay valid. Even if a
 * non-image socket appears behind the image sockets, removeInput lets the
 * core fix up remaining links' target_slot.
 *
 * Fail-safe: on any error, all sockets (2..10) are rebuilt. A node that
 * cannot be wired is worse than extra empty sockets.
 *
 * Keeper-only scope: this extension ignores every node type except
 * `GoRi_ConsistencyKeeper` (early return in beforeRegisterNodeDef), so the
 * camera node and unrelated nodes are never touched.
 */
import { app } from "../../scripts/app.js";

const EXT_ID = "GoRi.Keeper.ProgressiveImageInputs";
const KEEPER_NODE_TYPE = "GoRi_ConsistencyKeeper";
const IMAGE_INPUT_RE = /^image_\d+$/;
const FIRST_IMAGE = 2; // slot 1 is `image_1` (fixed, never managed)
const LAST_IMAGE = 10;
const LOOKAHEAD = 1; // empty slots shown past the last linked socket
const SLOT_HEIGHT = 20; // one input socket's height (frontend 1.52.x measured)

/** Debounce (ms) for socket cleanup. Same reason as camera (frontend calls
 * onConnectionsChange once per link while applying multi-connects in a
 * loop, so without coalescing one update runs N times). Human click gaps
 * are hundreds of ms, so 50ms reads as instant. */
const VISIBILITY_DEBOUNCE_MS = 50;

/** Coalesce rapid calls into a single execution after `wait` ms.
 * Used for lifecycle hooks that may fire in quick succession. */
function debounce(func, wait) {
    let timeout;
    return function(...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), wait);
    };
}

function imageNumber(name) {
  const m = /^image_(\d+)$/.exec(String(name ?? ""));
  return m ? Number(m[1]) : 0;
}

/** Managed socket: image_2..image_10 only. image_1 must never be created
 * here (slot 1 is `image_1`), and `image_1` itself never
 * matches IMAGE_INPUT_RE so scans already skip it. */
function isManagedImage(name) {
  const n = imageNumber(name);
  return n >= FIRST_IMAGE && n <= LAST_IMAGE;
}

/** The fixed main-subject socket name (slot 1, never managed). */
const MAIN_IMAGE = "image_1";

/** True when the fixed `image_1` socket has a link.
 * 왜(Why) 이걸 보나 (2026-10-12 사용자 지시): 새 노드를 꺼내면 예전에는
 * image_1·image_2 가 함께 보였는데, 슬롯 1(주 피사체)이 꽂혀야 2번이 의미를
 * 갖는다. 그래서 2번 이후의 등장을 image_1 의 **연결 여부**로 게이트한다.
 * 이 확장은 image_1 을 만들거나 지우지 않는다 — 읽기만 한다. */
function isMainLinked(node) {
  for (const inp of node?.inputs ?? []) {
    if (inp && inp.name === MAIN_IMAGE) return inp.link != null;
  }
  return false;
}

/** Count of existing managed image sockets */
function countImageSockets(node) {
  let count = 0;
  for (const inp of node?.inputs ?? []) {
    if (inp && isManagedImage(inp.name)) count++;
  }
  return count;
}

/** Highest linked image number (2-based), 0 when none linked */
function lastLinkedImageNumber(node) {
  let last = 0;
  for (const inp of node?.inputs ?? []) {
    if (inp && isManagedImage(inp.name) && inp.link != null) {
      const n = imageNumber(inp.name);
      if (n > last) last = n;
    }
  }
  return last;
}

/** Count and last-linked in a single pass (same reason as camera: one scan
 * instead of two over the same array). */
function scanImageSockets(node) {
  let count = 0;
  let last = 0;
  for (const inp of node?.inputs ?? []) {
    if (!inp || !isManagedImage(inp.name)) continue;
    count++;
    if (inp.link != null) {
      const n = imageNumber(inp.name);
      if (n > last) last = n;
    }
  }
  return { count, last };
}

/** Index of the last managed image socket in node.inputs */
function lastImageSocketIndex(node) {
  const inputs = node?.inputs ?? [];
  for (let i = inputs.length - 1; i >= 0; i--) {
    if (inputs[i] && isManagedImage(inputs[i].name)) return i;
  }
  return -1;
}

/** True while a link is being dragged (removing sockets mid-drag orphans it) */
function isDraggingLink() {
    const renderLinks = app?.canvas?.linkConnector?.renderLinks;
    return Array.isArray(renderLinks) && renderLinks.length > 0;
}

function updateVisibility(node) {
  try {
    const template = node._goriKeeperImageTemplate;
    if (!Array.isArray(template) || !template.length) return;

    const scan = scanImageSockets(node);
    const lastLinked = scan.last;
    const mainLinked = isMainLinked(node);
    // Early return when nothing changed (scan key covers count + links).
    // Same reason as camera: this runs debounced, but each run still scans
    // the inputs array, so a no-op must stay cheap. restoreAll can grow
    // sockets without links, hence count is part of the key.
    // 왜(Why) image_1 연결 여부도 키에 넣나 (2026-10-12): 1번만 꽂거나 빼는
    // 변화는 count/last 로는 보이지 않는다. 키에 없으면 조기 반환이 그 갱신을
    // 삼켜 2번이 영영 안 나타나거나 안 사라진다.
    const key = scan.count + ":" + lastLinked + ":" + (mainLinked ? 1 : 0);
    if (node._goriKeeperScanKey === key && !isDraggingLink()) {
      return;
    }

    // Template[0] is image_2, so offset by FIRST_IMAGE - 1 from the number.
    // 왜(Why) image_1 이 게이트인가 (2026-10-12 사용자 지시): 슬롯 1(주 피사체)이
    // 꽂혀야 2번이 의미를 갖는다. 그래서 1번이 비어 있으면 관리 소켓을 **0개**로
    // 두고(새 노드는 image_1 하나만 보인다), 1번이 꽂히면 2번부터 예고한다.
    const desired = mainLinked
      ? Math.min(template.length,
                 Math.max(1, lastLinked - FIRST_IMAGE + 1 + LOOKAHEAD))
      : 0;

    let count = scan.count;
    if (count === desired) {
      // Settled: record the key so repeat triggers stay cheap.
      node._goriKeeperScanKey = key;
      return;
    }

    // Keep node height in step with socket changes (same reason as camera:
    // freed space would otherwise stretch remaining full-height widgets).
    // Grow side is handled by the core's addInput; shrink side subtracts
    // exactly removed-count * SLOT_HEIGHT instead of computeSize(), which
    // wobbles with widget content.
    const countBefore = count;

    while (count < desired) {
      const spec = template[count];
      node.addInput(spec.name, spec.type, spec);
      count++;
    }

    if (count > desired && !isDraggingLink()) {
      while (count > desired) {
        const idx = lastImageSocketIndex(node);
        if (idx < 0) break;
        node.removeInput(idx);
        count--;
      }
    }

    // 소켓 감산은 **새 노드에만** 한다 (2026-10-18 라이브 실측).
    // 왜(Why) 로드된 노드를 빼는가: 노드 정의에는 image_2~10 이 항상 있으므로
    // 워크플로를 열 때도 그 9개가 먼저 만들어졌다가 여기서 빠진다. 그 감산을
    // 로드에도 적용하면 저장해 둔 사용자 크기가 매번 (빠진 수 × 20px) 만큼
    // 줄어든다 — 실측: 저장 500 -> 로드 후 320(9×20=180 감산). 저장된 크기는
    // 이미 소켓이 정리된 상태를 반영하므로 감산할 대상이 없다. 새 노드는 정의상
    // 부풀려진 크기를 되돌려야 하므로 그대로 감산한다(뒤이어 shrinkNewNode 가
    // 내용 높이로 확정한다).
    const removed = countBefore - count;
    if (removed > 0 && !node._goriKeeperLoaded && isSizeLike(node.size)) {
      node.setSize([node.size[0], node.size[1] - removed * SLOT_HEIGHT]);
    }
    // 새 노드면 소켓이 바뀐 만큼 높이를 **최소치까지** 다시 조인다.
    // 왜(Why) 여기서도 부르나 (2026-10-12 사용자 지시): 위 감산은 소켓 수만
    // 반영한다. DOM 위젯이 아직 안 붙었을 때 computeSize 가 과대하면 아래쪽에
    // 빈 여백이 남는다 — 생성 직후 한 번 더 재계산해 그 여백을 없앤다.
    // 로드된 노드(_goriKeeperLoaded)는 사용자가 저장한 배치를 존중해 건드리지 않는다.
      if (!node._goriKeeperLoaded) {
        shrinkNewNode(node);
      } else if (!node._goriKeeperLoadRepaired) {
        // 로드된 노드는 사용자가 저장한 배치를 기본으로 존중하지만,
        // 과거 버전/타이밍 때문에 저장된 크기가 내용 하단보다 크게 남은 경우
        // (예: 예산 꼬리 8px, 소켓 감산 전 크기) 한 번만 정리한다.
        // 왜(Why) 한 번만: 사용자가 의도적으로 키운 크기는 이후 건드리지 않는다.
        node._goriKeeperLoadRepaired = true;
        const repair = () => {
          try {
            if (!isSizeLike(node.size)) return;
            const fit = Math.round(widgetContentBottom(node));
            if (fit <= 0) {
              // 위젯이 아직 안 붙었으면 재시도
              if (typeof requestAnimationFrame === "function") requestAnimationFrame(repair);
              else setTimeout(repair, 100);
              return;
            }
            const min = (typeof node.computeSize === "function") ? node.computeSize() : null;
            const minH = isSizeLike(min) ? Math.round(min[1]) : fit;
            const h = fit > 0 ? fit : Math.max(1, minH);
            if (node.size[1] > h + 7) {
              node.setSize([node.size[0], h]);
            }
          } catch (_) { /* 조용히 무시 */ }
        };
        repair();
        if (typeof requestAnimationFrame === "function") requestAnimationFrame(repair);
        setTimeout(repair, 300);
      }
    // Record the key only when settled. When removal is deferred mid-drag
    // (or the tail lookup fails), the key stays stale so the next trigger
    // re-runs instead of early-returning on "nothing changed" and leaving
    // the deferred shrink undone forever.
    if (count === desired) {
      node._goriKeeperScanKey = key;
    }
  } catch (err) {
    restoreAll(node);
  }
}

/** Fail-safe: rebuild every managed socket (2..10) */
function restoreAll(node) {
  try {
    const template = node._goriKeeperImageTemplate;
    if (!Array.isArray(template) || !template.length) return;
    if (isDraggingLink()) return;
    let count = countImageSockets(node);
    while (count < template.length) {
      node.addInput(template[count].name, template[count].type, template[count]);
      count++;
    }
  } catch (_) {
    /* give up quietly — the node definition itself is fine */
  }
}

/* --- debounced visibility scheduler (same design as camera) ---
 *
 * WeakMap of per-node timers so a removed node drops its entry; the fired
 * callback re-checks graph membership before touching sockets. The template
 * is module-global because exactly one node type is targeted. */
const visibilityTimers = new WeakMap();
let IMAGE_TEMPLATE = [];

function scheduleVisibilityUpdate(node) {
  if (!node) return;
  const prev = visibilityTimers.get(node);
  if (prev !== undefined) clearTimeout(prev);
  visibilityTimers.set(node, setTimeout(() => {
    visibilityTimers.delete(node);
    const nodes = app.graph?._nodes;
    if (Array.isArray(nodes) && !nodes.includes(node)) return;
    try {
      if (!node._goriKeeperImageTemplate?.length) node._goriKeeperImageTemplate = IMAGE_TEMPLATE;
      updateVisibility(node);
    } catch (_) {
      restoreAll(node);
    }
  }, VISIBILITY_DEBOUNCE_MS));
}

function setCanvasDirty() {
  try {
    app.canvas?.setDirty?.(true, true);
  } catch (_) {
    /* ignore */
  }
}

/** 사이즈처럼 생긴 값인가 — plain array 와 typed array 흉내 객체를 모두 받는다.
 * 왜(Why) Array.isArray 로는 안 되나 (2026-10-18 라이브 실측): 프런트엔드
 * 1.53.10 의 node.size 게터는 **Float64Array 흉내 객체**를 돌려준다.
 * Array.isArray 는 false 이고 ArrayBuffer.isView 까지 false 다(진짜 뷰가 아니라
 * 프로토타입만 흉내낸다). 그래서 길이와 두 숫자만 보고 판단한다. 이 검사가
 * 없던 동안에는 새 노드의 높이 보정 두 곳(updateVisibility 감산·shrinkNewNode)
 * 이 통째로 반환돼 아래 188px 가 빈 여백으로 남았다(실측 free=188, gap=188).
 * 카메라 모듈도 같은 이유로 같은 함수를 쓴다. */
function isSizeLike(v) {
  return !!v && typeof v.length === "number" && v.length >= 2
    && typeof v[0] === "number" && typeof v[1] === "number";
}

/** 마지막으로 **보이는** 위젯의 하단(y + 높이). 배치 전이면 0.
 * 프런트엔드는 매 draw 마다 위젯 y 와 computedHeight 를 다시 심는다
 * (_arrangeWidgets: computedHeight = computeSize + 4). 그래서 이 값이 곧
 * "내용이 실제로 차지하는 높이"이고, 노드 높이와 무관하게 안정적이다 —
 * 크기를 줄인 뒤 다시 재도 같은 값이 나온다(멱등의 근거). */
function widgetContentBottom(node) {
  let bottom = 0;
  for (const w of node?.widgets ?? []) {
    if (!w || w.hidden) continue;
    if (typeof w.y !== "number") continue;
    let h = 0;
    if (typeof w.computedHeight === "number" && w.computedHeight > 0) {
      h = w.computedHeight; // _arrangeWidgets 가 심은 배치 높이
    } else if (typeof w.computeSize === "function") {
      // 아직 배치 전: 캔버스 위젯 규약(computeSize + 위아래 4)으로 근사한다
      const c = w.computeSize(isSizeLike(node.size) ? node.size[0] : 0);
      if (isSizeLike(c)) h = c[1] + 4;
    }
    if (h <= 0) continue;
    const b = w.y + h;
    if (b > bottom) bottom = b;
  }
  return bottom;
}

/** 새 노드의 높이를 **내용 높이에 정확히** 맞춘다 (폭은 유지).
 * 왜(Why) 필요한가 (2026-10-11 실측 · 2026-10-12 사용자 지시): 노드를 오자마자
 * 꺼내면 이미지 소켓 image_2~10 이 정의대로 9개나 있어서 아래가 크게 빈 여백으로
 * 보인다. 위 updateVisibility 의 감산만으로는 소켓 수만 반영돼 최소치에 못
 * 미치거나(위젯이 아직 DOM 에 안 붙었을 때) 반대로 너무 짧아진다 — 그래서
 * 두 값을 함께 본다. 로드(워크플로 열기)가 끼어들면 즉시 중단해서 저장된 배치에
 * 손대지 않는다.
 *
 * 왜(Why) computeSize() 최소치가 아니라 **내용 하단**인가 (2026-10-18 라이브 실측):
 * computeSize() 는 프런트엔드의 예산이라 실제 배치보다 꼬리 8px 만큼 크다
 * (실측 min=234 vs 내용 하단=226). 처음에는 "남은 여백(freeWidgetSpace)을
 * 없앤다" 로 짰는데, 이미 맞춰진 뒤에는 free 가 0 이라 그 보정이 건너뛰어지고
 * 예산 234 로 **되돌아가 8px 를 다시 붙였다** (실측 타임라인: t=103ms 226 ->
 * t=413ms 234). 300ms 재시도 패스가 그 되돌림을 일으켰다. 그래서 기준을
 * "여백" 이 아니라 **보이는 위젯의 하단**으로 삼는다 — 이 값은 크기와 무관해
 * 몇 번을 다시 재도 226 이므로 되돌림이 원천적으로 없다.
 * 배치 전(위젯 y 없음)에는 잴 수 없으므로 예산(computeSize 최소치)으로만
 * 맞춘다 — 그 상태에서도 run 은 정상이다(측정은 다음 draw 뒤에 다시 온다). */
function shrinkNewNode(node) {
  if (typeof node?.computeSize !== "function") return;
  if (!isSizeLike(node.size)) return;
  const min = node.computeSize();
  if (!isSizeLike(min)) return;
  const fit = Math.round(widgetContentBottom(node));
  const h = fit > 0 ? fit : Math.max(1, Math.round(min[1]));
  if (node.size[1] !== h) {
    node.setSize([Math.max(node.size[0], min[0]), h]);
  }
}

app.registerExtension({
  name: EXT_ID,
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== KEEPER_NODE_TYPE) return;

    // Collect image_2..image_10 socket specs from the node definition
    // (name/type/tooltip preserved), sorted by slot number.
    const template = [];
    const optional = nodeData.input?.optional ?? {};
    for (const [name, spec] of Object.entries(optional)) {
      if (!isManagedImage(name)) continue;
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

    const afterLifecycle = (node) => {
      try {
        if (!node._goriKeeperImageTemplate?.length) node._goriKeeperImageTemplate = template;
        updateVisibility(node);
      } catch (_) {
        restoreAll(node);
      }
      if (!node._goriKeeperLoaded && !node._goriKeeperShrinkScheduled) {
        node._goriKeeperShrinkScheduled = true;
        const pass = () => {
          try {
            if (node._goriKeeperLoaded) return; // 로드가 끼어들면 즉시 중단
            shrinkNewNode(node);
          } catch (_) {
            /* 축소 실패는 조용히 무시 — 기본 크기로 사용 가능 */
          }
        };
        pass();
        if (typeof requestAnimationFrame === "function") requestAnimationFrame(pass);
        setTimeout(pass, 300);
      }
    };

    /* Debounce rapid lifecycle hooks (onNodeCreated + onConfigure may fire
     * back-to-back during node creation). 50ms matches the visibility debounce. */
    const lifecycleDebouncers = new WeakMap();
    function scheduleLifecycle(node) {
        let d = lifecycleDebouncers.get(node);
        if (!d) {
            d = debounce((n) => afterLifecycle(n), 50);
            lifecycleDebouncers.set(node, d);
        }
        d(node);
    }

    /* Closure-kept originals (same reason as camera): other extensions may
     * wrap the same methods, so originals live only in the closure. Works
     * regardless of load order and restores cleanly. */
    const patchLifecycle = (name) => {
      const original = nodeType.prototype[name];
      // One-time guard: the frontend can re-register node defs, which would
      // otherwise stack a wrapper per registration (N timers per update).
      if (nodeType.prototype["_goriKeeperPatched_" + name]) return;
      nodeType.prototype["_goriKeeperPatched_" + name] = true;
      nodeType.prototype[name] = function (...args) {
        const result = original?.apply(this, args);
        // Never touch sockets mid-configure: the core may add sockets after
        // us, so always defer past the configure loop.
        if (name === "onConfigure") {
          this._goriKeeperLoaded = true;
        }
        scheduleLifecycle(this);
        return result;
      };
    };

    patchLifecycle("onNodeCreated");
    patchLifecycle("onConfigure");

    IMAGE_TEMPLATE = template;

    const originalConnections = nodeType.prototype.onConnectionsChange;
    if (!nodeType.prototype._goriKeeperPatched_onConnectionsChange) {
      nodeType.prototype._goriKeeperPatched_onConnectionsChange = true;
      nodeType.prototype.onConnectionsChange = function (...args) {
        const result = originalConnections?.apply(this, args);
        scheduleVisibilityUpdate(this);
        return result;
      };
    }
    setCanvasDirty();
  },
});

/* Exported for tests (mirrors the camera module's export contract). The
 * frontend does not consume extension exports, so this is behavior-neutral
 * and exactly one function/value set. */
export {
  imageNumber, countImageSockets, lastLinkedImageNumber, lastImageSocketIndex,
  isDraggingLink, updateVisibility, restoreAll,
  scheduleVisibilityUpdate, VISIBILITY_DEBOUNCE_MS,
  shrinkNewNode, isSizeLike, widgetContentBottom, isMainLinked, MAIN_IMAGE,
};
