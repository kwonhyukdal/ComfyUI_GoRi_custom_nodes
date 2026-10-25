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
const CAMERA_NODE_TYPE = "GoRi_CameraDirectorEncodeSkills";
const IMAGE_INPUT_RE = /^image_\d+$/;
const LOOKAHEAD = 1; // 마지막 연결 단자 다음에 미리 보여줄 빈칸 수
const SLOT_HEIGHT = 20; // 입력 소켓 1개의 세로 높이 (프론트엔드 1.52.x 실측)

/** 소켓 정리 지연(ms). 연결 일괄 반영 때 setTimeout 을 중복 발사하지 않게 한다.
 *
 * 왜(Why) 50 인가: 코어는 다중 연결을 한 번에 반영할 때 입력 슬롯을 **루프로
 * 돌며** onConnectionsChange 를 부른다(프론트엔드 1.53.6 번들 실측). 그때마다
 * setTimeout 을 하나씩 예약하면 갱신이 N회 반복된다. 입력을 놓는 데는
 * 사람의 클릭 간격(수백 ms)이 걸리므로 50ms 로 묶여도 체감상 즉시다.
 * 0 으로 두면 방금 한 호출과 합쳐지지 않으므로 의미가 없다. */
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

/** 현재 존재하는 image 소켓 개수 */
function countImageSockets(node) {
  let count = 0;
  for (const inp of node?.inputs ?? []) {
    if (inp && IMAGE_INPUT_RE.test(inp.name)) count++;
  }
  return count;
}

/** 연결된 마지막 image 소켓의 image 번호(1부터), 없으면 0 */
function lastLinkedImageNumber(node) {
  let last = 0;
  for (const inp of node?.inputs ?? []) {
    if (inp && IMAGE_INPUT_RE.test(inp.name) && inp.link != null) {
      const n = imageNumber(inp.name);
      if (n > last) last = n;
    }
  }
  return last;
}

/** image 소켓 개수와 연결된 마지막 번호를 한 번의 순회로 함께 낸다.
 *
 * 왜(Why) 둘을 합쳤나 (2026-10-03 실측): updateVisibility 가 이 둘을 따로
 * 불러 inputs 배열을 두 번 훑었다. 순회당 읽기가 두 배였고, 그 수는
 * probe_visibility_scans.mjs 로 실제로 셌다. 값이 둘 다 같은 배열에서 나오므로
 * 합칠 수 있다.
 *
 * 왜(Why) 기존 둘을 안 지웠나: `countImageSockets` 는 restoreAll 이 쓰고,
 * `lastLinkedImageNumber` 는 테스트가 검증한다(R68). **export 계약이므로
 * 지우면 테스트가 깨진다.** 중복처럼 보여도 한쪽은 남기는 이유가 이것이다. */
function scanImageSockets(node) {
  let count = 0;
  let last = 0;
  for (const inp of node?.inputs ?? []) {
    if (!inp || !IMAGE_INPUT_RE.test(inp.name)) continue;
    count++;
    if (inp.link != null) {
      const n = imageNumber(inp.name);
      if (n > last) last = n;
    }
  }
  return { count, last };
}

/** node.inputs 배열에서 가장 뒤에 있는 image 소켓 인덱스 */
function lastImageSocketIndex(node) {
  const inputs = node?.inputs ?? [];
  for (let i = inputs.length - 1; i >= 0; i--) {
    if (inputs[i] && IMAGE_INPUT_RE.test(inputs[i].name)) return i;
  }
  return -1;
}

/** 링크 드래그 중인지 확인 (드래그 중 소켓이 사라지는 사고를 막는다) */
function isDraggingLink() {
    const renderLinks = app?.canvas?.linkConnector?.renderLinks;
    return Array.isArray(renderLinks) && renderLinks.length > 0;
}

