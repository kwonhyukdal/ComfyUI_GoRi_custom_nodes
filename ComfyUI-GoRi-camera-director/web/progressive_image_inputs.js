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
    node._goriScanKey = scan.count + ":" + lastLinked;

    const desired = lastLinked === 0
      ? 1
      : Math.min(template.length, lastLinked + LOOKAHEAD);

    let count = scan.count;
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
    if (removed > 0 && Array.isArray(node.size)) {
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
  if (typeof node?.computeSize !== "function") return;
  if (!Array.isArray(node.size)) return;
  const min = node.computeSize();
  if (!Array.isArray(min)) return;
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
  const w = (node.widgets || []).find((x) => x && x.name === "model");
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

// 새 실행이 시작되면 모든 표시등을 초기화 (직전 실행의 잔광 제거)
app.api?.addEventListener?.("execution_start", clearAllLlmLights);

app.registerExtension({
  name: EXT_ID,
  setup() {
    // 카메라 노드가 하나도 없는 빈 그래프를 저장하는 경우까지 대비한다.
    // (그 경우엔 이 노드가 없으니 지울 키도 없다 — 그래도 훅은 심어 둔다)
    try {
      hookGraphSerializeBlankApiKey(app.graph);
    } catch (_) {
      /* 무시 */
    }
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
        }
        setTimeout(() => afterLifecycle(this), 0);
        return result;
      };
    };

    patchLifecycle("onNodeCreated");
    patchLifecycle("onConfigure");

    IMAGE_TEMPLATE = template;

    // 노드 우클릭 메뉴: 공유 전 api_key 원클릭 제거.
    // 저장·실행 직렬화 경로가 같아 저장값만 가리는 건 불가능하므로(가리면
    // 실행도 깨짐), 공유할 때 값을 비우는 방식으로 키 유출을 막는다.
    // 이미 비어 있으면 메뉴를 비활성화한다.
    const origMenu = nodeType.prototype.getExtraMenuOptions;
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
  findApiKeyWidget, maskApiKeyWidget, clearApiKeyWidget, apiKeyWidgetIndex,
  hookSerializeBlankApiKey, hookApiKeyPayloadGuard,
  blankApiKeyInWorkflowData, hookGraphSerializeBlankApiKey,
  drawLlmLight, applyLlmLight, anyNodeBlinking, updateBlinkTimer,
  scheduleVisibilityUpdate, VISIBILITY_DEBOUNCE_MS,
};