function updateVisibility(node) {
  try {
    const template = node._goriImageTemplate;
    if (!Array.isArray(template) || !template.length) return;

    const scan = scanImageSockets(node);
    const lastLinked = scan.last;
    // 왜(Why) 조기 반환인가 (2026-10-03 실측): 이 함수는 debounce 로 묶여 있어
    // 호출 횟수는 줄었지만, **호출될 때마다 inputs 배열을 훑는다.**
    // 실측(probe_visibility_scans.mjs, 연결 5장 · 반복 20회):
    //   수정 전  호출당 54회 읽기, 20회 반복 = 1080회
    //   수정 후  호출당 21회 읽기, 20회 반복 =  420회
    // scan 은 위에서 한 번 훑은 결과다 — 판정을 위해 추가로 훑지 않는다.
    //
    // 판정 조건이 "scan 전체" 인 이유: desired 는 lastLinked 로만 정해지지만,
    // restoreAll 이 실패 경로에서 lastLinked 와 무관하게 소켓을 늘릴 수 있어서
    // count 도 함께 봐야 한다. 둘 다 같으면 정말로 할 일이 없다.
    // 드래그 중에는 isDraggingLink() 가 true 여서 판정을 아예 하지 않는다.
    if (node._goriScanKey === scan.count + ":" + lastLinked && !isDraggingLink()) {
      return;
    }
    // 왜(Why) 여기서 키를 먼저 기록하지 않나 (2026-10-11 실측): 드래그 중에는
    // 축소를 보류한다(아래 줄이기 블록). 그 순간 키를 미리 기록하면 드래그가
    // 끝난 뒤의 갱신이 "변경 없음"으로 조기 반환해 **보류된 축소가 영영
    // 수행되지 않는다.** 실측 프로브로 카메라 JS 에서 재현했다(드래그 종료
    // 후에도 소켓 5개가 그대로, 기대 4개). 키는 정착(count === desired)했을
    // 때만 기록한다 — 키퍼 JS 와 같은 규칙.

    const desired = lastLinked === 0
      ? 1
      : Math.min(template.length, lastLinked + LOOKAHEAD);

    let count = scan.count;
    if (count === desired) {
      node._goriScanKey = scan.count + ":" + lastLinked;
      return;
    }

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
    // 소켓 변경 전의 여유 공간 (2026-10-19 사용자 보고 수정). 왜(Why) 재나:
    // addInput 이 프런트엔드 expandToFitContent 를 태워 노드를 **콘텐츠보다
    // 크게** 키운다(실측: 소켓 1칸 추가 시 20px 가 아니라 32px 증가, 남은
    // 12px 이 여유로 생긴다). 그 여유를 상한 없는 topic 이 흡수해 2줄이
    // 3줄로 부푼다 — "이미지1 에 선을 꼽으면 topic 이 늘어난다" 의 원인.
    const freeBefore = Number(node.freeWidgetSpace);

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

    // 소켓 감산은 **새 노드에만** 한다 (2026-10-19 라이브 실측, 키퍼 JS 와 동일).
    // 왜(Why) 로드된 노드를 빼는가: 노드 정의에는 image_1~image_10 이 항상
    // 있으므로 워크플로를 열 때도 그 9개가 먼저 만들어졌다가 여기서 빠진다.
    // 그 감산을 로드에도 적용하면 저장해 둔 사용자 크기가 매 열기마다
    // (빠진 수 × 20px) 만큼 줄어든다 — 실측: 저장 500 -> 로드 후 320(9×20=180).
    // 저장된 크기는 이미 소켓이 정리된 상태를 반영하므로 감산할 대상이 없다.
    // _goriLoaded 는 onConfigure(로드)에서 동기로 서고, 이 함수는 50ms
    // 디바운스로 그 뒤에 도므로 로드 경로에서 확실히 true 다.
    const removed = countBefore - count;
    if (removed > 0 && !node._goriLoaded && isSizeLike(node.size)) {
      node.setSize([node.size[0], node.size[1] - removed * SLOT_HEIGHT]);
    }
    // 소켓 추가로 **늘어난 여유**를 되돌린다 (2026-10-19 사용자 보고 수정).
    // 왜(Why) 다음 프레임으로 미루나: addInput 안에서는 freeWidgetSpace 가
    // 아직 갱신되지 않는다(실측 로그: addInput("image_2") 시 "free 74->74").
    // 실제 노드 성장과 여유 산정은 프런트엔드 arrange 가 다음 프레임에 한다.
    // 그래서 지금 재면 옛값을 읽어 보정이 헛돈다 — 한 프레임 뒤에 잰다.
    //
    // 왜(Why) 필요한가: addInput 이 expandToFitContent 로 노드를 콘텐츠보다
    // 크게 키운다(실측: 소켓 1칸 추가 시 20px 아니라 32px 증가). 그 12px 이
    // 여유로 남고, 상한 없는 topic 이 흡수해 2줄 -> 3줄 로 부푼다. 여유가
    // **늘었을 때만** 증가분을 높이에서 빼면 free 가 원래값으로 돌아와 topic
    // 이 제 줄 수로 복귀한다(실측: 664 -> 652, free 62, topic 38px).
    //
    // 왜(Why) cap 으로 자르지 않고 "증가분"만 빼나: 사용자가 코너를 끌어 키운
    // 노드는 free 가 cap 보다 크다(실측: 900px 노드 free=330). cap 으로 자르면
    // 그 리사이즈를 되돌린다. 증가분만 빼면 사용자 여유는 그대로 남는다.
    // 소켓이 여유를 **소비**한 경우(리사이즈된 노드에 소켓 추가, free 감소)는
    // 음수라 손대지 않는다 — 그건 정상 동작이다.
    const _beforeH = isSizeLike(node.size) ? node.size[1] : null;
    const _correctFreeGrowth = () => {
      try {
        if (_beforeH === null || !isSizeLike(node.size)) return;
        const freeAfter = Number(node.freeWidgetSpace);
        if (isFinite(freeBefore) && isFinite(freeAfter)
            && freeAfter > freeBefore) {
          node.setSize([node.size[0], node.size[1] - (freeAfter - freeBefore)]);
        }
      } catch (_) {
        /* 보정 실패는 조용히 무시 — 토픽 줄 수가 원복되지 않을 뿐이다 */
      }
    };
    if (typeof requestAnimationFrame === "function") {
      requestAnimationFrame(() => requestAnimationFrame(_correctFreeGrowth));
    }
    // 왜(Why) 지연도 함께 두나: requestAnimationFrame 이 없는/백그라운드 탭에서
    // 프레임이 안 돌 수 있다. 디바운스(50ms) 뒤 arrange 가 끝난 시점을 노린다.
    setTimeout(_correctFreeGrowth, 80);
    // 왜(Why) 정착했을 때만 키를 기록하나 (2026-10-11 실측): 줄이기가 드래그
    // 중 보류되면 count > desired 인 채로 끝난다. 이때 키를 기록하면 다음
    // 트리거가 조기 반환해 보류된 축소가 영영 안 된다. 정착한 경우에만
    // 기록해서 미완료 상태에서는 다음 트리거가 다시 돌게 한다(키퍼 JS 와 같음).
    if (count === desired) {
      node._goriScanKey = scan.count + ":" + lastLinked;
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

/* --- 소켓 가시성 갱신 스케줄러 (디바운스) ---
 *
 * 왜(Why) 디바운스인가 (2026-10-02): 코어는 링크를 **하나씩** 연결/해제할 때마다
 * onConnectionsChange 를 부른다 (프론트엔드 1.53.6 번들 실측 — 다중 선택 드래그로
 * 5개를 한 번에 붙이면 5회 연속 호출). 그때마다 setTimeout 을 새로 예약했으므로
 * 갱신이 5번 반복되고, 매번 inputs 배열을 끝까지 훑으며 addInput/removeInput 을
 * 부른다. 50ms 로 묶으면 **마지막 상태에서 한 번만** 돈다.
 *
 * 왜(Why) 지연이 눈에 안 띄나: 소켓 하나를 노출하는 데는 사람이 링크를 놓는
 * 클릭 간격(수백 ms)이 걸린다. 50ms 는 그 안쪽이라 지연이 아니라
 * "연결 확정" 으로 읽힌다. 체감 지연으로 측정되지는 않는다.
 *
 * 왜(Why) WeakMap 인가: 노드마다 타이머 핸들을 들고 있으면 노드가 캔버스에서
 * 지워진 뒤에도 **타이머가 살아 있다** (WeakMap 엔트리만 사라지고 setTimeout 은
 * 남는다). 그래서 지연이 끝난 시점에 그래프에 아직 있는지 확인하고, 없으면
 * 아무것도 하지 않는다. */
const visibilityTimers = new WeakMap();
/* beforeRegisterNodeDef 가 채운다. 대상 노드 타입이 하나뿐이므로 전역 1개. */
let IMAGE_TEMPLATE = [];

function scheduleVisibilityUpdate(node) {
  if (!node) return;
  const prev = visibilityTimers.get(node);
  if (prev !== undefined) clearTimeout(prev);
  visibilityTimers.set(node, setTimeout(() => {
    visibilityTimers.delete(node);
    // 노드가 이미 지워졌으면 만지지 않는다 — addInput 은 무의미하다.
    const nodes = app.graph?._nodes;
    if (Array.isArray(nodes) && !nodes.includes(node)) return;
    try {
      if (!node._goriImageTemplate?.length) node._goriImageTemplate = IMAGE_TEMPLATE;
      updateVisibility(node);
    } catch (_) {
      restoreAll(node);
    }
  }, VISIBILITY_DEBOUNCE_MS));
}

// ----- topic 위젯 크기(하한 2줄) + 휠 스크롤 -------------------------------
// 1.53.10 프런트엔드 실측: 위젯 높이의 진실은 프런트엔드가 쥔다 — DOM 위젯의
// 최소 높이는 options.getMinHeight(없으면 요소 CSS 변수, 없으면 50px)로
// 정해지고, **상한 콜백이 없는 위젯이 노드의 남는 공간을 전부 흡수한다**
// (distributeSpace). 이 노드에서 흡수 위젯은 topic 하나다. 사용자 지시
// (2026-10-17): 꺼냈을 때 표시되는 크기가 2칸(하한), 노드를 키우면 topic
// 칸이 같이 커질 것(상한 없음 → 남는 공간이 전부 여기로), 노드 하단에 빈
// 공간이 남지 않을 것. 그래서 **하한만** 2줄 측정값으로 묶고(아래
// applyFixedTextareaHeight) 새 노드는 남는 공간이 0 인 높이로 줄인다
// (shrinkNewNode — 프런트엔드 회계상 computeSize 최소치보다 약 16px 작다).
// 위젯 자체는 resize:none 이라 크기 조절은 노드 코너 드래그로만 하고,
// 텍스트가 넘치면 칸 안에서 휠 스크롤한다. 노드가 스스로 커지는 자동
// 확장은 하지 않는다 — 여러 노드를 오자와 열에 맞춰 정돈해 두면 자동 크기
// 변화가 배치를 흐트러뜨린다.

/** topic textarea의 DOM 요소 (없으면 null) */
function topicElement(node) {
    const w = (node?.widgets || []).find((x) => x?.name === "topic");
    return w?.element ?? null;
}

/** [w, h] 모양인가 — 노드 크기 판정.
 * 왜(Why) Array.isArray 로는 안 되나 (2026-10-17 라이브 실측): 프런트엔드는
 * node.size 를 Float32Array 로 들고 있다(프로브 덤프 {"0":400,"1":888},
 * Array.isArray 는 false). 이 판정을 Array.isArray 로 쓰던 곳들이 통째로
 * 죽은 코드가 됐다 — shrinkNewNode 가 그래서 새 노드를 2칸으로 줄이지
 * 못했고(초기 2칸 실패의 원인), 소켓 해제 높이 보정(updateVisibility)과
 * 팝업 앵커(computePopupScreenPos)도 같이 죽어 있었다. plain array 와
 * typed array 를 모두 받는다. */
function isSizeLike(v) {
  return !!v && typeof v.length === "number" && v.length >= 2
    && typeof v[0] === "number" && typeof v[1] === "number";
}

/** 새 노드의 높이를 "topic 2칸 + 남는 공간 0" 인 높이로 줄인다 (폭은 유지).
 * 왜(Why) computeSize() 최소치가 아닌가: 프런트엔드는 computeSize 예산에
 * 위젯마다 +4 와 꼬리 +8/+6 을 남기는데 실제 배치는 그 값을 소비하지 않는다
 * (1.53.10 실측 — V1 은 그래서 최소치에서 하단 16px 공백이 생겼다).
 * freeWidgetSpace 는 프런트엔드가 마지막 배치에서 노드에 심어 둔 여유값
 * 이라 "여유가 캡과 같아지는 높이"를 역산할 수 있다:
 * h = 현재높이 - (여유 - 캡). 제목·슬롯 높이는 약분된다. 값이 없거나
 * (배치 전) 여유가 이미 캡 이하면 computeSize() 최소치로만 줄인다. */
function shrinkNewNode(node) {
  if (typeof node?.computeSize !== "function") return;
  if (!isSizeLike(node.size)) return;
  const min = node.computeSize();
  if (!isSizeLike(min)) return;
  let h = min[1];
  const w = (node.widgets || []).find((x) => x?.name === "topic");
  const free = node.freeWidgetSpace;
  if (w && typeof free === "number") {
    const cap = topicWidgetHeight(w, w.element);
    if (free > cap) h = node.size[1] - (free - cap);
  }
  if (node.size[1] > h) {
    node.setSize([Math.max(node.size[0], min[0]), h]);
  }
}

/** 로드된 노드를 **저장된 크기**로 되돌린다 (F5 재현 버그 수정, 2026-10-19).
 *
 * 왜(Why) 필요한가 (2026-10-19 라이브 실측): F5/컴피 재시작으로 워크플로를 열면
 * 노드 정의가 image_1~image_10 소켓 10개를 먼저 만든다. 저장된 노드 높이(예:
 * 612)는 소켓이 1개일 때의 값이라 10개를 못 담는다 → 프런트엔드가 콘텐츠에
 * 맞춰 노드를 **756 으로 자동 확장**한다(expandToFitContent). 그 뒤
 * updateVisibility 가 미연결 소켓 9개를 제거하지만 `_goriLoaded` 가 높이 감산을
 * 건너뛰므로(저장 크기 존중) 노드가 756 에 남는다. 남는 여유(206px)를 상한 없는
 * topic 위젯이 전부 흡수해 topic 칸이 2줄(≈38px)에서 167px 로 부풀었다 —
 * "새로고침하면 topic 이 커진다" 의 직접 원인(실측 재현).
 *
 * 왜(Why) shrinkNewNode 를 그냥 부르지 않나: 그 함수는 `size-(free-cap)` 로
 * 여유를 접는데, **사용자가 코너를 끌어 키운 노드도 같은 방식으로 접어**
 * 의도한 리사이즈를 되돌린다(실측: 수동 900 → 612 로 붕괴). 그래서 로드
 * 경로에서는 "저장된 크기" 자체를 복원해야 한다 — 저장 크기가 곧 사용자가
 * 남겨 둔 의도(2줄이면 2줄, 키웠으면 키운 값)다.
 *
 * 왜(Why) `_goriSavedSize` 와 복원 대상이 다른가: onConfigure 가 저장된
 * 크기를 심는다. 자동 확장은 그보다 **뒤**에 일어나므로, 현재 높이가 저장
 * 높이보다 크면 그 차이는 확장분이다 — 저장 높이로 되돌리면 여유가 사라져
 * topic 이 원래 줄 수로 돌아온다(실측: 756 → 612 로 되돌리면 topic 38px,
 * free 62px=cap). 저장 높이 이하로는 절대 줄이지 않는다(사용자 축소 의도 보존).
 *
 * 매 드로우에서 불려도 싸다 — 값이 같으면 대입하지 않는다. 좁은 폭으로
 * 리사이즈된 경우 폭은 건드리지 않는다(높이만 복원).
 *
 * 왜(Why) 시간 창이 필요한가 (2026-10-19 라이브 실측): 복원을 영구히 켜 두면
 * **사용자가 나중에 코너를 끌어 키운 리사이즈까지 저장 크기로 되돌린다**
 * (실측: 수동 900 → 즉시 612 로 붕괴). 자동 확장은 로드 직후 ~600ms 안에만
 * 일어나므로, 그보다 넉넉한 창(기본 1500ms) 동안만 복원하고 이후엔 손대지
 * 않는다. 창이 지나면 사용자 리사이즈가 그대로 살아남는다. */
const SAVED_SIZE_RESTORE_WINDOW_MS = 1500;
function restoreSavedSize(node) {
  const saved = node?._goriSavedSize;
  if (!isSizeLike(saved) || !isSizeLike(node.size)) return;
  // 로드 직후 창 안에서만 복원한다. 창 밖은 사용자 리사이즈 영역이다.
  const until = node._goriRestoreUntil;
  if (typeof until === "number" && Date.now() > until) return;
  // 저장 높이보다 **크면** 확장분이다 — 저장 높이로 되돌린다.
  // 이미 저장 높이 이하면(사용자가 더 줄였거나 확장이 없었거나) 손대지 않는다.
  if (node.size[1] > saved[1]) {
    node.setSize([node.size[0], saved[1]]);
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
const TOPIC_ELS = new WeakSet();
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

/** topic·llm_hint textarea **하한** 높이 — **2줄** (2026-10-17 사용자 지시).
 * 왜(Why) 하한인가: 두 위젯은 노드 높이가 변할 때마다 함께 늘어나고, 줄이면
 * 잘린다. 노드 코너 드래그 하한이 이 밑으로 못 내려가게 잠근다. 상한은 열어
 * 두어 노드를 키우면 칸이 같이 커진다(사용자 지시 2026-10-17 — 리사이즈가
 * 고정이면 안 된다).
 * 왜(Why) 2줄인가: 2026-10-12 에는 1줄 최소치였으나, 노드를 꺼냈을 때의 초기
 * 표시가 2줄이어야 한다는 사용자 지시(2026-10-17)로 올렸다. 넘치는 텍스트는
 * 칸 안에서 휠 스크롤한다(위 TOPIC_ELS 핸들러).
 * 왜(Why) 상수가 아니라 **측정**인가: 글꼴·줄간격·패딩이 프런트엔드 판마다
 * 다르다. 상수로 박으면 어떤 판에서 잘리거나 남는다. */
const FIXED_TEXTAREA_LINES = 2;
const FIXED_TEXTAREA_FALLBACK_PX = 42;

/** textarea 의 고정 높이(px) = FIXED_TEXTAREA_LINES 줄 + 패딩.
 * 캔버스 DOM 밖(계산된 스타일이 비어 있음)이면 알려진 실측 근사치를 돌려준다 —
 * 값의 신뢰가 생기는 곳에서만 캐시한다(applyFixedTextareaHeight). */
function textareaFixedHeight(el) {
  try {
    const cs = window.getComputedStyle(el);
    const fsRaw = parseFloat(cs.fontSize);
    const lhRaw = parseFloat(cs.lineHeight);
    if (!isFinite(fsRaw) && !isFinite(lhRaw)) {
      return FIXED_TEXTAREA_FALLBACK_PX; // 미부착 — 계산된 스타일 없음
    }
    let lh = lhRaw;
    if (!isFinite(lh) || lh <= 0) {
      lh = (isFinite(fsRaw) && fsRaw > 0 ? fsRaw : 13) * 1.45;
    }
    const pad = (parseFloat(cs.paddingTop) || 0)
      + (parseFloat(cs.paddingBottom) || 0);
    const bord = (parseFloat(cs.borderTopWidth) || 0)
      + (parseFloat(cs.borderBottomWidth) || 0);
    const extra = (cs.boxSizing === "border-box") ? (pad + bord) : 0;
    const px = Math.ceil(lh * FIXED_TEXTAREA_LINES + extra);
    return px > 0 ? px : FIXED_TEXTAREA_FALLBACK_PX;
  } catch (_) {
    return FIXED_TEXTAREA_FALLBACK_PX;
  }
}

/** 위젯 레이아웃 높이(px) = textarea 높이 + 위·아래 margin.
 * 프런트엔드(1.53.10 실측)는 DOM 요소 높이를 "위젯 레이아웃 높이 - 2*margin"
 * 으로 배치한다(GraphView 의 DOM 위젯 레이어). 그래서 이 값이 요소 높이의
 * 환산 기준이다 — 레이아웃 **하한**(레이아웃 캡)으로 쓰면 요소가 2줄이 되고,
 * 요소 style 은 건드리지 않는다(프레임워크 배치를 이기면 리사이즈가 안 먹는다).
 * 캐시는 부착 후에만 — 미부착 측정은 틀릴 수 있고, 틀린 값이 캐시되면
 * 드로우 훅이 다시 재지 않는다. */
function topicWidgetHeight(w, el) {
  const px = el && el.isConnected
    ? (el._goriFixedPx || (el._goriFixedPx = textareaFixedHeight(el)))
    : textareaFixedHeight(el);
  const m = typeof w?.margin === "number" ? w.margin : 10;
  return px + m * 2;
}

/** topic·llm_hint 의 **하한** 높이를 2줄(측정값)로 묶는다 — 상한은 열어 둔다.
 * 1) 레이아웃 하한: options.getMinHeight 를 주입한다. 프런트엔드(1.53.10
 *    실측)는 이 값을 위젯 최소 높이로 읽는다(computeLayoutSize). 노드를
 *    2줄 아래로 줄여도 이 밑으로는 안 내려가고, 노드 코너 드래그의 하한도
 *    computeSize() 를 타므로 이 캡이 지킨다. computeSize 도 이 값을 읽으므로
 *    DOM 부착 전에도 먼저 건다.
 *    상한 콜백(maxHeight)은 **일부러 설치하지 않는다** — 상한이 없어야
 *    노드의 남는 공간을 topic 이 전부 흡수해(distributeSpace) 노드를 키울
 *    때 2줄 위로 같이 커지고(사용자 지시 2026-10-17), 하단에 회색 공백이
 *    남지 않는다. 상한을 주면 남는 공간이 굳어 하단 공백이 된다(V1 실측).
 * 2) 요소 style 은 **건드리지 않는다**: 프런트엔드가 위젯 레이아웃 높이 -
 *    2*margin 으로 DOM 요소를 매 프레임 배치한다(GraphView 실측). 요소
 *    height/min/max 를 우리가 고정하면 이 배치를 이겨서 리사이즈가 안
 *    먹는다. 배치를 그대로 따르게 두면 레이아웃 높이만 조절하면 요소가
 *    자동으로 채운다.
 * rows 는 부착 후에만 맞춘다 — 미부착 요소는 줄 수가 화면에 의미가 없다.
 * 값이 이미 맞으면 **대입하지 않는다** — 매 드로우에서 불리는 함수라 무조건
 * 대입하면 스타일 재계산이 프레임마다 돈다. 측정값은 **요소에** 캐시한다
 * (새 요소가 붙으면 자동으로 다시 잰다 — DOM 재마운트 대응). */
function applyFixedTextareaHeight(node) {
  // 2026-10-17 실측 교훈: 여기가 ("topic", "llm_hint") 였다. 콤마 연산자라
  // "llm_hint" 문자열의 **문자 단위**로 순회해 어느 위젯도 찾지 못했고,
  // 이 함수 전체가 조용한 죽은 코드였다(1.9.36~42 의 고정 높이가 안 먹은 원인).
  for (const name of ["topic", "llm_hint"]) {
    const w = (node.widgets || []).find((x) => x.name === name);
    const el = w?.element;
    if (!el) continue;
    if (w.options) {
      if (!w._goriLayoutCap) {
        // 호출 시점에 w.element 를 읽는다 — DOM 재마운트로 요소가 교체돼도
        // 낡은 요소를 재지 않는다.
        w._goriLayoutCap = () => topicWidgetHeight(w, w.element);
      }
      if (w.options.getMinHeight !== w._goriLayoutCap) {
        w.options.getMinHeight = w._goriLayoutCap;
      }
    }
    if (!el.isConnected) continue;
    if (el.rows !== FIXED_TEXTAREA_LINES) el.rows = FIXED_TEXTAREA_LINES;
  }
}

/** 하한 캡·rows 를 **매 드로우에서** 다시 보장한다.
 * 왜(Why) 드로우 훅인가 (2026-10-12 사용자 지시): 레이아웃/위젯 배치가 매
 * 프레임 다시 돌기 때문에 생성 시 한 번만 적용하면 새로고침·소켓 연결/해제
 * 후 값이 달라진다. 드로우 직후 보정하면 사용자가 보는 값이 항상 같다.
 * 값이 같으면 대입하지 않으므로 비용은 비교뿐이다. */
function ensureFixedTextareaDrawHook(node) {
  if (node._goriFixedTextareaHooked) return;
  node._goriFixedTextareaHooked = true;
  const prev = node.onDrawForeground;
  node.onDrawForeground = function (ctx) {
    prev?.apply(this, arguments);
    try {
      attachTopicScroll(this);
      applyFixedTextareaHeight(this);
      // 로드된 노드의 자동 확장분을 저장 크기로 되돌린다 (2026-10-19 F5 버그).
      // 매 프레임 불리지만 값이 같으면 대입하지 않으므로 비용은 비교뿐이고,
      // 확장은 로드 직후 한 번뿐이라 몇 프레임 뒤 자연히 no-op 이 된다.
      restoreSavedSize(this);
    } catch (_) {
      /* 보정 실패는 조용히 무시 — 다음 프레임에 다시 시도한다 */
    }
  };
}

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
  // 왜(Why) WeakSet 인가(2026-10-02): 예전 Set 는 **DOM 요소를 강하게** 잡는다.
  // 노드를 지울 때 onRemoved 훅으로 delete 하던 구조였는데, 그 훅이 다른
  // 확장에 의해 먼저 교체되거나 실행되지 않으면 요소가 영영 회수되지 않는다
  // (캔버스 DOM은 수천 개). WeakSet 는 참조가 사라지면 자동으로 빠지므로
  // 정리 자체가 필요 없다. 그래서 onRemoved 후킹도 **제거했다** — 후킹이
  // 하나 줄면 다른 확장과 충돌할 자리도 하나 줄어든다.
  TOPIC_ELS.add(el);
}

/* ---------------------------------------------------------------------------
 * api_key 마스킹 (방송/녹화용 가림막)
 *
 * 한 줄 STRING 위젯(api_key)은 캔버스 TextWidget으로 그려지며, 그리기 경로는
 * 베이스 클래스의 `_displayValue` getter를 읽는다(1.52.7 프론트엔드 실측).
 * 인스턴스에 `_displayValue`만 재정의해 화면에는 ●●●●를 그리고,
 * `value` 자체는 절대 건드리지 않는다 → 실행·큐·워크플로 JSON 저장값은
 * 원본 그대로 유지된다.
 *
 * 고정 8자리를 쓰는 이유: 자릿수 비례 마스킹은 키 길이를 노출한다.
 * 빈 값이면 빈 문자열을 돌려줘 "키 없음" 상태가 그대로 보인다.
 *
 * 편집(더블클릭): TextWidget.onClick이 여는 canvas.prompt 다이얼로그
 * (<input type='text' class='value'>, 동기 생성)의 input을 password로
 * 바꿔 입력 중에도 키가 노출되지 않게 한다. 값 자체는 원본이 오간다.
 *
 * 확정(OK 버튼·Enter) 시 provider 칸 기준으로 루트 .env에 반영한다
 * (POST /gori_api_key — 저장·삭제·교체). 빈 값 확정은 삭제다.
 * Esc·마우스이탈로 닫으면 동기화하지 않는다.
 *
 * 저장 파일의 키 제외는 아래 hookSerializeBlankApiKey가 담당한다.
 * ------------------------------------------------------------------------- */
const API_KEY_MASK = "●●●●●●●●";

/** api_key 위젯 찾기 (없으면 undefined) */
function findApiKeyWidget(node) {
  try {
    return (node?.widgets || []).find((x) => x && x.name === "api_key");
  } catch (_) {
    return undefined;
  }
}

function maskApiKeyWidget(node) {
  try {
    const w = findApiKeyWidget(node);
    if (!w || w._goriMasked) return;
    w._goriMasked = true;
    // 1) 표시 마스킹 (그리기 경로만 가로챈다)
    try {
      Object.defineProperty(w, "_displayValue", {
        configurable: true,
        get() {
          const v = this.computedDisabled ? "" : String(this.value ?? "");
          return v ? API_KEY_MASK : "";
        },
      });
    } catch (_) {
      /* getter 재정의 실패 시 편집 가림만 적용 */
    }
    // 2) 편집 다이얼로그 가림 + 3) 확정(OK/Enter) 시 루트 .env 반영
    const origClick = w.onClick;
    if (typeof origClick === "function") {
      w.onClick = function (arg) {
        const r = origClick.call(this, arg);
        try {
          const box = arg?.canvas?.prompt_box;
          const input = box?.querySelector?.("input.value");
          if (input) input.type = "password";
          // OK 버튼·Enter 확정만 동기화한다 (Esc·마우스이탈 닫기는 무시).
          // 빈 값 확정 = 메모장에서 삭제, 새 값 = 교체. 제공자는 provider 칸 기준.
          const okBtn = box?.querySelector?.("button");
          if (input && okBtn) {
            const sync = () => {
              try {
                const prov = String(
                  (node.widgets || []).find((x) => x && x.name === "provider")?.value || "");
                const key = input.value ?? "";
                fetch("/gori_api_key", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ provider: prov, key }),
                })
                  .then((r) => (r && typeof r.json === "function" ? r.json() : null))
                  .then((data) => {
                    // 저장 확인 전에 위젯을 지우면 키를 잃는다. 서버가
                    // "루트 .env 에 넣었다" 고 확인해 준 경우에만 지운다.
                    // 그래서 실행은 .env 에서 키를 읽는다(llm_client.py:494-503).
                    if (!data || !data.ok) return;
                    if (String(key).trim() &&
                        String(w.value ?? "").trim() === String(key).trim()) {
                      clearApiKeyWidget(node);
                    }
                  })
                  .catch(() => {
                    /* 전송 실패는 무시 — 위젯값 그대로 실행되므로 안전하다 */
                  });
              } catch (_) {
                /* 전송 실패는 무시 — 위젯값 실행에는 영향 없음 */
              }
            };
            okBtn.addEventListener("click", sync);
            input.addEventListener("keydown", (e) => {
              if (e && e.key === "Enter") sync();
            });
          }
        } catch (_) {
          /* 가림 실패는 무시 — 값 동작에 영향 없음 */
        }
        return r;
      };
    }
    setCanvasDirty();
  } catch (_) {
    /* 마스킹 실패는 노드 동작에 영향을 주지 않는다 */
  }
}

/** 공유 전 키 제거용: api_key 위젯 값을 비운다 (value setter가 dirty 처리).
 * 빈 값이면 false를 돌려줘 메뉴 비활성화 판단에 쓴다. */
function clearApiKeyWidget(node) {
  try {
    const w = findApiKeyWidget(node);
    if (!w || !String(w.value ?? "")) return false;
    w.value = "";
    return true;
  } catch (_) {
    return false;
  }
}

/** 이 노드의 api_key 가 widgets_values 에 들어가는 위치 인덱스.
 *
 * 왜(Why) 이 계산인가: 저장 payload 의 widgets_values 는 위젯 순서대로
 * 채워지되 serialize === false 인 위젯은 코어 규칙대로 건너뛴다.
 * 그 규칙을 모르면 다른 위치(예: 15 가 아니라 16)를 빈칸으로 만들어
 * provider 나 pf_steps 를 망가뜨린다. 못 찾으면 -1 이고 호출측이 방어한다. */
function apiKeyWidgetIndex(node) {
  try {
    let index = 0;
    for (const w of node?.widgets || []) {
      if (w && w.serialize === false) continue;
      if (w && w.name === "api_key") return index;
      index++;
    }
    return -1;
  } catch (_) {
    return -1;
  }
}

/** 저장 payload 한 건에서 이 노드의 api_key 를 세 군데 전부 비운다.
 *
 * 왜(Why) 세 군데인가: 프론트엔드 1.53.6 실측에서 워크플로 파일에 키가
 * 들어가는 자리는 정확히 두 곳이었다 (widgets_values[n], widgets_values_named).
 * properties 는 그때 깨끗했지만(측정함) 다른 버전에서 값이 남는 경우가
 * 있어 비용이 0 인 보험으로 함께 비운다.
 *
 * 반환값은 그대로 내보낸다. 실행 경로(app.graphToPrompt)는 이 함수를
 * 호출하지 않으므로 실행은 영향을 받지 않는다. */
function blankApiKeyInWorkflowData(data, graph) {
  try {
    const nodes = data?.nodes;
    if (!Array.isArray(nodes)) return;
    for (const saved of nodes) {
      if (!saved || saved.type !== CAMERA_NODE_TYPE) continue;
      if (saved.widgets_values_named &&
          Object.prototype.hasOwnProperty.call(saved.widgets_values_named, "api_key")) {
        saved.widgets_values_named.api_key = "";
      }
      const live = graph?._nodes_by_id?.[saved.id];
      const index = live ? apiKeyWidgetIndex(live) : -1;
      if (index >= 0 && Array.isArray(saved.widgets_values) && index < saved.widgets_values.length) {
        saved.widgets_values[index] = "";
      }
      // index < 0(라이브 노드가 없음)이면 위치 대응을 지어내지 않는다.
      // 나머지 두 곳은 이름이라서 상관없이 지워진다.
      if (saved.properties &&
          Object.prototype.hasOwnProperty.call(saved.properties, "api_key") &&
          saved.properties.api_key) {
        saved.properties.api_key = "";
      }
    }
  } catch (_) {
    /* 저장 경로 실패를 파급시키지 않는다 */
  }
}

/** 저장 payload 전용 그래프 후킹. 실행 payload 는 app.graphToPrompt 라
 * 별개 경로이고 이 훅은 건드리지 않는다.
 *
 * 왜(Why) 그래프 단위인가: **실측함.** 프론트엔드 1.53.6 의 app.graph.serialize()
 * 는 LGraphNode.serialize() 를 호출하지 않는다(호출 추적 결과 0회).
 * 워크플로 파일에 쓰이는 값은 그래프가 widgets_values / widgets_values_named 를
 * 직접 만든다. 그래서 노드 단위 후킹만 해 두면 저장 시 100% 새어 나간다 —
 * 2026-10-03 14:08 저장 파일에서 실제로 두 곳에 키가 들어 있었다. */
function hookGraphSerializeBlankApiKey(graph) {
  try {
    if (!graph || graph._goriGraphSerializeHooked) return false;
    const orig = graph.serialize;
    if (typeof orig !== "function") return false;
    graph._goriGraphSerializeHooked = true;
    graph.serialize = function (...args) {
      const data = orig.apply(this, args);
      blankApiKeyInWorkflowData(data, this);
      return data;
    };
    return true;
  } catch (_) {
    return false;
  }
}

/* ---------------------------------------------------------------------------
 * 워크플로 저장 시 api_key 빈칸 직렬화 (공유 안전) — 노드 단위 후킹
 *
 * **옛 설명 (1.52.7 기준) 이 맞지 않았다. 정정한다.**
 * "저장 파일은 node.serialize() 결과를 쓴다" 는 1.53.6 에서 성립하지 않는다.
 * 실측  app.graph.serialize() → LGraphNode.serialize() 호출 0회.
 * 그래서 이 함수는 이제 **두 번째 방어선** 이다. 첫 방어선은 위의
 * hookGraphSerializeBlankApiKey 다. 프론트엔드가 node.serialize() 를 다시
 * 쓰기 시작하면 이쪽도 그대로 동작한다. 둘 다 남긴다.
 *
 * 실행 페이로드는 live 위젯 값을 직접 읽는다(app.graphToPrompt 실측 3회).
 * serialize 결과만 고쳐서 실행은 그대로 두고 밖으로 나가는 파일에서만
 * 키를 뺀다. (PNG 내장 prompt 사본은 서버 실행 시 이 노드가 제거한다)
 *
 * 미연결 방치 노드: computeExecutionOrder 는 미연결 노드도 실행 목록에
 * 포함하므로, 출력이 하나도 연결 안 된 노드는 실행 페이로드에도 키를
 * 내보내지 않는다(serializeValue 가드). 출력 연결 노드는 실값 그대로.
 * 뮤트/우회는 코어가 output 에서 제외하므로 별도 처리 불필요.
 * ------------------------------------------------------------------------- */
function hookSerializeBlankApiKey(node) {
  try {
    if (!node || node._goriSerializeHooked) return;
    const orig = node.serialize;
    if (typeof orig !== "function") return;
    node._goriSerializeHooked = true;
    node.serialize = function (...args) {
      const info = orig.apply(this, args);
      try {
        // 이름 기준 (정렬 문제 없음)
        if (info?.widgets_values_named &&
            Object.prototype.hasOwnProperty.call(info.widgets_values_named, "api_key")) {
          info.widgets_values_named.api_key = "";
        }
        // 위치 배열 (코어와 같은 순서로 serialize 제외 위젯 건너뜀)
        if (info && Array.isArray(info.widgets_values)) {
          const index = apiKeyWidgetIndex(this);
          if (index >= 0 && index < info.widgets_values.length) {
            info.widgets_values[index] = "";
          }
        }
        // properties 사본 (1.53.6 저장 경로에서는 깨끗했지만 방어선)
        if (info?.properties &&
            Object.prototype.hasOwnProperty.call(info.properties, "api_key") &&
            info.properties.api_key) {
          info.properties.api_key = "";
        }
      } catch (_) {
        /* 직렬화 실패 파급 방지 */
      }
      return info;
    };
  } catch (_) {
    /* 후킹 실패는 노드 동작에 영향을 주지 않는다 */
  }
}

/** 실행 페이로드용 serializeValue 가드: 출력 미연결(방치) 노드는 키 제외.
 * 출력이 하나라도 연결돼 있으면 실값 그대로 (정상 실행 보장).
 * live 값은 건드리지 않아 뮤트 해제·선 연결 즉시 원상복구된다. */
function hookApiKeyPayloadGuard(node) {
  try {
    const w = findApiKeyWidget(node);
    if (!w || w._goriPayloadHooked) return;
    w._goriPayloadHooked = true;
    w.serializeValue = () => {
      try {
        const outs = node.outputs || [];
        if (outs.length && outs.every((o) => !o || !(o.links && o.links.length))) return "";
        return w.value;
      } catch (_) {
        return w.value;
      }
    };
  } catch (_) {
    /* 후킹 실패는 노드 동작에 영향을 주지 않는다 */
  }
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
// 왜(Why) 프로토 없는 객체인가: 상태 이름은 웹소켓 페이로드에서 온다.
// 일반 객체로 만들면 state="toString" 같은 값이 **상속된 함수**를 집어와
// spec.fadeMs 가 undefined 가 되며, 게다가 나중에 그 함수로 무엇을 하든
// 이 테이블이 오염될 수 있다. prototype 이 null 이면 오직 자기 키만 잡힌다.
const LLM_LIGHT_STYLE = Object.assign(Object.create(null), {
  busy: { color: "#35d07f", blink: true, fadeMs: 0 },
  on: { color: "#35d07f", blink: false, fadeMs: 6000 },
  fail: { color: "#e05555", blink: false, fadeMs: 9000 },
});

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

/** "busy" 인 노드가 하나라도 있는지. 점멸 타이머를 돌릴지 결정한다.
 *
 * 왜(Why) 그래프를 훑는가: 표시등은 노드별 상태라 그래프를 봐야 한다.
 * 그래도 **타이머가 이미 도는 중이면 다시 훑지 않는다** — 그 사이 상태 변화는
 * applyLlmLight 가 항상 이 함수를 다시 부르므로, 이미 도는 타이머는 곧바로
 * 확인하고 돌아가는 게 아니다. 캐시가 아니라 **상태 변화로만** 재평가한다. */
function anyNodeBlinking() {
  try {
    const nodes = app.graph?._nodes;
    if (!Array.isArray(nodes)) return false;
    for (const n of nodes) {
      if (n && n._goriLlmState === "busy") return true;
    }
    return false;
  } catch (_) {
    return false;
  }
}

function updateBlinkTimer() {
  const blinking = anyNodeBlinking();
  if (blinking && !llmBlinkTimer) {
    llmBlinkTimer = setInterval(setCanvasDirty, 60);
  } else if (!blinking && llmBlinkTimer) {
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

/** LLM 표시줄에 표시등을 캔버스로 그린다 (node 로컬 좌표).
 * 표시줄은 **ai_llm_setup 헤더**다 (2026-10-17 — 섹션 접기 도입): model 줄은
 * 접히면 안 보이는데 표시등은 접혀 있어도 계속 와야 한다(실행 중 여부 표시).
 * 헤더가 아직 없거나 자리가 없으면 model 줄로 대체한다(설치 직후 1프레임). */
function drawLlmLight(node, ctx) {
  const state = node._goriLlmState;
  if (!state) return;
  const spec = LLM_LIGHT_STYLE[state];
  if (!spec) return;
  if (spec.fadeMs && Date.now() > (node._goriLlmUntil || 0)) {
    node._goriLlmState = null;
    return;
  }
  const hw = findLlmHeaderWidget(node);
  const w = (hw && typeof hw.y === "number")
    ? hw
    : (node.widgets || []).find((x) => x && x.name === "model");
  if (!w || typeof w.y !== "number") return;
  let alpha = 1;
  if (spec.blink) {
    alpha = 0.35 + 0.65 * Math.abs(Math.sin(Date.now() / 180));
  }
  // 왜(Why) 작은 원 하나인가 (2026-10-03 실측): 여기 원래 **노드 전체 너비의
  // 테두리 사각형**을 그렸다(bw = nodeWidth - 8). 문서화된 의도("초록 점멸",
  // 이 파일 447행 · camera_director.py:329)는 LED 였는데 화면에는 가로 바로
  // 보였다. 노드를 늘리면 바도 함께 늘어나고, shadowBlur 9 가 그 테두리를
  // 발광시켜 "이상한 가로 빛" 으로 읽혔다. 표시등은 **크기가 고정**이어야 한다.
  const cx = 10;
  const cy = w.y + 12;
  const r = 4;
  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.fillStyle = spec.color;
  ctx.strokeStyle = spec.color;
  ctx.lineWidth = 1;
  ctx.shadowColor = spec.color;
  ctx.shadowBlur = 6;
  ctx.beginPath();
  if (typeof ctx.arc === "function") {
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
  } else {
    // arc 가 없는 캔버스 구현 대비. 사각형이어도 크기는 고정이다.
    ctx.rect(cx - r, cy - r, r * 2, r * 2);
  }
  ctx.fill();
  // 얇은 테두리를 한 겹 더 그린다. 어두운 노드 배경에서도 확실히 보인다.
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

// 하류 파이프라인 신호 (2026-10-21): 백엔드가 정지 이미지/영상 판정을 알린다.
// 2026-10-21: motion/motion2 위젯 이름에 "only video" 가 항상 붙으므로(라벨
// 재정의), 정지 이미지 판정 시 값에 붙이던 꼬리표는 제거했다. 이 신호는 노드
// 속성(_goriIsVideo)에 판정을 기록해 두는 용도로 유지한다(백엔드의
// notify_pipeline_type 과 짝 — 향후 표시·진단에 쓸 수 있게 남긴다).
app.api?.addEventListener?.("gori_pipeline_type", (event) => {
  try {
    const detail = event.detail || {};
    const id = Number(detail.node);
    const node = Number.isFinite(id) ? app.graph?.getNodeById?.(id) : null;
    if (!node) return;
    node._goriIsVideo = !!detail.is_video;
    app.canvas?.setDirty?.(true, true);
  } catch (_) {
    /* 무시 */
  }
});

// 새 실행이 시작되면 모든 표시등을 초기화 (직전 실행의 잔광 제거)
app.api?.addEventListener?.("execution_start", clearAllLlmLights);

/* ---------------------------------------------------------------------------
 * ai_llm_setup 섹션 헤더 + LLM 설정 접기 (2026-10-17)
 *
 * provider~vision_detail 6개 LLM 위젯이 motion2 아래부터 시작해 노드 중간을
 * 채운다. 규칙(auto)만 쓰는 사용자는 이 6칸을 볼 필요가 없어서, "AI LLM 설정"
 * 헤더 한 줄을 클릭하면 6칸이 접히고 노드 높이가 함께 줄어든다. 클릭하면 다시
 * 펼쳐진다.
 *
 * **기본 상태 = 접힘** (2026-10-18 사용자 지시 — 노드를 꺼낼 때 접힌 채로
 * 나온다). 저장된 값이 있으면 그것을 따르고, 없으면 새 노드는 접힘·로드는
 * 펼침이다 (로드 경로는 크기를 안 건드리므로, 이 기능 이전에 저장된 펼친
 * 크기에 접힘을 씌우면 하단에 빈 공간이 남는다 — resolveLlmFolded 참조).
 *
 * 헤더는 JS 전용 위젯(serialize:false)이라 워크플로 저장물에 **자체가 남지
 * 않는다** — widgets_values 는 23개 그대로이고, 실행 프롬프트(graphToPrompt)
 * 에도 들어가지 않는다(프롬프트는 options.serialize:false 를 본다 — INPUT_TYPES
 * 에 없는 이름이 프롬프트에 섞이면 서버 검증이 죽으므로 두 곳 모두 막는다).
 * 복원은 위치 기반이라 serialize:false 를 건너뛰므로 기존 워크플로의 값
 * 매핑은 어긋나지 않는다(번호 매핑은 건드리지 않는다 — F16 과 같은 규칙).
 *
 * 접힘 상태는 node.properties 에 남는다(node.properties 임의 키 생존 실측
 * 2026-10-17 — configure 가 키를 전부 복사한다). 접기 높이 차이도 properties
 * 에 남는다(gori_llm_fold_px) — 로드 직후엔 위젯 y 가 아직 없어서 배치를 못
 * 잰다(첫 arrange 전에 숨겨야 늘어남 보정이 없다 — 아래 applyLlmFoldFromProperties).
 *
 * 높이 계산(Why 배치 기준인가): 프런트엔드 _arrangeWidgets 는 위젯 1칸 =
 * computeSize+4 이고, DOM 위젯(extra_negative)은 남는 공간을 나눠 갖는다.
 * computeSize() 차이는 이 분배를 반영하지 않아 셀 때마다 어긋난다(파일 위
 * shrinkNewNode 주석의 "예산과 실제 배치의 괴리" 와 같은 종류). 그래서 접는
 * 순간의 **실제 y 좌표 차이**(pf_steps.y - provider.y)를 잰다 — 두 위젯이
 * 그룹을 앞뒤로 감싸고 있어 차이가 곧 그룹의 배치 높이가 된다. 접힌 뒤에는
 * 숨긴 위젯의 y 가 멈춰 있으므로 properties 에 남은 px 를 쓴다(socket 추가로
 * 전체 y 가 밀려도 px 는 그대로라 정확하다).
 * ------------------------------------------------------------------------- */
const LLM_HEADER_NAME = "ai_llm_setup";
const LLM_HEADER_LABEL = "AI LLM 설정";
/** 접기 대상 6개. llm_hint 는 **빼야 한다** — 이미 hidden:True 인 위젯이라
 * 이 목록에 넣으면 펼칠 때 hidden=false 를 되돌려 UI 에 되살아난다(API·스크립트
 * 전용 위젯이 화면에 나온다). */
const LLM_FOLD_WIDGETS = [
  "provider", "model", "api_key", "custom_base_url",
  "extra_negative", "vision_detail",
];
const LLM_FOLD_PROP = "gori_llm_setup_folded";
const LLM_FOLD_PX_PROP = "gori_llm_fold_px";

function findLlmHeaderWidget(node) {
  try {
    return (node?.widgets || []).find((w) => w && w.name === LLM_HEADER_NAME);
  } catch (_) {
    return undefined;
  }
}

/** 접기 대상 위젯만 모은다 (순서는 LLM_FOLD_WIDGETS — 레이아웃 순서와 같음). */
function llmFoldGroupWidgets(node) {
  try {
    const ws = node?.widgets || [];
    return LLM_FOLD_WIDGETS
      .map((name) => ws.find((w) => w && w.name === name))
      .filter(Boolean);
  } catch (_) {
    return [];
  }
}

/** 접기 높이(px) = 그룹의 실제 배치 높이.
 * 1순위 y 좌표 차이 — 같은 arrange 결과에서 나온 값이라 배치와 정확히 일치.
 * 2순위 computedHeight 합 — 마지막 arrange 가 심어 둔 값(숨긴 위젯에도 남는다).
 * 3순위 computeSize+4 합 — 둘 다 없을 때의 근사치 (배치 간격과 같은 24px).
 * 측정 불가면 0 — 접기/펼치기에서 크기 보정만 생략된다(위젯 숨김/표시는 정상). */
function measureLlmFoldFootprint(node) {
  try {
    const ws = node?.widgets || [];
    const first = ws.find((w) => w && w.name === "provider");
    const after = ws.find((w) => w && w.name === "pf_steps");
    if (first && after &&
        typeof first.y === "number" && typeof after.y === "number") {
      const d = after.y - first.y;
      if (d > 0) return d;
    }
    let sum = 0;
    for (const w of llmFoldGroupWidgets(node)) {
      if (typeof w.computedHeight === "number" && w.computedHeight > 0) {
        sum += w.computedHeight;
      } else if (typeof w.computeSize === "function") {
        const h = w.computeSize(node?.size?.[0] || 300);
        sum += (Array.isArray(h) && typeof h[1] === "number" ? h[1] : 20) + 4;
      } else {
        sum += 24; // NODE_WIDGET_HEIGHT(20) + 배치 간격(4)
      }
    }
    return sum > 0 ? sum : 0;
  } catch (_) {
    return 0;
  }
}

/** LLM 섹션 접기/펼치기 (헤더 클릭). hidden 토글 + 노드 높이 보정 + 기록.
 * 접힘폭은 토글 **전에** 잰다(접힌 뒤 y 가 멈춰 있고, 펼칠 땐 properties px). */
function setLlmSectionFolded(node, folded) {
  try {
    if (!node) return false;
    const group = llmFoldGroupWidgets(node);
    if (!group.length) return false;
    const props = node.properties || (node.properties = {});
    const allHidden = group.every((w) => w.hidden === true);
    if (folded === allHidden && folded === !!props[LLM_FOLD_PROP]) return false;
    let px = 0;
    if (folded) {
      px = measureLlmFoldFootprint(node);
      if (px > 0) props[LLM_FOLD_PX_PROP] = px;
    } else {
      px = Number(props[LLM_FOLD_PX_PROP]) || 0;
      if (!(px > 0)) px = measureLlmFoldFootprint(node);
    }
    for (const w of group) w.hidden = folded;
    props[LLM_FOLD_PROP] = folded;
    // 왜(Why) 같은 흐름인가: 숨김과 리사이즈 사이에 arrange 가 끼면
    // _arrangeWidgets 가 topic 흡수/자동 증가로 노드를 되돌린다. setDirty 는
    // 다음 프레임에 arrange 를 돌게 할 뿐이라 여기서는 동기으로 맞춘다.
    if (px > 0 && isSizeLike(node.size)) {
      const h = folded ? node.size[1] - px : node.size[1] + px;
      node.setSize([node.size[0], Math.max(60, h)]);
    }
    setCanvasDirty();
    return true;
  } catch (_) {
    return false;
  }
}

function toggleLlmSectionFolded(node) {
  try {
    const group = llmFoldGroupWidgets(node);
    const cur = group.length > 0 && group.every((w) => w.hidden === true);
    return setLlmSectionFolded(node, !cur);
  } catch (_) {
    return false;
  }
}

/** 유효 접힘 상태 해석. 저장된 값(properties)이 있으면 그것을 따른다. 없으면
 * **새 노드는 접힘** — 꺼낼 때 AI LLM 설정이 접힌 채로 나온다(2026-10-18 지시).
 * 로드된 노드는 펼침: 이 기능 이전 저장물의 노드 크기는 펼친 크기이고 로드
 * 경로는 크기를 안 건드리므로, 속성이 없다고 접으면 하단에 빈 공간이 남는다. */
function resolveLlmFolded(node) {
  try {
    const props = node?.properties;
    if (props && Object.prototype.hasOwnProperty.call(props, LLM_FOLD_PROP)) {
      return !!props[LLM_FOLD_PROP];
    }
    return !node?._goriLoaded;
  } catch (_) {
    return false;
  }
}

/** 접힘 상태를 적용한다 — **hidden 만, 크기 무관.**
 * 왜(Why) 크기를 안 만지나: 접힌 채 저장된 노드의 크기는 이미 접힌 크기이고
 * (토글할 때 setLlmSectionFolded 가 맞춰 둔다), 새 노드의 높이는 뒤이어
 * shrinkNewNode 가 접힌 그룹을 반영해 줄여 준다.
 * 왜(Why) 동기으로(in onConfigure) 부르나: 늦게(디바운스 afterLifecycle)
 * 숨기면 첫 arrange 가 펼친 채로 노드를 자동 증가시켰다가 50ms 뒤 다시
 * 줄여서 하단에 공백이 남는다. configure 직후 onConfigure 는 첫 arrange
 * **전**이라 이 순서가 보장된다.
 * 새 노드 기본 접힘은 properties 에 기록한다 — 기록하지 않으면 저장 후
 * 재로드에서 속성이 없어 다시 펼쳐진다(헤더 화살표도 어긋난다). 접기폭
 * (gori_llm_fold_px)도 **접기 전에** 재서 함께 남긴다 — 접힌 뒤엔 잴 수 없다. */
function applyLlmFoldFromProperties(node) {
  try {
    const group = llmFoldGroupWidgets(node);
    if (!group.length) return false;
    const props = node.properties || (node.properties = {});
    const folded = resolveLlmFolded(node);
    if (folded === true) {
      // 접기폭도 함께 남긴다 (**접기 전에** 잰다). 안 남기면 펼칠 때가
      // 문제다 — 접힌 뒤엔 숨긴 위젯 y 가 멈추고 보이는 위젯은 위로 밀려
      // y 차이가 무너진다(실측: 차이 0). 그러면 computedHeight 합으로
      // 떨어져 배치 간격(+4/칸)이 빠진 값이 나온다.
      if (!Object.prototype.hasOwnProperty.call(props, LLM_FOLD_PX_PROP)) {
        const px = measureLlmFoldFootprint(node);
        if (px > 0) props[LLM_FOLD_PX_PROP] = px;
      }
      if (!Object.prototype.hasOwnProperty.call(props, LLM_FOLD_PROP)) {
        props[LLM_FOLD_PROP] = true;
      }
    }
    let changed = false;
    for (const w of group) {
      if (!!w.hidden !== folded) {
        w.hidden = folded;
        changed = true;
      }
    }
    if (changed) setCanvasDirty();
    return changed;
  } catch (_) {
    return false;
  }
}

/** 헤더를 motion2 바로 뒤에 넣는다 (1회 · JS 전용 · 저장되지 않는다).
 * motion2 다음(provider 앞)이므로 기존 위젯들의 상대 순서는 그대로다. */
function installLlmSetupHeader(node) {
  try {
    const widgets = node?.widgets;
    if (!Array.isArray(widgets)) return false;
    if (findLlmHeaderWidget(node)) return false;
    const idx = widgets.findIndex((w) => w && w.name === "motion2");
    if (idx < 0) return false;
    const hw = {
      type: "gori_llm_header",
      name: LLM_HEADER_NAME,
      value: "",
      // 저장(serialize)과 실행(graphToPrompt) 두 경로를 각각 막는다 —
      // 코어의 두 검사가 다른 키(widget.serialize / options.serialize)를 본다
      // (1.53.10 번들 실측). 한쪽만 막으면 한쪽으로 새어 나간다.
      serialize: false,
      options: { serialize: false },
      computeSize(width) {
        return [width, 20];
      },
      draw(ctx, n, width, y, H) {
        this.y = y;
        this.last_y = y;
        drawLlmSetupHeader(ctx, n, width, y, H);
      },
      mouse(event, pos, n) {
        const t = event?.type;
        if (t === "pointerdown" || t === "mousedown") {
          toggleLlmSectionFolded(n);
          return true;
        }
        return false;
      },
    };
    widgets.splice(idx + 1, 0, hw);
    return true;
  } catch (_) {
    return false;
  }
}

/** 헤더 한 줄: 가운데 라벨 + 좌우 구분선 + 접힘 화살표 (노드 로컬 좌표). */
function drawLlmSetupHeader(ctx, node, width, y, H) {
  try {
    const folded = resolveLlmFolded(node);
    const label = LLM_HEADER_LABEL;
    const cy = y + H / 2;
    ctx.save();
    ctx.textBaseline = "middle";
    ctx.textAlign = "center";
    ctx.fillStyle = "#cfe8ff";
    let tw = 72;
    if (typeof ctx.measureText === "function") {
      try {
        tw = ctx.measureText(label).width || tw;
      } catch (_) {
        /* 측정 실패 시 근사 폭 유지 */
      }
    }
    ctx.fillText(label, width / 2, cy);
    // 구분선 — 가운데 라벨과 오른쪽 화살표를 피해 그린다.
    // 왼쪽 시작(22)은 LLM 표시등(cx=10, r=4)이 앉을 자리를 비운다.
    ctx.strokeStyle = "#555";
    ctx.lineWidth = 1;
    const lx0 = 22;
    const lx1 = width / 2 - tw / 2 - 8;
    const rx0 = width / 2 + tw / 2 + 8;
    const rx1 = width - 24;
    ctx.beginPath();
    if (lx1 > lx0) {
      ctx.moveTo(lx0, cy);
      ctx.lineTo(lx1, cy);
    }
    if (rx1 > rx0) {
      ctx.moveTo(rx0, cy);
      ctx.lineTo(rx1, cy);
    }
    ctx.stroke();
    ctx.fillStyle = "#999";
    ctx.textAlign = "right";
    ctx.fillText(folded ? "▶" : "▼", width - 8, cy);
    ctx.restore();
  } catch (_) {
    /* 드로우 실패는 무시 — 다음 프레임에 다시 시도한다 */
  }
}

/* ------------------------------------------------------------------ */
/* 기능 드롭다운 -> 다중 선택 토글 팝업 (2026-10-16)                    */
/* ------------------------------------------------------------------ */
/* 왜(Why) 이 구조인가 (사용자 요구): 드롭다운을 클릭하면 각 항목 옆에
 * 토글이 있고, 항목 글자를 눌러도 선택되지 않는다 — 토글만 선택을 바꾼다.
 * 여러 개를 켠 뒤 캔버스를 클릭하면 닫히고, 위젯 표시가 '자동 (auto)' 에서
 * '수동 (n개)' 로 바뀐다. 값은 콤마 구분 문자열로 저장하며 백엔드
 * (cam_tables.split_multi)가 각 값의 조항을 모두 생성한다.
 * 팝업은 캔버스가 아니라 HTML 오버레이로 만든다 — 줌·팬 변환과 무관하게
 * 클릭 처리가 단순하고, 체크박스라 다중 선택이 자연스럽다. */

const MULTI_WIDGET_NAMES = [
  "shot", "lens", "angle", "composition", "lighting",
  "grade", "motion", "speed", "amplitude", "motion2",
];
const MULTI_AUTO_LABEL = "자동 (auto)";

/** 위젯 표시 이름 재정의 (2026-10-21 사용자 지시).
 *
 * 무빙(motion/motion2)은 영상 파이프라인에서만 반영되므로 화면 이름에
 * "only video" 를 붙여 사용자 혼란을 막는다. **내부 키(w.name)는 그대로**
 * 둔다 — 저장된 워크플로의 widgets_values_named 매핑과 백엔드 키, LLM JSON
 * 규격, 프리셋, 판정(cam_guards)이 전부 name 에 묶여 있어 이름을 바꾸면
 * 기존 워크플로 값이 사라진다. 표시만 바꾸는 것이 안전하다.
 */
const WIDGET_DISPLAY_LABELS = {
  motion: "motion (only video)",
  motion2: "motion2 (only video)",
};

/** 위젯의 표시 이름 (label 이 있으면 우선, 없으면 name). 순수 함수. */
function widgetDisplayName(w) {
  if (!w) return "";
  return w.label || w.name || "";
}

function splitMultiValue(v) {
  return String(v ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s && s !== MULTI_AUTO_LABEL);
}

function joinMultiValue(values, selected) {
  const ordered = values.filter((v) => v !== MULTI_AUTO_LABEL && selected.has(v));
  return ordered.length ? ordered.join(",") : MULTI_AUTO_LABEL;
}

/** 위젯 칸에 보일 텍스트. 선택이 있으면 '수동 (n개)', 없으면 '자동 (auto)'. */
function multiDisplayText(v) {
  const sel = splitMultiValue(v);
  return sel.length ? `수동 (${sel.length}개)` : MULTI_AUTO_LABEL;
}

/** 무빙(motion/motion2) 위젯의 표시 텍스트.
 *
 * 2026-10-21: 위젯 **이름**에 이미 "only video" 가 붙으므로(label 재정의),
 * 정지 이미지 판정 시 값에 붙이던 "· 영상 전용" 꼬리표는 제거했다(중복).
 * 값은 다중 선택 표시(수동 n개 / 자동)만 담는다.
 */
function motionPipelineDisplay(node, name, v) {
  return multiDisplayText(v);
}

let multiPopupEl = null;
let multiPopupState = null;
let multiPopupOpenedAt = 0;
/** 팝업을 연 순간의 캔버스 줌 배율 — 내용 배율의 기준 (연 순간 = 1배). */
let multiPopupOpenScale = 1;
/** 마지막으로 적용한 내용 배율 (같으면 다시 적용하지 않는다). */
let multiPopupAppliedScale = 1;
/** 안 깎인 자연 크기 (세로 캡 판정의 입력 — 내용 배율이 바뀔 때 다시 잰다). */
let multiPopupNaturalW = 0;
let multiPopupNaturalH = 0;
/** 마지막으로 적용한 화면 좌표 (같으면 DOM 에 다시 쓰지 않는다). */
let multiPopupLastLeft = NaN;
let multiPopupLastTop = NaN;
/** 캔버스 변환 추적 루프 핸들 (열려 있는 동안만 돈다; closeMultiPopup 이 취소). */
let multiPopupRaf = 0;

/** 팝업 내부 요소 크기를 배율 s 에 맞춰 다시 적용한다.
 * s = 캔버스 줌 배율(연 순간 대비) — 노드와 같이 캔버스와 함께 커지고
 * 작아진다 (사용자 지시 2026-10-17). */
function applyMultiPopupScale(el, s) {
  if (!el) return;
  const scale = typeof s === "number" && s > 0 ? s : 1;
  el.style.fontSize = (12 * scale).toFixed(1) + "px";
  const cbPx = Math.max(10, Math.round(13 * scale));
  const rowPad = Math.round(2 * scale) + "px " + Math.round(6 * scale) + "px";
  const headPad = Math.round(3 * scale) + "px " + Math.round(6 * scale) + "px";
  for (const cb of el.querySelectorAll("input[type=checkbox]")) {
    cb.style.width = cbPx + "px";
    cb.style.height = cbPx + "px";
  }
  for (const r of el.querySelectorAll(".gori-multi-row")) r.style.padding = rowPad;
  for (const h of el.querySelectorAll(".gori-multi-head")) h.style.padding = headPad;
}

/** 팝업 내용 배율 = 캔버스 줌 비율 (연 순간 대비). 순수 함수 — 테스트 가능.
 * 왜(Why) 상대 배율인가: 팝업은 연 순간 읽을 수 있어야 하고(1배 = 기준 크기),
 * 그 뒤 캔버스 줌에 노드처럼 같이 반응해야 한다 (사용자 지시 2026-10-17 —
 * "노드에 마우스 올리고 휠 쓰면 캔버스하고 같이 움직인다"). */
function popupContentScale(openScale, nowScale) {
  const base = typeof openScale === "number" && openScale > 0 ? openScale : 1;
  const now = typeof nowScale === "number" && nowScale > 0 ? nowScale : base;
  return now / base;
}

/** 팝업의 화면 좌표를 계산한다 (순수 함수 — 테스트 가능).
 *
 * 앵커 = 클릭한 위젯의 **오른쪽 상단** (노드 오른쪽 끝, 위젯 상단).
 *
 * 왜(Why) 이 변환식인가: LiteGraph 의 DragAndScale 규약은
 * `screen = (graph + offset) * scale` 이다. `graph * scale + offset` 로
 * 계산하면 그래프를 이동·확대한 상태에서 팝업이 엉뚱한 곳에 뜬다.
 * convertOffsetToCanvas 가 있으면 그 함수를 그대로 쓴다 (규약의 원본).
 */
function computePopupScreenPos(node, widget, ds, rect) {
  const nodeW = isSizeLike(node?.size) ? node.size[0] : 0;
  const wy = typeof widget?.last_y === "number" ? widget.last_y : 0;
  const gx = (node?.pos?.[0] || 0) + nodeW; // 그래프 좌표: 노드 오른쪽 끝
  const gy = (node?.pos?.[1] || 0) + wy;    // 그래프 좌표: 위젯 상단
  let x, y;
  if (ds && typeof ds.convertOffsetToCanvas === "function") {
    const p = ds.convertOffsetToCanvas([gx, gy]);
    x = p[0];
    y = p[1];
  } else {
    const scale = typeof ds?.scale === "number" ? ds.scale : 1;
    x = (gx + (ds?.offset?.[0] || 0)) * scale;
    y = (gy + (ds?.offset?.[1] || 0)) * scale;
  }
  return [(rect?.left || 0) + x, (rect?.top || 0) + y];
}

/** 팝업이 최소한 보여야 하는 높이(px) — 이보다 낮게 깎이면 위로 올려서라도 보여준다. */
const POPUP_MIN_VISIBLE_PX = 120;

/** 팝업 상자를 화면 안에 맞춘다 (순수 함수 — 테스트 가능).
 * 가로: 넘치면 안쪽으로 민다 (기존 동작).
 * 세로: 넘치면 **위로 밀지 않고** 높이만 깎는다(maxH). 왜(Why) 위로 밀면
 * 안 되나 (2026-10-17 사용자 보고 — motion2 팝업이 speed 줄에 뜸): 위로 미는
 * 옛 폭(화면 높이에서 팝업 높이를 뺀 값)은 클릭한 위젯 위치와 무관한 상수라,
 * 긴 팝업일수록 클릭한 줄에서 멀리 떨어진 엉뚱한 줄에 붙어 보인다. 위쪽은
 * 클릭한 줄에 고정하고 높이만 깎으면 나머지 항목은 내부 스크롤(스크롤바·휠)
 * 로 본다. 줄이 화면 바닥에 너무 가까워 최소 높이조차 안 들어가면 그때만
 * 위로 올린다. */
function fitPopupBox(sx, sy, w, h, vw, vh) {
  let left = Math.max(0, sx);
  let top = Math.max(0, sy);
  let maxH = h;
  if (vw && left + w > vw) left = Math.max(0, vw - w - 4);
  if (vh && top + h > vh) {
    maxH = Math.max(POPUP_MIN_VISIBLE_PX, vh - top - 8);
    if (top + maxH > vh) top = Math.max(0, vh - maxH - 4);
  }
  return { left, top, maxH };
}

function closeMultiPopup() {
  if (multiPopupRaf) {
    try {
      cancelAnimationFrame(multiPopupRaf);
    } catch (_) {
      /* rAF 가 없는 환경에서는 무시 */
    }
    multiPopupRaf = 0;
  }
  if (multiPopupEl && multiPopupEl.parentNode) {
    multiPopupEl.parentNode.removeChild(multiPopupEl);
  }
  multiPopupEl = null;
  multiPopupState = null;
}

/** 팝업이 열려 있는 동안 매 프레임 캔버스 변환(이동·줌)에 팝업을 다시 붙인다.
 * 위치: 앵커(노드 오른쪽 끝 + 클릭한 줄)를 매번 다시 계산 — 캔버스를 이동·
 * 확대하면 노드와 같이 움직인다. 내용 크기는 캔버스 줌 배율(연 순간 대비)을
 * 따라간다 (사용자 지시 2026-10-17). 값이 바뀐 것만 DOM 에 쓴다.
 * 취소는 closeMultiPopup. */
function multiPopupTick() {
  multiPopupRaf = 0;
  const menu = multiPopupEl;
  const st = multiPopupState;
  if (!menu || !st) return;
  try {
    const canvas = app?.canvas;
    const ds = canvas?.ds;
    const rect = canvas?.canvas?.getBoundingClientRect?.();
    if (ds && rect) {
      const s = popupContentScale(multiPopupOpenScale, ds.scale);
      if (Math.abs(s - multiPopupAppliedScale) > 0.001) {
        multiPopupAppliedScale = s;
        applyMultiPopupScale(menu, s);
        const keep = menu.style.maxHeight;
        menu.style.maxHeight = "none";
        multiPopupNaturalW = menu.offsetWidth || 0;
        multiPopupNaturalH = menu.offsetHeight || 0;
        menu.style.maxHeight = keep;
      }
      const [sx, sy] = computePopupScreenPos(st.node, st.widget, ds, rect);
      const vw = globalThis.innerWidth || 0;
      const vh = globalThis.innerHeight || 0;
      const box = fitPopupBox(sx, sy, multiPopupNaturalW, multiPopupNaturalH, vw, vh);
      const left = Math.round(box.left);
      const top = Math.round(box.top);
      if (left !== multiPopupLastLeft) {
        menu.style.left = left + "px";
        multiPopupLastLeft = left;
      }
      if (top !== multiPopupLastTop) {
        menu.style.top = top + "px";
        multiPopupLastTop = top;
      }
      const mh = box.maxH < multiPopupNaturalH ? box.maxH + "px" : "";
      if (menu.style.maxHeight !== mh) menu.style.maxHeight = mh;
    }
  } catch (_) {
    /* 프레임 실패는 무시 — 다음 프레임이 다시 시도한다 */
  }
  multiPopupRaf = requestAnimationFrame(multiPopupTick);
}

/** 팝업 밖 클릭이면 닫는다. 여는 클릭 자체를 닫기로 오인하지 않도록
 * 열린 직후 200ms 는 무시한다 (같은 클릭이 캡처 단계에 먼저 도달한다). */
function ensureMultiPopupCloseHook() {
  if (typeof document === "undefined" || document._goriMultiClose) return;
  document._goriMultiClose = true;
  document.addEventListener("pointerdown", (e) => {
    if (!multiPopupEl) return;
    if (Date.now() - multiPopupOpenedAt < 200) return;
    if (multiPopupEl.contains(e.target)) return;
    closeMultiPopup();
  }, true);
}

function commitMultiValue(node, widget, values, selected) {
  widget.value = joinMultiValue(values, selected);
  try {
    widget.callback?.(widget.value, app.canvas, node, [0, 0], null);
  } catch (_) {
    /* 콜백 실패는 값 반영만 못 한다 — 조용히 무시 */
  }
  app.canvas?.setDirty?.(true, true);
}

function openMultiPopup(node, widget) {
  closeMultiPopup();
  ensureMultiPopupCloseHook();
  const values = Array.isArray(widget.options?.values)
    ? widget.options.values : [];
  if (!values.length) return;
  const selected = new Set(splitMultiValue(widget.value));
  const menu = document.createElement("div");
  menu.className = "gori-multi-popup";
  menu.style.cssText = [
    "position:fixed", "z-index:100000", "background:#232323",
    "border:1px solid #666", "border-radius:4px", "padding:4px",
    "color:#e0e0e0", "font-size:12px", "line-height:1.5",
    "min-width:150px", "max-height:70vh", "overflow:auto",
    "box-shadow:0 4px 12px rgba(0,0,0,.5)", "user-select:none",
  ].join(";");

  // 헤더 = 위젯 이름(좌) + 새로고침 버튼(우). 어떤 기능을 설정하는지 알아야
  // 한다 (사용자 요구). '자동 (auto)' 는 노드 본체 위젯이 값으로 표시하므로
  // 팝업에서는 두지 않는다.
  const head = document.createElement("div");
  head.className = "gori-multi-head";
  head.style.cssText = [
    "display:flex", "align-items:center", "justify-content:space-between",
    "padding:3px 6px", "margin-bottom:2px", "font-weight:bold",
    "color:#cfe8ff", "border-bottom:1px solid #444", "cursor:default",
  ].join(";");
  const headName = document.createElement("span");
  headName.textContent = String(widget.name || "");
  head.appendChild(headName);
  // 새로고침 버튼 (우측 상단, 사용자 지정 2026-10-23): 프리셋바의 ↻ 와 같은
  // 모양·호버 동작 — 평소에는 ↻ 아이콘만, 마우스를 올리면 사각 박스
  // (#3a3a3a 채움 + #7ea6ff 테두리). 누르면 **이 팝업의 위젯 하나만**
  // 현재 프리셋 기본값으로 되돌린다 — 사용자가 체크로 바꾼 부분만 리셋되고
  // 프리셋이 제공하는 값은 유지된다(runPresetWidgetReset 참조).
  const headReset = document.createElement("span");
  headReset.textContent = "↻";
  headReset.title = "이 항목을 프리셋 기본값으로 되돌리기";
  headReset.style.cssText = [
    "margin-left:auto", "cursor:pointer", "color:#8ab4ff",
    "font-weight:normal", "padding:0 6px", "line-height:1.4",
    "border:1px solid transparent", "border-radius:4px",
  ].join(";");
  headReset.addEventListener("mouseenter", () => {
    headReset.style.background = "#3a3a3a";
    headReset.style.borderColor = "#7ea6ff";
  });
  headReset.addEventListener("mouseleave", () => {
    headReset.style.background = "transparent";
    headReset.style.borderColor = "transparent";
  });
  headReset.addEventListener("click", (e) => {
    e.stopPropagation();
    if (!runPresetWidgetReset(node, widget.name)) return;
    // 팝업 체크 상태를 리셋된 값에 맞춘다 — 행을 다시 만들지 않고 같은
    // 체크박스를 그대로 두므로 스크롤 위치도 유지된다.
    const fresh = splitMultiValue(widget.value);
    selected.clear();
    fresh.forEach((v2) => selected.add(v2));
    for (const r of checkRows) r.cb.checked = selected.has(r.value);
  });
  head.appendChild(headReset);
  menu.appendChild(head);

  // 항목: '자동 (auto)' 은 제외한다 (헤더가 그 자리를 대신한다).
  // checkRows 는 리셋 버튼이 체크 상태를 되돌릴 때 쓴다.
  const checkRows = [];
  values.filter((v) => v !== MULTI_AUTO_LABEL).forEach((v) => {
    const row = document.createElement("div");
    row.className = "gori-multi-row";
    row.style.cssText =
      "display:flex;align-items:center;gap:6px;padding:2px 6px;";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = selected.has(v);
    cb.style.cssText = "margin:0;cursor:pointer;";
    const lb = document.createElement("span");
    lb.textContent = v;
    lb.style.cssText = "cursor:default;";
    cb.addEventListener("change", () => {
      if (cb.checked) selected.add(v);
      else selected.delete(v);
      commitMultiValue(node, widget, values, selected);
    });
    row.appendChild(cb);
    row.appendChild(lb);
    menu.appendChild(row);
    checkRows.push({ value: v, cb });
  });

  document.body.appendChild(menu);
  multiPopupEl = menu;
  multiPopupState = { node, widget };
  multiPopupOpenedAt = Date.now();
  multiPopupOpenScale = 1; // 연 순간 = 내용 배율 1 (아래 위치 계산에서 갱신)
  multiPopupAppliedScale = 1;
  applyMultiPopupScale(menu, 1);

  // 휠은 캔버스로 넘긴다 (사용자 지시 2026-10-17): 팝업만 따로 커지던 옛
  // 동작을 제거. 노드 위 휠과 완전히 같다 — 프런트의 processMouseWheel 이
  // 설정(기본: 캔버스 이동, Ctrl·트랙패드: 줌)을 그대로 처리한다.
  // 단 팝업이 세로로 깎여 스크롤이 필요하면 세로 휠은 목록 스크롤로 쓰고
  // (프런트의 textarea 휠 처리와 같은 패턴), Ctrl·가로 휠·제스처는 캔버스.
  menu.addEventListener("wheel", (e) => {
    e.stopPropagation();
    const canvas = app?.canvas;
    const scrollable = menu.scrollHeight > menu.clientHeight + 1;
    const gesture = !!canvas?.pointer?.isTrackpadGesture?.(e);
    const horizontal = Math.abs(e.deltaX) > Math.abs(e.deltaY);
    if (e.ctrlKey || gesture || horizontal || !scrollable) {
      canvas?.processMouseWheel?.(e);
    }
  }, { passive: false });

  // 위치: 클릭한 위젯의 **오른쪽**에 붙인다 (사용자 예시 이미지 3장).
  // 노드 오른쪽 끝에서 시작하고, 세로는 위젯 상단에 맞춘다.
  try {
    const canvas = app.canvas;
    const dom = canvas?.canvas;
    const rect = dom?.getBoundingClientRect?.();
    const ds = canvas?.ds;
    if (rect && ds) {
      multiPopupOpenScale = typeof ds.scale === "number" && ds.scale > 0 ? ds.scale : 1;
      const [sx, sy] = computePopupScreenPos(node, widget, ds, rect);
      const vw = globalThis.innerWidth || 0;
      const vh = globalThis.innerHeight || 0;
      const w = menu.offsetWidth || 0;
      const h = menu.offsetHeight || 0;
      multiPopupNaturalW = w;
      multiPopupNaturalH = h;
      const box = fitPopupBox(sx, sy, w, h, vw, vh);
      // 세로가 깎였으면 상자 높이를 제한한다 — 나머지 항목은 내부 스크롤로
      // 본다. 위로 미는 옛 폭(화면 높이에서 팝업 높이를 뺀 값)은 클릭한 줄과
      // 무관한 상수라 긴 팝업이 엉뚱한 줄에 떠 보였다 (motion2 사고 —
      // fitPopupBox 참조).
      if (box.maxH < h) menu.style.maxHeight = box.maxH + "px";
      menu.style.left = Math.round(box.left) + "px";
      menu.style.top = Math.round(box.top) + "px";
      multiPopupLastLeft = Math.round(box.left);
      multiPopupLastTop = Math.round(box.top);
    }
  } catch (_) {
    /* 위치 계산 실패해도 팝업은 뜬다 (좌상단) */
  }

  // 캔버스 변환(이동·줌) 추적 시작 — 노드와 같이 움직인다 (2026-10-17).
  multiPopupRaf = requestAnimationFrame(multiPopupTick);
}

/** 기능 위젯 하나를 다중 선택 위젯으로 교체한다. */
function installMultiSelectWidget(node, name) {
  const widgets = node?.widgets;
  if (!Array.isArray(widgets)) return false;
  const idx = widgets.findIndex((w) => w && w.name === name);
  if (idx < 0) return false;
  const old = widgets[idx];
  if (old._goriMulti) return false; // 이미 설치됨
  const values = Array.isArray(old.options?.values)
    ? old.options.values.slice() : [];
  // '자동 (auto)' 는 항상 맨 앞에 있어야 한다 — 배경 라벨이자 해제 상태다.
  // 왜(Why) 방어하나: 콤보 values 를 못 읽는 환경에서 특정 기능에 '자동' 이
  // 빠져 보인다는 지적이 있었다. 없으면 여기서 채운다.
  if (!values.includes(MULTI_AUTO_LABEL)) values.unshift(MULTI_AUTO_LABEL);
  // 원본 draw 를 보존한다 — ComfyUI 기본 그리기가 **이름**까지 그려 준다.
  // 직접 그리면 이름이 사라져 어떤 기능인지 알 수 없다 (사용자 지적).
  const origDraw = typeof old.draw === "function" ? old.draw : null;
  const mw = {
    _goriMulti: true,
    type: "gori_multi",
    name,
    // 표시 이름만 재정의 (내부 키 name 은 유지). WIDGET_DISPLAY_LABELS 참조.
    label: WIDGET_DISPLAY_LABELS[name] || old.label || name,
    value: old.value,
    options: Object.assign({}, old.options, { values }),
    y: old.y,
    last_y: typeof old.last_y === "number" ? old.last_y : old.y,
    computeSize(width) { return [width, 20]; },
    draw(ctx, n, width, y, H) {
      this.last_y = y;
      this.y = y;
      const realValue = this.value;
      const display = motionPipelineDisplay(n, this.name, realValue);
      // ComfyUI 기본 draw 를 재사용해 **이름**까지 그대로 나오게 한다.
      // 표시용 텍스트를 잠시 value 로 넣어 그린 뒤 즉시 되돌린다.
      if (origDraw) {
        this.value = display;
        try {
          origDraw.call(this, ctx, n, width, y, H);
        } finally {
          this.value = realValue;
        }
        return;
      }
      // 기본 draw 가 없는 환경 대비 — 이름 + 값 + 화살표를 직접 그린다.
      // 표시 이름은 label 우선(this.label), 없으면 name.
      ctx.save();
      ctx.textBaseline = "middle";
      ctx.fillStyle = "#999";
      ctx.textAlign = "left";
      ctx.fillText(String(widgetDisplayName(this)), 15, y + H / 2);
      ctx.fillStyle = "#ddd";
      ctx.textAlign = "right";
      ctx.fillText(display, width - 20, y + H / 2);
      ctx.fillStyle = "#999";
      ctx.fillText("▼", width - 8, y + H / 2);
      ctx.restore();
    },
    mouse(event, pos, n) {
      const t = event?.type;
      if (t === "pointerdown" || t === "mousedown") {
        if (multiPopupState && multiPopupState.widget === this) {
          closeMultiPopup();
        } else {
          openMultiPopup(n, this);
        }
        return true;
      }
      return false;
    },
  };
  widgets[idx] = mw;
  return true;
}

/** 노드의 기능 위젯 전부를 다중 선택으로 교체. */
function installMultiSelectWidgets(node) {
  let n = 0;
  for (const name of MULTI_WIDGET_NAMES) {
    try {
      if (installMultiSelectWidget(node, name)) n += 1;
    } catch (_) {
      /* 한 위젯 실패가 나머지를 막지 않게 한다 */
    }
  }
  return n;
}

/* ------------------------------------------------------------------ */
/* 프리셋 기억 + 프리셋바 우측 끝 리셋 버튼 (2026-10-22 R200)           */
/* ------------------------------------------------------------------ */
/* 왜(Why) 이 구조인가 (사용자 제보): 자동 프리셋에서 기능을 체크하고
 * 시네마틱 인물로 갔다가 자동으로 돌아오면 체크가 사라졌다. 새로고침·
 * ComfyUI 재시작 뒤에도 사라졌다. 기존 코드는 (1) 프리셋 전환마다 미러
 * 값을 덮어써 사용자 편집을 지우고, (2) 자동으로 돌아오면 전 필드를 강제
 * '자동 (auto)' 로 바꿨고, (3) 로드 뒤 첫 틱에도 같은 강제 초기화를
 * 돌렸다. 지금은 프리셋별 기억을 두고 전환 시에만 값을 옮긴다.
 *
 * 전부 지우는 일(초기화)은 프리셋바 우측 끝의 리셋 버튼만 한다 —
 * 브라우저 새로고침 아이콘 모양. 버튼은 **현재 선택된 프리셋**의
 * 기본값으로 되돌린다: 자동이면 전 필드 자동, 이름 프리셋이면 미러 값.
 * 프리셋이 제공하는 값은 리셋의 대상이 아니라 복원의 기준이다. */

/** 리셋 버튼이 차지하는 폭 (px). 프리셋바 오른쪽 끝에서 한 칸 안쪽에 붙는다. */
const PRESET_RESET_STRIP_W = 26;

/** 리셋 버튼과 프리셋바 오른쪽 끝 사이의 간격 — 위젯 한 칸. 사용자 지정
 * (2026-10-22): 버튼을 오른쪽 끝에서 한 칸 안쪽으로 옮긴다. 한 칸의 폭은
 * 위젯 한 줄 높이(H)이며 그릴 때 정해진다 — H 를 모를 때의 폴백 값은
 * litegraph 기본 행 높이 20. */
const PRESET_RESET_SLOT_FALLBACK_H = 20;

/** 노드의 프리셋별 기억 저장소. 키 = 프리셋 위젯 값, 값 = {필드: 값}. */
function presetMemoryOf(node) {
  if (!node || typeof node !== "object") return {};
  if (!node._goriPresetMemory || typeof node._goriPresetMemory !== "object") {
    node._goriPresetMemory = {};
  }
  return node._goriPresetMemory;
}

/** 현재 기능 필드 값의 스냅샷. 순수하게 읽기만 한다. */
function snapshotPresetFields(node) {
  const snap = {};
  for (const name of MULTI_WIDGET_NAMES) {
    const w = (node?.widgets || []).find((x) => x && x.name === name);
    if (w) snap[name] = w.value;
  }
  return snap;
}

/** 기능 필드에 값을 적용한다. null 은 건드리지 않는다. */
function applyPresetFields(node, values) {
  let changed = false;
  for (const name of MULTI_WIDGET_NAMES) {
    const w = (node?.widgets || []).find((x) => x && x.name === name);
    if (w && values && values[name] != null && w.value !== values[name]) {
      w.value = values[name];
      changed = true;
    }
  }
  if (changed) {
    try {
      app.canvas?.setDirty?.(true, true);
    } catch (_) {
      /* 캔버스 갱신 실패는 값 반영에 영향이 없다 */
    }
  }
  return changed;
}

/** 프리셋의 기본값. 자동이면 전 필드 자동, 이름 프리셋이면 미러 값
 * (미러에 없는 필드는 자동). mirror 를 받는 순수 함수 — 테스트 가능. */
function presetDefaultFields(presetName, mirror) {
  const out = {};
  for (const name of MULTI_WIDGET_NAMES) out[name] = MULTI_AUTO_LABEL;
  if (presetName === MULTI_AUTO_LABEL || presetName === "auto") return out;
  const table = mirror !== undefined
    ? mirror
    : (typeof CAMERA_PRESETS === "undefined" ? null : CAMERA_PRESETS);
  const p = table ? table[presetName] : null;
  if (p) {
    for (const k of Object.keys(p)) {
      if (k in out && p[k] != null) out[k] = p[k];
    }
  }
  return out;
}

/** 첫 관측: 현재 프리셋의 값을 기억만 하고 위젯을 건드리지 않는다.
 * 왜(Why) 덮어쓰지 않나: 새로고침·재시작 뒤 워크플로가 복원한 체크 값도
 * 사용자 선택이다. 여기서 프리셋 기본값을 적용하면 R200 제보(새로고침
 * 초기화)가 그대로 돌아온다. 이름 프리셋인데 필드가 전부 자동이면 아직
 * 적용된 적 없는 상태라 기억을 남기지 않는다 — 전환·리셋 때 프리셋
 * 기본값이 적용되도록. */
function rememberCurrentPresetFields(node) {
  try {
    const pw = (node?.widgets || []).find((w) => w && w.name === "preset");
    const cur = pw ? pw.value : "";
    if (!cur || node._goriLastPreset !== undefined) return false;
    const snap = snapshotPresetFields(node);
    const allAuto = MULTI_WIDGET_NAMES.every(
      (n) => !snap[n] || snap[n] === MULTI_AUTO_LABEL
    );
    if (!allAuto || cur === MULTI_AUTO_LABEL || cur === "auto") {
      presetMemoryOf(node)[cur] = snap;
    }
    node._goriLastPreset = cur;
    return true;
  } catch (_) {
    return false;
  }
}

/** 리셋: 현재 프리셋의 기본값을 적용하고 기억도 기본값으로 되돌린다.
 * 프리셋이 제공하는 값은 그대로 살아 있고 사용자가 바꾼 것만 원래대로
 * 간다 (사용자 지정 2026-10-22). */
function runPresetReset(node, mirror) {
  try {
    const pw = (node?.widgets || []).find((w) => w && w.name === "preset");
    const presetName = pw ? pw.value : "";
    const defaults = presetDefaultFields(presetName, mirror);
    applyPresetFields(node, defaults);
    presetMemoryOf(node)[presetName] = snapshotPresetFields(node);
    // 같은 프리셋 재적용으로 오인해 다시 덮어쓰지 않게 현재 값을 맞춘다.
    node._goriLastPreset = presetName;
    return true;
  } catch (_) {
    return false;
  }
}

/** 팝업의 새로고침 버튼 — 기능 위젯 **하나만** 현재 프리셋 기본값으로
 * 되돌린다 (사용자 지정 2026-10-23: "새로 고침을 눌렀을 때 리셋이 되는 건
 * 그 팝업 창만, 사용자가 체크로 선택한 부분만"). 기준값은 프리셋바 전체
 * 리셋(runPresetReset)과 같다 — 프리셋이 제공하는 값은 유지되고 사용자가
 * 체크로 바꾼 부분만 원래대로 간다. 프리셋이 이 칸을 제공하지 않으면
 * '자동 (auto)'. 현재 프리셋의 기억도 같이 갱신한다 — 리셋 뒤 프리셋을
 * 나갔다 돌아와도 리셋된 상태가 유지된다(R200 기억 규약과 같다).
 * 콜백·setDirty 는 commitMultiValue 와 같은 순서로 뒤에서 한 번씩 부른다. */
function runPresetWidgetReset(node, widgetName) {
  try {
    if (!MULTI_WIDGET_NAMES.includes(widgetName)) return false;
    const widgets = node?.widgets || [];
    const w = widgets.find((x) => x && x.name === widgetName);
    if (!w) return false;
    const pw = widgets.find((x) => x && x.name === "preset");
    const presetName = pw ? pw.value : "";
    const target = presetDefaultFields(presetName)[widgetName];
    if (target == null) return false;
    w.value = target;
    const mem = presetMemoryOf(node);
    const snap = mem[presetName] || snapshotPresetFields(node);
    snap[widgetName] = target;
    mem[presetName] = snap;
    try {
      w.callback?.(w.value, app.canvas, node, [0, 0], null);
    } catch (_) {
      /* 콜백 실패는 값 반영에 영향이 없다 */
    }
    try {
      app.canvas?.setDirty?.(true, true);
    } catch (_) {
      /* 캔버스 갱신 실패는 값 반영에 영향이 없다 */
    }
    return true;
  } catch (_) {
    return false;
  }
}

/** 리셋 클릭 판정 — 오른쪽 끝에서 한 칸 안쪽 스트립. 순수 함수 — 테스트
 * 가능. 좌표 규약: 새 litegraph 는 위젯 mouse/onClick 에 노드 로컬 x 를 준다
 * (코어 bundle 실측: `e.canvasX - node.pos[0]`). 히트 구간은
 * [폭 - 스트립 - 한칸, 폭 - 한칸) — 그린 버튼 사각형과 정확히 일치한다.
 * 오른쪽 한 칸 갭은 버튼이 아니며(빈 여백), 그 곳 클릭은 콤보를 따른다. */
function presetResetHitX(x, width, slotH) {
  const slot = Number.isFinite(slotH) ? slotH : PRESET_RESET_SLOT_FALLBACK_H;
  return Number.isFinite(x) && Number.isFinite(width)
    && width > PRESET_RESET_STRIP_W + slot
    && x >= width - PRESET_RESET_STRIP_W - slot
    && x < width - slot;
}

/** 리셋 아이콘 — 브라우저 새로고침(원형 화살) 모양. 노드 로컬 좌표.
 * withBox 가 참이면 사각 버튼 배경을 함께 그린다(호버 상태). 기본은 화살만
 * — 평소에는 ↻ 아이콘만 보이고 호버에서 사각 박스가 나타난다(사용자 지정
 * 2026-10-22 23:27). 박스 세로 높이는 preset 바 행 높이 h 와 같다. */
function drawPresetResetIcon(ctx, stripX, y, h, withBox) {
  try {
    const cx = stripX + PRESET_RESET_STRIP_W / 2;
    const cy = y + h / 2;
    const r = Math.min(PRESET_RESET_STRIP_W, h) * 0.30;
    ctx.save();
    if (withBox) {
      ctx.beginPath();
      if (typeof ctx.roundRect === "function") {
        ctx.roundRect(stripX + 1, y, PRESET_RESET_STRIP_W - 2, h, 4);
      } else {
        ctx.rect(stripX + 1, y, PRESET_RESET_STRIP_W - 2, h);
      }
      ctx.fillStyle = "#3a3a3a";
      ctx.fill();
      ctx.strokeStyle = "#7ea6ff";
      ctx.lineWidth = 1;
      ctx.stroke();
    }
    ctx.strokeStyle = "#8ab4ff";
    ctx.lineWidth = 1.6;
    ctx.beginPath();
    ctx.arc(cx, cy, r, -Math.PI * 0.5 + 0.45, Math.PI * 1.5 - 0.45);
    ctx.stroke();
    const tx = cx + r * Math.cos(-Math.PI * 0.5 + 0.45);
    const ty = cy + r * Math.sin(-Math.PI * 0.5 + 0.45);
    ctx.beginPath();
    ctx.moveTo(tx - 1.5, ty - 3.5);
    ctx.lineTo(tx + 2.5, ty + 0.5);
    ctx.lineTo(tx - 3.5, ty + 1.5);
    ctx.closePath();
    ctx.fillStyle = "#8ab4ff";
    ctx.fill();
    ctx.restore();
  } catch (_) {
    /* 아이콘 실패는 무시 — 리셋 동작은 클릭 판정으로 돈다 */
  }
}

/** 워크플로 저장 — 새 프론트엔드의 저장 경로. 실측(2026-10-23, 실행 중
 * 페이지 프로브): app.saveGraph / app.storeWorkflow / app.workflowManager 는
 * 전부 없고, 저장은 extensionManager(pinia 스토어)에 있다 —
 * `app.extensionManager.workflow.saveWorkflow()` 가 표준 경로이고
 * `activeWorkflow.save()` 가 같은 프로토 타입에 있다(두 메서드 실측 확인).
 * 어느 쪽도 없으면(구버전 프론트·비정상 로드) 저장하지 않고 거짓을 돌려준다
 * — 사용자에게는 조용하되 반환값으로 판정 가능하다(테스트 가능). */
function runWorkflowSave() {
  try {
    const wf = app?.extensionManager?.workflow;
    if (wf && typeof wf.saveWorkflow === "function") {
      wf.saveWorkflow();
      return true;
    }
    const active = wf?.activeWorkflow;
    if (active && typeof active.save === "function") {
      active.save();
      return true;
    }
  } catch (_) {
    /* 저장 실패는 조용히 — Ctrl+S 로 언제든 저장할 수 있다 */
  }
  return false;
}

/** 저장 아이콘 — 플로피 디스크 모양. 노드 로컬 좌표. ↻ 아이콘(위 행)과
 * 크기·색·호버 동작이 같다(사용자 지정 2026-10-23): 평소에는 아이콘만
 * 보이고 호버에서 사각 박스가 나타난다. 박스 세로 높이는 행 높이 h 와
 * 같다. 몸통(rect)+셔터(상단 작은 rect)+라벨(하단 rect) — rect 만 써
 * 그리기 계약을 테스트가 그대로 잡을 수 있게 한다. */
function drawPresetSaveIcon(ctx, stripX, y, h, withBox) {
  try {
    const cx = stripX + PRESET_RESET_STRIP_W / 2;
    const cy = y + h / 2;
    const s = Math.min(PRESET_RESET_STRIP_W, h) * 0.32;
    ctx.save();
    if (withBox) {
      ctx.beginPath();
      if (typeof ctx.roundRect === "function") {
        ctx.roundRect(stripX + 1, y, PRESET_RESET_STRIP_W - 2, h, 4);
      } else {
        ctx.rect(stripX + 1, y, PRESET_RESET_STRIP_W - 2, h);
      }
      ctx.fillStyle = "#3a3a3a";
      ctx.fill();
      ctx.strokeStyle = "#7ea6ff";
      ctx.lineWidth = 1;
      ctx.stroke();
    }
    ctx.strokeStyle = "#8ab4ff";
    ctx.lineWidth = 1.4;
    const bw = s * 1.9;
    const bh = s * 1.9;
    const bx = cx - bw / 2;
    const by = cy - bh / 2;
    ctx.beginPath();
    ctx.rect(bx, by, bw, bh);
    ctx.stroke();
    ctx.beginPath();
    ctx.rect(cx - s * 0.55, by, s * 1.1, s * 0.6);
    ctx.stroke();
    ctx.beginPath();
    ctx.rect(cx - s * 0.55, by + bh - s * 0.9, s * 1.1, s * 0.9);
    ctx.stroke();
    ctx.restore();
  } catch (_) {
    /* 아이콘 실패는 무시 — 저장 동작은 클릭 판정으로 돈다 */
  }
}

/** 캔버스 위 마우스의 그래프 좌표 — window 캡처 리스너로 추적한다.
 * 왜(Why) 캔버스 엘리먼트가 아니라 window 캡처인가: 실측(2026-10-22 23:58)
 * 에서 캔버스 엘리먼트 리스너로는 호버 판정이 늘 거짓이었다 — 같은 이벤트에서
 * 내 프로브 리스너는 발화했고 순수 판정·좌표 변환·그리기는 전부 정상이었다.
 * 즉 좌표 공급원이 문제였다. ComfyUI 의 오버레이 UI 가 포인터 이벤트 대상을
 * 가로채 캔버스 엘리먼트로는 실제 마우스 흐름이 오지 않는다. window 캡처는
 * 대상과 무관하게 모든 이동을 받는다. 변환식은 코어와 같다:
 * (캔버스 픽셀)/scale - offset. 신선도 가드: 마우스가 멈추면 값이 오래되니
 * TTL 을 넘기면 graph_mouse 로 폴백한다(마지막 위치라 값은 동일하다). */
const PRESET_RESET_HOVER_TTL_MS = 1500;
let _goriPointerGraphPos = null;
let _goriPointerPosTs = 0;

/** 리스너를 붙인다 — 창마다 한 번. 그릴 때마다 불려도 가드로 한 번만 걸린다. */
let _goriTrackerWin = null;
function attachPointerTracker() {
  if (_goriTrackerWin === window) return;
  _goriTrackerWin = window;
  window.addEventListener("pointermove", (e) => {
    try {
      const c = app.canvas;
      const el = c?.canvas;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      if (e.clientX < rect.left || e.clientX > rect.right
        || e.clientY < rect.top || e.clientY > rect.bottom) return;
      const scale = c?.ds?.scale ?? 1;
      const off = c?.ds?.offset || [0, 0];
      _goriPointerGraphPos = [
        (e.clientX - rect.left) / scale - off[0],
        (e.clientY - rect.top) / scale - off[1],
      ];
      _goriPointerPosTs = Date.now();
      // 새 프론트는 요청 기반 렌더링이다 — 가만히 있다가 마우스만 움직이면
      // 다시 그리지 않는다(startRendering/stopRendering, bundle 실측
      // 2026-10-22 23:47). 이동마다 다시 그려야 호버 박스가 뜬다.
      c?.setDirty?.(true, true);
    } catch (_) {
      /* 무시 — 다음 이동에서 다시 시도한다 */
    }
  }, { capture: true, passive: true });
}

/** 호버 판정 — 로컬 마우스가 리셋 버튼 사각형(그린 것과 같은 구간) 위에
 * 있는가. 순수 함수 — 테스트 가능. y 범위는 행 높이 하나. */
function presetResetHoveredAt(localX, localY, width, y, H) {
  try {
    const slot = (typeof H === "number" && H > 0)
      ? H
      : PRESET_RESET_SLOT_FALLBACK_H;
    if (!presetResetHitX(localX, width, slot)) return false;
    return typeof localY === "number"
      && localY >= y && localY <= y + slot;
  } catch (_) {
    return false;
  }
}

/** 호버 판정 — 그릴 때 쓴다. 자체 추적 좌표가 신선하면 우선, 아니면
 * graph_mouse(코어가 마지막 위치를 보관 — 실측 23:58, 이동 이벤트마다
 * 갱신을 확인). 그래프 좌표를 노드 로컬로 바꿔 사각형 판정에 넘긴다.
 * 왜(Why) Array.isArray 로 검사하지 않나: 실측(2026-10-22 23:58 종단)에서
 * 새 프론트의 node.pos 는 배열이 아니라 객체({0:420, 1:220})였다 — 가드가
 * 항상 거짓이어서 판정이 호출조차 안 됐고, 이것이 호버가 안 뜬 전부였다.
 * 그래서 좌표 공급원뿐 아니라 가드도 duck-typing 으로 검사한다. */
function presetResetHovered(node, width, y, H) {
  try {
    attachPointerTracker();
    const fresh = Array.isArray(_goriPointerGraphPos)
      && (Date.now() - _goriPointerPosTs) < PRESET_RESET_HOVER_TTL_MS;
    const m = fresh ? _goriPointerGraphPos : app.canvas?.graph_mouse;
    if (!m || typeof m[0] !== "number" || typeof m[1] !== "number"
      || !node?.pos || typeof node.pos[0] !== "number"
      || typeof node.pos[1] !== "number") {
      return false;
    }
    return presetResetHoveredAt(
      m[0] - node.pos[0], m[1] - node.pos[1], width, y, H
    );
  } catch (_) {
    return false;
  }
}

/** 콤보 몸통을 줄인 폭으로 그린다. 콘크리트 뷰의 drawWidget 이 있으면 그걸
 * 쓰고(뷰가 raw 위젯에 합쳐진 뒤에야 보인다 — adoptConcreteWidget 실측),
 * 없으면 값 텍스트만 그려 최소 모양을 유지한다. */
function drawComboBodyShrunk(w, ctx, width, y, H, lowQuality) {
  let drawn = false;
  try {
    if (typeof w.drawWidget === "function") {
      w.drawWidget(ctx, { width, showText: !lowQuality });
      drawn = true;
    }
  } catch (_) {
    /* 뷰 몸통 실패 시 아래 최소 드로잉으로 간다 */
  }
  if (!drawn) {
    try {
      ctx.save();
      ctx.fillStyle = "#222";
      ctx.beginPath();
      if (typeof ctx.roundRect === "function") {
        ctx.roundRect(15, y, Math.max(0, width - 30), H, 4);
      } else {
        ctx.rect(15, y, Math.max(0, width - 30), H);
      }
      ctx.fill();
      ctx.fillStyle = "#ddd";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(String(w.value ?? ""), width / 2, y + H / 2);
      ctx.restore();
    } catch (_) {
      /* 최소 드로잉 실패도 무시 — 값은 콤보 클릭으로 바꿀 수 있다 */
    }
  }
}

/** 프리셋 위젯에 리셋 버튼을 얹는다 (JS 전용 — 저장되지 않는다).
 * 그리기: 새 litegraph 는 draw 속성이 있으면 drawWidget 보다 우선한다
 * (코어 drawWidgets dispatch 실측). 콤보를 폭 - 스트립 - 한 칸으로 그려
 * 오른쪽에서 한 칸 안쪽 스트립을 버튼에 남긴다 — "프리셋바 우측 끝에서
 * 한 칸 왼쪽" 배치(사용자 지정 2026-10-22). 한 칸은 위젯 한 줄 높이 H.
 * 클릭: 새 litegraph 코어 콤보는 onClick 으로, 구버전은 mouse 로 처리한다
 * (toConcreteWidget 이 있으면 mouse 는 무시된다 — 실측). */
function installPresetResetButton(node) {
  const widgets = node?.widgets;
  if (!Array.isArray(widgets)) return false;
  const pw = widgets.find((w) => w && w.name === "preset");
  if (!pw || pw._goriPresetReset) return false;
  pw._goriPresetReset = true;

  // 그리기: 항상 draw 를 얹는다 — 새 litegraph dispatch 는 draw 속성이
  // 있으면 콘크리트 뷰의 drawWidget 보다 우선한다(코어 drawWidgets 실측).
  // (1) 구버전처럼 원본 draw 가 있으면 줄인 폭으로 되돌리고, (2) 없으면
  // (새 litegraph) 콘크리트 뷰가 맡기던 몸통을 직접 부른다. 몸통 메서드
  // (drawWidget)는 뷰가 raw 위젯에 합쳐진 뒤에야 보인다(adoptConcreteWidget
  // 실측) — 합쳐지기 전엔 값 텍스트만 그려 최소 모양을 유지한다.
  if (typeof pw.draw === "function") {
    const origDraw = pw.draw;
    pw.draw = function (ctx, n, width, y, H) {
      this.y = y;
      this.last_y = y;
      const w = (typeof width === "number" && width > 0) ? width
        : (typeof n?.size?.[0] === "number" ? n.size[0] : 0);
      const slot = (typeof H === "number" && H > 0) ? H
        : PRESET_RESET_SLOT_FALLBACK_H;
      this._goriResetSlotH = slot;
      const inner = Math.max(0, w - PRESET_RESET_STRIP_W - slot);
      try {
        origDraw.call(this, ctx, n, inner, y, H);
      } catch (_) {
        origDraw.call(this, ctx, n, width, y, H);
      }
      // ↻ 아이콘은 항상 그린다 — 사각 배경만 호버에서 (사용자 지정
      // 2026-10-22 23:27: 평소에는 화살만, 호버에서 박스).
      drawPresetResetIcon(ctx, inner, y, H, presetResetHovered(n, w, y, H));
    };
  } else {
    pw.draw = function (ctx, n, width, y, H, lowQuality) {
      this.y = y;
      this.last_y = y;
      const w = (typeof width === "number" && width > 0) ? width
        : (typeof n?.size?.[0] === "number" ? n.size[0] : 0);
      const slot = (typeof H === "number" && H > 0) ? H
        : PRESET_RESET_SLOT_FALLBACK_H;
      this._goriResetSlotH = slot;
      const inner = Math.max(0, w - PRESET_RESET_STRIP_W - slot);
      drawComboBodyShrunk(this, ctx, inner, y, H, lowQuality);
      // ↻ 아이콘은 항상 그린다 — 사각 배경만 호버에서 (사용자 지정
      // 2026-10-22 23:27: 평소에는 화살만, 호버에서 박스).
      drawPresetResetIcon(ctx, inner, y, H, presetResetHovered(n, w, y, H));
    };
  }

  const origOnClick = typeof pw.onClick === "function" ? pw.onClick : null;
  pw.onClick = function (arg) {
    try {
      const e = arg?.e;
      const n = arg?.node || node;
      if (e && n) {
        const x = (typeof e.canvasX === "number") ? e.canvasX - n.pos[0] : NaN;
        const width = (typeof this.width === "number" && this.width > 0)
          ? this.width
          : (typeof n.size?.[0] === "number" ? n.size[0] : 0);
        const slot = Number.isFinite(this._goriResetSlotH)
          ? this._goriResetSlotH
          : PRESET_RESET_SLOT_FALLBACK_H;
        if (width > 0 && presetResetHitX(x, width, slot)) {
          runPresetReset(n);
          try {
            arg?.canvas?.setDirty?.(true, true);
          } catch (_) {
            /* 무시 */
          }
          return; // 리셋 클릭이었다 — 드롭다운을 열지 않는다
        }
      }
    } catch (_) {
      /* 판정 실패는 원래 콤보 클릭을 따른다 */
    }
    return origOnClick ? origOnClick.call(this, arg) : undefined;
  };

  const origMouse = typeof pw.mouse === "function" ? pw.mouse : null;
  if (origMouse) {
    // 구버전 litegraph: mouse 경로만 있는 프런트엔드용. 새 litegraph 는
    // onClick 을 우선해 이 래퍼는 호출되지 않는다.
    pw.mouse = function (event, pos, n) {
      const t = event?.type;
      if ((t === "pointerdown" || t === "mousedown") && Array.isArray(pos)) {
        const width = (typeof this.width === "number" && this.width > 0)
          ? this.width
          : (typeof n?.size?.[0] === "number" ? n.size[0] : 0);
        const slot = Number.isFinite(this._goriResetSlotH)
          ? this._goriResetSlotH
          : PRESET_RESET_SLOT_FALLBACK_H;
        if (width > 0 && presetResetHitX(pos[0], width, slot)) {
          runPresetReset(n || node);
          try {
            app.canvas?.setDirty?.(true, true);
          } catch (_) {
            /* 무시 */
          }
          return true;
        }
      }
      return origMouse.call(this, event, pos, n);
    };
  }
  return true;
}

/** automation 바 폭을 preset 바(콤보) 폭과 맞춘다 — 리셋 버튼이 오른쪽에서
 * 한 칸을 차지하는 만큼 automation 콤보도 같은 폭으로 그려 두 바의 오른쪽
 * 끝이 나란히 맞는다 (사용자 지정 2026-10-22 23:07, 통일성). */
function installAutomationBarMatch(node) {
  const widgets = node?.widgets;
  if (!Array.isArray(widgets)) return false;
  const aw = widgets.find((w) => w && w.name === "automation");
  if (!aw || aw._goriBarMatch) return false;
  aw._goriBarMatch = true;
  if (typeof aw.draw === "function") {
    const origDraw = aw.draw;
    aw.draw = function (ctx, n, width, y, H) {
      this.y = y;
      this.last_y = y;
      const w = (typeof width === "number" && width > 0) ? width
        : (typeof n?.size?.[0] === "number" ? n.size[0] : 0);
      const slot = (typeof H === "number" && H > 0) ? H
        : PRESET_RESET_SLOT_FALLBACK_H;
      try {
        origDraw.call(this, ctx, n, Math.max(0, w - PRESET_RESET_STRIP_W - slot), y, H);
      } catch (_) {
        origDraw.call(this, ctx, n, width, y, H);
      }
    };
  } else {
    aw.draw = function (ctx, n, width, y, H, lowQuality) {
      this.y = y;
      this.last_y = y;
      const w = (typeof width === "number" && width > 0) ? width
        : (typeof n?.size?.[0] === "number" ? n.size[0] : 0);
      const slot = (typeof H === "number" && H > 0) ? H
        : PRESET_RESET_SLOT_FALLBACK_H;
      drawComboBodyShrunk(this, ctx, Math.max(0, w - PRESET_RESET_STRIP_W - slot), y, H, lowQuality);
    };
  }
  return true;
}

/** 저장 버튼 — ↻ 아이콘 바로 아래 칸(automation 행의 오른쪽 스트립)에
 * 저장 아이콘을 얹는다 (JS 전용 — 저장되지 않는다). 크기(폭 26 × 행 높이
 * H)와 호버 동작(아이콘 항상 표시, 호버 시 사각 박스)은 ↻ 와 동일하다
 * (사용자 지정 2026-10-23). automation 콤보는 폭 정합 래퍼가 이미
 * 폭-26-한칸 으로 줄여 그리므로 그 스트립은 비어 있다.
 *
 * 왜(Why) 이 래퍼는 몸통을 다시 줄이지 않나: 설치 순서가 폭 정합
 * (installAutomationBarMatch) **뒤**라 이 래퍼가 바깥이다. 안쪽(폭 정합
 * 래퍼)이 받은 폭을 그대로 넘겨 몸통을 줄이게 두고, 바깥에서 전체 폭으로
 * 스트립 x(폭-26-한칸)를 계산해 아이콘을 그린다. 순서가 뒤집히면 두 래퍼가
 * 각각 줄여 이중 축소가 된다 — afterLifecycle 의 설치 순서를 테스트가
 * 고정한다(F28 소스 계약). 원본 draw 가 아예 없으면(구버전) 몸통을 스스로
 * 줄여 그린다. 클릭: preset 리셋 버튼과 같은 판정(presetResetHitX — y 는
 * 위젯 라우팅이 이미 골라 주므로 x 만 본다)으로 스트립 히트 시
 * runWorkflowSave 를 부르고 드롭다운을 열지 않는다. */
function installPresetSaveButton(node) {
  const widgets = node?.widgets;
  if (!Array.isArray(widgets)) return false;
  const aw = widgets.find((w) => w && w.name === "automation");
  if (!aw || aw._goriPresetSave) return false;
  aw._goriPresetSave = true;

  const origDraw = typeof aw.draw === "function" ? aw.draw : null;
  aw.draw = function (ctx, n, width, y, H, lowQuality) {
    this.y = y;
    this.last_y = y;
    const w = (typeof width === "number" && width > 0) ? width
      : (typeof n?.size?.[0] === "number" ? n.size[0] : 0);
    const slot = (typeof H === "number" && H > 0) ? H
      : PRESET_RESET_SLOT_FALLBACK_H;
    const stripX = Math.max(0, w - PRESET_RESET_STRIP_W - slot);
    this._goriSaveSlotH = slot;
    if (origDraw) {
      try {
        origDraw.call(this, ctx, n, width, y, H, lowQuality);
      } catch (_) {
        origDraw.call(this, ctx, n, width, y, H, lowQuality);
      }
    } else {
      drawComboBodyShrunk(this, ctx, stripX, y, H, lowQuality);
    }
    // 저장 아이콘도 항상 그린다 — 사각 배경만 호버에서 (↻ 와 동일 사양).
    drawPresetSaveIcon(ctx, stripX, y, H, presetResetHovered(n, w, y, H));
  };

  const origOnClick = typeof aw.onClick === "function" ? aw.onClick : null;
  aw.onClick = function (arg) {
    try {
      const e = arg?.e;
      const n = arg?.node || node;
      if (e && n) {
        const x = (typeof e.canvasX === "number") ? e.canvasX - n.pos[0] : NaN;
        const width = (typeof this.width === "number" && this.width > 0)
          ? this.width
          : (typeof n.size?.[0] === "number" ? n.size[0] : 0);
        const slot = Number.isFinite(this._goriSaveSlotH)
          ? this._goriSaveSlotH
          : PRESET_RESET_SLOT_FALLBACK_H;
        if (width > 0 && presetResetHitX(x, width, slot)) {
          runWorkflowSave();
          try {
            arg?.canvas?.setDirty?.(true, true);
          } catch (_) {
            /* 무시 */
          }
          return; // 저장 클릭이었다 — 드롭다운을 열지 않는다
        }
      }
    } catch (_) {
      /* 판정 실패는 원래 콤보 클릭을 따른다 */
    }
    return origOnClick ? origOnClick.call(this, arg) : undefined;
  };

  const origMouse = typeof aw.mouse === "function" ? aw.mouse : null;
  if (origMouse) {
    // 구버전 litegraph: mouse 경로만 있는 프런트엔드용. 새 litegraph 는
    // onClick 을 우선해 이 래퍼는 호출되지 않는다.
    aw.mouse = function (event, pos, n) {
      const t = event?.type;
      if ((t === "pointerdown" || t === "mousedown") && Array.isArray(pos)) {
        const width = (typeof this.width === "number" && this.width > 0)
          ? this.width
          : (typeof n?.size?.[0] === "number" ? n.size[0] : 0);
        const slot = Number.isFinite(this._goriSaveSlotH)
          ? this._goriSaveSlotH
          : PRESET_RESET_SLOT_FALLBACK_H;
        if (width > 0 && presetResetHitX(pos[0], width, slot)) {
          runWorkflowSave();
          try {
            app.canvas?.setDirty?.(true, true);
          } catch (_) {
            /* 무시 */
          }
          return true;
        }
      }
      return origMouse.call(this, event, pos, n);
    };
  }
  return true;
}

app.registerExtension({
  name: EXT_ID,
  setup() {
    // Clean up stale timers from previous extension loads to prevent leaks.
    if (llmBlinkTimer) { clearInterval(llmBlinkTimer); llmBlinkTimer = null; }
    if (llmFadeTimer) { clearTimeout(llmFadeTimer); llmFadeTimer = null; }
    // 카메라 노드가 하나도 없는 빈 그래프를 저장하는 경우까지 대비한다.
    // (그 경우엔 이 노드가 없으니 지울 키도 없다 — 그래도 훅은 심어 둔다)
    try {
      hookGraphSerializeBlankApiKey(app.graph);
    } catch (_) {
      /* 무시 */
    }
    // Preset sync: 프리셋별 기억 + 전환 시에만 값 이동 (2026-10-22 R200).
    // 왜(Why) 덮어쓰지 않게 바꿨나: 프리셋 전환마다 미러 값을 덮어써 사용자
    // 편집이 사라졌고, 자동 복귀 시 전 필드가 강제 '자동 (auto)' 로 바뀌었고,
    // 로드 뒤 첫 틱에도 같은 강제 초기화가 돌았다 (R200 제보 — 체크 유실).
    // 첫 관측은 기억만 남긴다. 전부 지우는 일은 리셋 버튼만 한다.
    try {
      setInterval(() => {
        try {
          const nodes = app.graph?._nodes || [];
          for (const node of nodes) {
            if (node?.type !== 'GoRi_CameraDirectorEncodeSkills') continue;
            if (node._goriLastPreset === undefined) {
              // 첫 관측(로드·새 노드): 복원된 값을 그대로 기억한다.
              rememberCurrentPresetFields(node);
              continue;
            }
            const pw = (node.widgets || []).find((w) => w && w.name === 'preset');
            if (!pw) continue;
            const cur = pw.value;
            if (!cur || node._goriLastPreset === cur) continue;
            // 프리셋 전환: 나가는 프리셋의 현재 값을 기억하고, 들어오는
            // 프리셋의 기억이 있으면 복원, 없으면 프리셋 기본값을 적용한다.
            presetMemoryOf(node)[node._goriLastPreset] = snapshotPresetFields(node);
            const remembered = presetMemoryOf(node)[cur];
            applyPresetFields(node, remembered || presetDefaultFields(cur));
            node._goriLastPreset = cur;
          }
        } catch (_) {}
      }, 400);
    } catch (_) {}
  },
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

    /** 공통 지연 처리: 소켓 정리 + (새 노드면) 높이 축소 + 휠 스크롤 훅 +
     * api_key 마스킹. 각 영역은 서로에게 영향을 주지 않게 분리한다.
     * DOM 위젯은 첫 드로잉 때 마운트되므로 여러 시점에 재시도한다. */
    const afterLifecycle = (node) => {
      try {
        if (!node._goriImageTemplate?.length) node._goriImageTemplate = template;
        updateVisibility(node);
      } catch (_) {
        restoreAll(node);
      }
      try {
        maskApiKeyWidget(node);
      } catch (_) {
        /* 마스킹 실패는 조용히 무시 */
      }
      try {
        hookSerializeBlankApiKey(node);
      } catch (_) {
        /* 직렬화 후킹 실패는 조용히 무시 */
      }
      try {
        // 저장 payload 후킹 (1.53.6 실측상 이것이 실제 방어선이다)
        hookGraphSerializeBlankApiKey(node.graph);
      } catch (_) {
        /* 그래프 후킹 실패는 조용히 무시 */
      }
      try {
        hookApiKeyPayloadGuard(node);
      } catch (_) {
        /* 페이로드 가드 실패는 조용히 무시 */
      }
      try {
        attachTopicScroll(node);
      } catch (_) {
        /* 휠 스크롤 훅 실패는 조용히 무시 */
      }
      try {
        // 기능 드롭다운을 다중 선택 토글로 교체 (2026-10-16)
        installMultiSelectWidgets(node);
      } catch (_) {
        /* 다중 선택 위젯 설치 실패는 조용히 무시 — 기본 드롭다운으로 동작 */
      }
      try {
        // 프리셋바 우측(끝에서 한 칸 안쪽) 리셋 버튼 (2026-10-22 R200)
        installPresetResetButton(node);
      } catch (_) {
        /* 리셋 버튼 설치 실패는 조용히 무시 — 프리셋 동기화는 그대로 */
      }
      try {
        // automation 바 폭을 preset 바와 맞춘다 (2026-10-22 23:07)
        installAutomationBarMatch(node);
      } catch (_) {
        /* 폭 정합 실패는 조용히 무시 — automation 은 원래 폭으로 그려진다 */
      }
      try {
        // ↻ 아래 칸(automation 행 스트립)의 저장 버튼 (2026-10-23).
        // **나중에 쓰려고 미리 만들어 둔 것 — 지금은 숨긴다**(사용자 지정
        // 2026-10-23 01:04). 코드는 전부 남아 있고 이 호출만 주석으로 막아
        // 화면에 나타나지 않는다. 다시 쓸 때 아래 줄의 주석을 푼다.
        // 폭 정합 뒤에 설치해야 이중 축소가 없다 (F28 소스 계약).
        // installPresetSaveButton(node);
      } catch (_) {
        /* 저장 버튼 설치 실패는 조용히 무시 — Ctrl+S 로 저장할 수 있다 */
      }
      try {
        // ai_llm_setup 헤더 삽입 — motion2 아래, JS 전용(serialize:false)
        installLlmSetupHeader(node);
      } catch (_) {
        /* 헤더 설치 실패는 조용히 무시 — LLM 6칸이 그대로 노출된다 */
      }
      try {
        // 접힘 상태 적용 (hidden 만 — 크기는 저장된 값을 존중한다). 새 노드는
        // 여기서 기본 접힘으로 들어간다. 로드 경로에서는 onConfigure 에서 이미
        // 동기으로 처리됐다 — 여기는 새로고침·확장 재로드 등 이후 시점의
        // 안전망(멱등).
        applyLlmFoldFromProperties(node);
      } catch (_) {
        /* 접힘 적용 실패는 조용히 무시 */
      }
      try {
        applyFixedTextareaHeight(node);
        ensureFixedTextareaDrawHook(node);
      } catch (_) {
        /* 고정 높이 실패는 조용히 무시 */
      }
      if (!node._goriLoaded && !node._goriShrinkScheduled) {
        node._goriShrinkScheduled = true;
        const pass = () => {
          try {
            if (node._goriLoaded) return; // 로드가 끼어들면 즉시 중단
            shrinkNewNode(node);
            attachTopicScroll(node);
            applyFixedTextareaHeight(node);
            ensureFixedTextareaDrawHook(node);
          } catch (_) {
            /* 축소 실패는 조용히 무시 — 기본 크기로 사용 가능 */
          }
        };
        pass();
        if (typeof requestAnimationFrame === "function") requestAnimationFrame(pass);
        setTimeout(pass, 300);
      } else if (node._goriLoaded) {
        // 로드 경로: 소켓 10개가 만들어진 뒤 프런트엔드가 노드를 콘텐츠에 맞춰
        // 자동 확장했을 수 있다(저장 크기가 작을 때). 저장 크기로 되돌린다
        // (2026-10-19 F5 버그). 확장은 이 시점 뒤에 일어날 수도 있어(디바운스
        // 타이밍 가변) 몇 번 더 시도하고, 최종 방어선은 드로우 훅이다.
        const restore = () => {
          try {
            restoreSavedSize(node);
          } catch (_) {
            /* 복원 실패는 조용히 무시 — 드로우 훅이 다시 시도한다 */
          }
        };
        restore();
        if (typeof requestAnimationFrame === "function") {
          requestAnimationFrame(restore);
        }
        setTimeout(restore, 300);
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

    /* 원본 보존형 후킹(Why): 다른 확장이 같은 메서드를 감쌀 수 있으므로
     * 원본을 인스턴스/프로토타입에 붙여두지 않고 클로저로만 들고 있다.
     * 그래야 ours-first / theirs-first 어느 순서로 로드되어도 호출이
     * 빠지지 않고, 되돌릴 때 원본이 그대로다. */
    const patchLifecycle = (name) => {
      const original = nodeType.prototype[name];
      // 왜(Why) 중복 방지인가: 프론트엔드는 노드 정의를 다시 등록할 수
      // 있고(확장 로드/리로드), 그때마다 이 함수가 다시 호출된다. 방치하면
      // 후킹이 층층이 쌓여 setTimeout 이 N개 예약되고 노드 하나가 소켓
      // 갱신을 N번 한다. 플래그 하나로 구조적으로 막는다.
      if (nodeType.prototype["_goriPatched_" + name]) return;
      nodeType.prototype["_goriPatched_" + name] = true;
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
          // 저장된 크기를 기억한다 (2026-10-19 F5 버그 수정). configure 는
          // 소켓 10개(image_1~image_10, 노드 정의)가 이미 만들어진 뒤에 돌고,
          // 그 상태에서 프런트엔드가 콘텐츠에 맞춰 노드를 자동 확장할 수 있다.
          // 저장 크기가 곧 사용자의 의도이므로 여기서 복사해 두고, 로드 경로의
          // restoreSavedSize 가 확장분을 되돌린다. 이 시점의 this.size 는
          // 방금 복원된 저장값이다.
          try {
            if (isSizeLike(this.size)) {
              this._goriSavedSize = [this.size[0], this.size[1]];
              // 자동 확장은 로드 직후에만 일어난다. 그 창 동안만 복원하고,
              // 창이 지나면 사용자 리사이즈를 건드리지 않는다.
              this._goriRestoreUntil =
                Date.now() + SAVED_SIZE_RESTORE_WINDOW_MS;
            }
          } catch (_) {
            /* 크기 기억 실패는 조용히 무시 — 확장 보정만 생략된다 */
          }
          // 접힘 상태는 **여기서 동기으로** 적용한다 (디바운스를 타지 않는다):
          // 늦게 숨기면 첫 arrange 가 펼친 채로 노드를 자동 증가시켰다가
          // 50ms 뒤 다시 줄여 하단 공백이 남는다(applyLlmFoldFromProperties
          // 주석 참조). configure 는 widgets 완성·properties 복원 뒤에
          // onConfigure 를 부르므로 이 시점에 hidden 토글이 안전하다.
          try {
            applyLlmFoldFromProperties(this);
          } catch (_) {
            /* 접힘 적용 실패는 조용히 무시 */
          }
        }
        scheduleLifecycle(this);
        return result;
      };
    };

    patchLifecycle("onNodeCreated");
    patchLifecycle("onConfigure");

    // 노드 제거 시 점멸 타이머 정리 (2026-10-19 감사, M1).
    // 왜(Why) 필요한가: updateBlinkTimer 는 applyLlmLight 에서만 불린다. busy
    // 노드를 캔버스에서 지우면 anyNodeBlinking() 이 false 가 되지만 재호출이
    // 없어 60ms 인터벌이 다음 execution_start(clearAllLlmLights) 까지 계속
    // 캔버스를 dirty 로 다시 그린다. onRemoved 에서 한 번 점검하면 즉시 멈춘다.
    // patchLifecycle(디바운스+afterLifecycle)은 제거된 노드에 무거운 로직을
    // 태우므로 쓰지 않고, 가벼운 훅을 따로 단다.
    if (!nodeType.prototype._goriPatched_onRemoved) {
      nodeType.prototype._goriPatched_onRemoved = true;
      const origRemoved = nodeType.prototype.onRemoved;
      nodeType.prototype.onRemoved = function (...args) {
        const result = origRemoved?.apply(this, args);
        try {
          updateBlinkTimer();
        } catch (_) {
          /* 타이머 정리 실패는 조용히 무시 — 다음 실행에서 정리된다 */
        }
        return result;
      };
    }

    IMAGE_TEMPLATE = template;

    // 노드 우클릭 메뉴: 공유 전 api_key 원클릭 제거.
    // 저장·실행 직렬화 경로가 같아 저장값만 가리는 건 불가능하므로(가리면
    // 실행도 깨짐), 공유할 때 값을 비우는 방식으로 키 유출을 막는다.
    // 이미 비어 있으면 메뉴를 비활성화한다.
    const origMenu = nodeType.prototype.getExtraMenuOptions;
    if (!nodeType.prototype._goriPatched_getExtraMenuOptions) {
      nodeType.prototype._goriPatched_getExtraMenuOptions = true;
      nodeType.prototype.getExtraMenuOptions = function (canvas, options) {
        try {
          origMenu?.apply(this, arguments);
        } catch (_) {
          /* 기존 메뉴 실패는 무시 */
        }
        try {
          const node = this;
          const w = findApiKeyWidget(node);
          if (w && Array.isArray(options)) {
            options.push({
              content: "api_key 지우기 (공유용)",
              disabled: !String(w.value ?? ""),
              callback: () => clearApiKeyWidget(node),
            });
          }
        } catch (_) {
          /* 메뉴 추가 실패는 무시 */
        }
      };
    }

    const originalConnections = nodeType.prototype.onConnectionsChange;
    if (!nodeType.prototype._goriPatched_onConnectionsChange) {
      nodeType.prototype._goriPatched_onConnectionsChange = true;
      nodeType.prototype.onConnectionsChange = function (...args) {
        const result = originalConnections?.apply(this, args);
        scheduleVisibilityUpdate(this);
        return result;
      };
    }
  },
});

/* 테스트가 후킹된 prototype 을 그대로 재현해 "원본 보존"을 검증할 수
 * 있게 공개한다. 프론트엔드는 확장 export 를 소비하지 않으므로 동작에 영향이
 * 없고, 값은 함수 1개뿐이다. */
export {
  imageNumber, countImageSockets, lastLinkedImageNumber, lastImageSocketIndex,
  isDraggingLink, updateVisibility, restoreAll, topicElement, shrinkNewNode,
  restoreSavedSize,
  applyFixedTextareaHeight, textareaFixedHeight, topicWidgetHeight,
  ensureFixedTextareaDrawHook, FIXED_TEXTAREA_LINES,
  findApiKeyWidget, maskApiKeyWidget, clearApiKeyWidget, apiKeyWidgetIndex,
  hookSerializeBlankApiKey, hookApiKeyPayloadGuard,
  blankApiKeyInWorkflowData, hookGraphSerializeBlankApiKey,
  drawLlmLight, applyLlmLight, anyNodeBlinking, updateBlinkTimer,
  scheduleVisibilityUpdate, VISIBILITY_DEBOUNCE_MS,
  splitMultiValue, joinMultiValue, multiDisplayText,
  installMultiSelectWidget, installMultiSelectWidgets,
  computePopupScreenPos, fitPopupBox, POPUP_MIN_VISIBLE_PX, popupContentScale,
  MULTI_WIDGET_NAMES, MULTI_AUTO_LABEL,
  WIDGET_DISPLAY_LABELS, widgetDisplayName,
  PRESET_RESET_STRIP_W, presetMemoryOf, snapshotPresetFields,
  applyPresetFields, presetDefaultFields, rememberCurrentPresetFields,
  runPresetReset, presetResetHitX, drawPresetResetIcon,
  runPresetWidgetReset,
  PRESET_RESET_SLOT_FALLBACK_H, presetResetHoveredAt, presetResetHovered,
  drawComboBodyShrunk, installAutomationBarMatch,
  installPresetResetButton,
  runWorkflowSave, drawPresetSaveIcon, installPresetSaveButton,
  findLlmHeaderWidget, llmFoldGroupWidgets, measureLlmFoldFootprint,
  setLlmSectionFolded, toggleLlmSectionFolded, applyLlmFoldFromProperties,
  resolveLlmFolded, installLlmSetupHeader, drawLlmSetupHeader,
  LLM_HEADER_NAME, LLM_HEADER_LABEL, LLM_FOLD_WIDGETS,
  LLM_FOLD_PROP, LLM_FOLD_PX_PROP,
};


// ===== Preset data (mirror of presets.json) =====
const CAMERA_PRESETS = {"시네마틱 인물 (cinematic portrait)": {"shot": "중근접 (MCU)", "lens": "85mm f/1.4 (bokeh)", "angle": "수평 (eye-level)", "composition": "삼분할 (rule of thirds)", "lighting": "램브란트 (Rembrandt)", "grade": "시네마틱 필름 (cinematic)", "motion": "없음 (none)", "motion2": "없음 (none)", "speed": "보통 (normal)", "amplitude": "약간 (subtle)"}, "제품 히어로 (product hero)": {"shot": "중근접 (MCU)", "lens": "100mm 매크로 (macro)", "angle": "수평 (eye-level)", "composition": "중앙 대칭 (centered)", "lighting": "3점 스튜디오 (three-point)", "grade": "클린 커머셜 (commercial)", "motion": "없음 (none)", "motion2": "없음 (none)", "speed": "보통 (normal)", "amplitude": "약간 (subtle)"}, "CF 버티컬 (vertical ad)": {"shot": "중근접 (MCU)", "lens": "50mm 표준 (standard)", "angle": "수평 (eye-level)", "composition": "중앙 대칭 (centered)", "lighting": "3점 스튜디오 (three-point)", "grade": "비비드 포스터 (vivid)", "motion": "없음 (none)", "motion2": "없음 (none)", "speed": "느림 (slow)", "amplitude": "약간 (subtle)"}, "다큐 핸드헬드 (doc handheld)": {"shot": "중경 (MS)", "lens": "35mm 스냅 (snapshot)", "angle": "수평 (eye-level)", "composition": "삼분할 (rule of thirds)", "lighting": "흐린 부드러움 (soft overcast)", "grade": "절제된 프리미엄 (premium)", "motion": "없음 (none)", "motion2": "없음 (none)", "speed": "보통 (normal)", "amplitude": "보통 (normal)"}, "드라마틱 롱샷 (dramatic long shot)": {"shot": "원경 (WS)", "lens": "24mm 광각 (wide)", "angle": "로우앵글 (low angle)", "composition": "리딩라인 (leading lines)", "lighting": "로우키 (low key)", "grade": "시네마틱 필름 (cinematic)", "motion": "없음 (none)", "motion2": "없음 (none)", "speed": "느림 (slow)", "amplitude": "강하게 (dramatic)"}};
