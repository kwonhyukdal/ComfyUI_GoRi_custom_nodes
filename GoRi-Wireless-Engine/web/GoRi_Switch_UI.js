/* 
 * =============================================================
 * PROJECT: GoRi Switch Engine v1.0.2
 * DEVELOPER: GoRi
 * VERSION: 1.0.2 (Build 2026.05.18)
 * 
 * [LICENSE & TERMS OF USE]
 * 1. FREE TO USE: Free for individuals, organizations, and 
 * corporations (No Charge).
 * 2. NO REDISTRIBUTION: Unauthorized duplication or redistribution 
 * on any other platforms is strictly prohibited.
 * 3. NO PLAGIARISM: Any attempt to steal source code or rename 
 * the engine for redistribution is strictly forbidden.
 * 4. ATTRIBUTION: Mentioning "Powered by GoRi Engine" is highly 
 * recommended when sharing workflows.
 * 
 * [LEGAL WARNING]
 * This software is developed by GoRi. Unauthorized copying, 
 * modification, and especially commercial packaging/sales are 
 * subject to legal action under intellectual property laws.
 * (Security: Hidden Watermark 'GoRi-2026.04.15 k' Embedded)
 * 
 * CONTACT: khd57788@gmail.com
 * =============================================================
 */

import { app } from "../../scripts/app.js";
import { GORI_CONFIG } from "./gori_config.js";
import { GORI_RENDERER } from "./gori_render.js";
import { GORI_MENU } from "./gori_menu.js";
import { GORI_CORE } from "./gori_core.js";
import { normalizePastedNodes, disableReceiversBySenderNodes, patchCanvasClipboardMethods, patchProcessKey, findFreeChannel } from "./gori_clipboard.js";
import { patchAltDragMultiClone } from "./gori_clone.js";
import { enforceReceiverBlockFromDisabledSenders } from "./gori_utils.js";
import { patchLGraphAddMethods, patchGraphAddMethods, patchRemoveForBridgeReconnect, startGuardLoop, patchNodeMutationEvents } from "./gori_guard.js";
import { patchContextMenu, checkChannelTextClick, showPicker, closePicker, triggerBroadcast } from "./gori_context_menu.js";

app.registerExtension({
    name: "GoRi.SwitchEngine",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (GORI_CONFIG.isExcluded(nodeData)) return;

        // 1. 노드 상태 저장 (직렬화)
        const originalOnSerialize = nodeType.prototype.onSerialize;
        nodeType.prototype.onSerialize = function(o) {
            originalOnSerialize?.apply(this, arguments);
            o.gori_states = {
                gori_index: this.gori_index, 
                inputs: this.inputs?.map(s => ({ 
                    active: !!s.gori_active, 
                    channel: s.gori_channel || "",
                    auto_blocked: !!s.gori_auto_blocked
                })),
                outputs: this.outputs?.map(s => ({ 
                    active: !!s.gori_active, 
                    channel: s.gori_channel || "",
                    auto_blocked: !!s.gori_auto_blocked
                }))
            };
        };

        // 2. 노드 상태 복구
        const originalOnConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function(o) {
            originalOnConfigure?.apply(this, arguments);
            if (o.gori_states) {
                if (window.GORI._altDragIntCh) {
                    this.__gori_normalized = true;
                } else if ((window.GORI.pasteLevel || 0) > 0) {
                    this.__gori_pending_normalize = true;
                } else {
                    this.__gori_normalized = true;
                }
                this.gori_index = o.gori_states.gori_index;
                o.gori_states.inputs?.forEach((s, i) => { 
                    if (this.inputs && this.inputs[i]) { 
                        this.inputs[i].gori_active = !!s.active; 
                        this.inputs[i].gori_channel = s.channel || ""; 
                        this.inputs[i].gori_auto_blocked = !!s.auto_blocked; 
                    } 
                });
                o.gori_states.outputs?.forEach((s, i) => { 
                    if (this.outputs && this.outputs[i]) { 
                        this.outputs[i].gori_active = !!s.active; 
                        this.outputs[i].gori_channel = s.channel || ""; 
                        this.outputs[i].gori_auto_blocked = !!s.auto_blocked; 
                    } 
                });
            } else {
                this.__gori_normalized = true;
            }
        };

        // 2.1 복제(Clone) 메서드 가로채기 (gori 상태 복사 + pending 플래그 + Alt+drag 채널 재할당 + 중복 방지)
        const originalClone = nodeType.prototype.clone;
        nodeType.prototype.clone = function() {
            // 이미 우리가 만든 클론(id 기반)이면 자기 자신 반환 (LiteGraph 중복 클론 방지)
            if (window.GORI._altDragIds?.has(this.id)) return this;
            // Alt+drag 중 이미 clone된 노드는 중복 반환 방지
            if (window.GORI._altDragCloneMap?.has(this.id)) {
                return window.GORI._altDragCloneMap.get(this.id);
            }
            // 단일 노드 Alt+Drag: originalClone 호출 전에 원본 gori를 초기화했다가 복원
            // → onSerialize/onConfigure가 초기화된 상태를 복제본에 저장
            const isSingleAltDrag = window.GORI._altDragActive && window.GORI._altDragSingle;
            let goriBackup;
            if (isSingleAltDrag) {
                goriBackup = [];
                [...(this.inputs || []), ...(this.outputs || [])].forEach(s => {
                    goriBackup.push({ a: s.gori_active, c: s.gori_channel, b: s.gori_auto_blocked });
                    s.gori_active = false; s.gori_auto_blocked = false;
                });
            }

            const result = originalClone.apply(this, arguments);

            if (isSingleAltDrag) {
                let idx = 0;
                [...(this.inputs || []), ...(this.outputs || [])].forEach(s => {
                    s.gori_active = goriBackup[idx].a;
                    s.gori_channel = goriBackup[idx].c;
                    s.gori_auto_blocked = goriBackup[idx].b;
                    idx++;
                });
            }

            if (result) {
                if (window.GORI._altDragIntCh) {
                    if (!window.GORI._altDragCloneMap) window.GORI._altDragCloneMap = new Map();
                    window.GORI._altDragCloneMap.set(this.id, result);
                }
                result.__gori_cloned = true;
                const altCh = window.GORI._altDragIntCh;

                const copyGori = (srcSlots, dstSlots) => {
                    if (!srcSlots || !dstSlots) return;
                    srcSlots.forEach((s, i) => {
                        if (dstSlots[i]) {
                            if (s.gori_active !== undefined) dstSlots[i].gori_active = s.gori_active;
                            if (s.gori_channel !== undefined) {
                                dstSlots[i].gori_channel = altCh?.has(s.gori_channel) ? altCh.get(s.gori_channel) : s.gori_channel;
                            }
                            if (s.gori_auto_blocked !== undefined) dstSlots[i].gori_auto_blocked = s.gori_auto_blocked;
                        }
                    });
                };

                if (altCh && altCh.size === 0) {
                    result.__gori_normalized = true;
                    const assigned = new Set();
                    [...(result.inputs || []), ...(result.outputs || [])].forEach(s => {
                        const newCh = findFreeChannel(assigned);
                        assigned.add(newCh);
                        s.gori_channel = newCh;
                        s.gori_active = false; s.gori_auto_blocked = false;
                    });
                } else if (altCh) {
                    result.__gori_normalized = true;
                    copyGori(this.outputs, result.outputs);
                    const assigned = new Set();
                    (result.outputs || []).forEach((s, i) => {
                        const origSlot = this.outputs?.[i];
                        if (s && origSlot && origSlot.gori_active && origSlot.gori_channel && !altCh.has(origSlot.gori_channel)) {
                            const newCh = findFreeChannel(assigned);
                            assigned.add(newCh);
                            s.gori_channel = newCh;
                            s.gori_active = false; s.gori_auto_blocked = false;
                        }
                    });
                    (result.inputs || []).forEach(s => {
                        if (s && s.gori_active && s.gori_channel) {
                            if (altCh.has(s.gori_channel)) {
                                s.gori_channel = altCh.get(s.gori_channel);
                                assigned.add(s.gori_channel);
                            } else {
                                const newCh = findFreeChannel(assigned);
                                assigned.add(newCh);
                                s.gori_channel = newCh;
                                s.gori_active = false; s.gori_auto_blocked = false;
                            }
                        }
                    });
                } else {
                    copyGori(this.inputs, result.inputs);
                }
            }
            return result;
        };
        // 3. 시각화 호출 + Hover 배경
        const originalOnDrawForeground = nodeType.prototype.onDrawForeground;
        nodeType.prototype.onDrawForeground = function(ctx) {
            originalOnDrawForeground?.apply(this, arguments);
            if (this.__gori_pending_normalize) return;
            const gr = window.GORI;
            const hs = gr?.pinnedSlot || gr?.hoveredSlot;
            if (GORI_MENU.state.isActive && hs && hs.node === this && hs.slot && hs.slot.gori_channel && !hs.slot.widget) {
                const sPos = GORI_RENDERER.getSwitchPos(this, hs.slot, hs.isInput, hs.index);
                if (sPos) {
                    const chText = hs.slot.gori_channel || "";
                    const tc = document.createElement('canvas').getContext('2d');
                    tc.font = "italic 10px Arial";
                    const cw = tc.measureText(chText).width || 0;
                    const { gap, pad, h } = window.GORI?.BOX || { gap: 12, pad: 4, h: 16 };
                    const bx = hs.isInput ? sPos.localX + gap - pad + 0.5 : sPos.localX - gap - cw - pad + 0.5;
                    const bw = cw + pad * 2;
                    const by = sPos.localY + 1.5 - h/2;
                    ctx.save();
                    GORI_RENDERER.roundRect(ctx, bx, by, bw, h, 2.5);
                    ctx.fillStyle = "rgba(0, 0, 0, 0.70)";
                    ctx.fill();
                    ctx.restore();
                }
            }
            GORI_RENDERER.drawVisuals(ctx, this, app);
        };

        // 4. 마우스 좌클릭 스위치 토글
        const originalMouseDown = nodeType.prototype.onMouseDown;
        nodeType.prototype.onMouseDown = function (e) {
            if (e.button === 0) {
                const check = (slots, isInput) => {
                    if (!slots) return false;
                    for (let i = 0; i < slots.length; i++) {
                        const p = GORI_RENDERER.getSwitchPos(this, slots[i], isInput, i);
                        if (Math.sqrt((e.canvasX - p.x) ** 2 + (e.canvasY - p.y) ** 2) < 12) {
                            slots[i].gori_active = !slots[i].gori_active;
                            this.setDirtyCanvas(true, true);
                            return true;
                        }
                    }
                    return false;
                };
                if (check(this.inputs, true) || check(this.outputs, false)) return true;
            }
            return originalMouseDown?.apply(this, arguments);
        };
    },

    async setup() {
        GORI_MENU.init();  
        GORI_CORE.init();  
        console.log("✅ GoRi 엔진 패치 로드됨: 복사/붙여넣기 보정 v2026-05-08");

        window.GORI.normalizePastedNodes = normalizePastedNodes;

        const ensureCanvasPatches = () => {
            const okClipboard = patchCanvasClipboardMethods();
            const okKey = patchProcessKey();
            const okGraphProto = patchLGraphAddMethods();
            const okGraphInst = patchGraphAddMethods();
            const okGraph = okGraphProto || okGraphInst;
            const okRemove = patchRemoveForBridgeReconnect();
            const okMutation = patchNodeMutationEvents();
            const okAltDrag = patchAltDragMultiClone();
            const canvasInfo = window.app?.canvas ? 
                `ctor=${window.app.canvas.constructor?.name} pdPatched=${!!window.app.canvas.__goriPDMultiPatched}` 
                : 'no canvas';
            console.log(`🔄 GoRi 패치 시도: clipboard=${okClipboard} graph=${okGraph} altdrag=${okAltDrag} mutation=${okMutation} canvas=${canvasInfo}`);
            if (okClipboard && okGraph && okAltDrag) {
                if (!window.GORI.clipboardPatchReadyLogged) {
                    window.GORI.clipboardPatchReadyLogged = true;
                    console.log("✅ GoRi 복사/붙여넣기 훅 연결 완료");
                }
                // canvas DOM에 직접 리스너 등록 (Vue 우회)
                const domEl = window.app?.canvas?.canvas;
                if (domEl && domEl.addEventListener && !domEl.__goriPickerDone) {
                    domEl.__goriPickerDone = true;
                    // drawFrontCanvas 인스턴스 패치 (InputIndicators가 인스턴스 레벨에서 덮어써도 무시되지 않도록)
                    const cvs = window.app.canvas;
                    if (cvs && !cvs.__goriDFCPatched) {
                        cvs.__goriDFCPatched = true;
                        const origDFC = cvs.drawFrontCanvas.bind(cvs);
                        cvs.drawFrontCanvas = function(ctx) {
                            origDFC(ctx);
                            if (typeof window.GORI.updatePickerOverlay === 'function') {
                                window.GORI.updatePickerOverlay(cvs);
                            }
                        };
                    }
                    const blockPickerClick = (e) => {
                        if (e.button !== 0) return;
                        const gm = window.app?.canvas?.graph_mouse;
                        const ps = window.GORI?.pickerState;
                        if (!ps?.active || !gm) return false;
                        const { bx, by, baseW, baseH, itemH, list, cur, node: pn } = ps;
                        const liveScale = window.GORI.pickerScale || ps.scale || 1.0;
                        const { h: bh } = window.GORI.BOX;
                        const displayW = baseW * liveScale;
                        const displayH = baseH * liveScale;
                        const px = pn.pos[0] + bx, py = pn.pos[1] + by + bh + 1;
                        if (gm[0] >= px && gm[0] <= px + displayW && gm[1] >= py && gm[1] <= py + displayH) {
                            e.stopPropagation();
                            return true;
                        }
                        return false;
                    };
                    const handlePickerClick = (e) => {
                        if (e.button !== 0) return;
                        const cvs = window.app?.canvas;
                        if (!cvs) return;
                        const ps = window.GORI?.pickerState;
                        const gm = cvs.graph_mouse;
                        if (!gm) return;
                        const gx = gm[0], gy = gm[1];
                        if (ps?.active) {
                            // 메뉴 팝업/버튼 클릭 시 픽커 유지
                            const menuEl = document.getElementById('gori-popup-container');
                            const hamburgerEl = document.getElementById('gori-hamburger-menu');
                            if ((menuEl && menuEl.contains(e.target)) || (hamburgerEl && hamburgerEl.contains(e.target))) return;
                            if (e.target && e.target.closest && e.target.closest('#gori-picker-overlay')) return;
                            const { bx, by, baseW, baseH, itemH, list, cur, node: pn } = ps;
                            const liveScale = window.GORI.pickerScale || ps.scale || 1.0;
                            const s = cvs?.ds?.scale || 1;
                            const { h: bh } = window.GORI.BOX;
                            const displayW = baseW * liveScale;
                            const displayH = baseH * liveScale;
                            const px = pn.pos[0] + bx, py = pn.pos[1] + by + bh + 1;
                            if (gx >= px && gx <= px + displayW && gy >= py && gy <= py + displayH) {
                                const si = Math.max(0, Math.min(list.length - 4, cur - 1));
                                const idx = Math.floor((gy - py - 1 / s) / (itemH * liveScale));
                                const itemIdx = si + idx;
            if (itemIdx >= 0 && itemIdx < list.length) {
                const clickedChannel = list[itemIdx];
                if (clickedChannel === ps.slot.gori_channel && !ps.isInput && ps.slot.gori_active) {
                    triggerBroadcast(ps.slot, ps.node);
                    closePicker();
                    cvs.setDirty(true, true);
                    e.preventDefault();
                    e.stopPropagation();
                    window.GORI._pickerProcessed = true;
                    clearTimeout(window.GORI._pCooldown);
                    window.GORI._pCooldown = setTimeout(() => { window.GORI._pickerProcessed = false; }, 300);
                    return;
                }
                window.GORI._setNodeCh(ps.slot, ps.node, ps.isInput, ps.index, clickedChannel);
                ps.slot.gori_manual = true;
                ps.slot.gori_active = true;
                ps.slot.gori_auto_blocked = false;
                if (ps.isInput) {
                    const _idx = ps.list.indexOf(clickedChannel);
                    if (_idx >= 0) {
                        ps.list.splice(_idx, 1);
                        if (window.GORI.updatePickerOverlay) window.GORI.updatePickerOverlay(cvs);
                    }
                }
                pn.setDirtyCanvas(true, true);
                if (pn.graph) pn.graph._version++;
            }
                                closePicker();
                                cvs.setDirty(true, true);
                                e.preventDefault();
                                e.stopPropagation();
                                window.GORI._pickerProcessed = true;
                                clearTimeout(window.GORI._pCooldown);
                                window.GORI._pCooldown = setTimeout(() => { window.GORI._pickerProcessed = false; }, 300);
                                return;
                            }
                            closePicker();
                            cvs.setDirty(true, true);
                            window.GORI._pickerProcessed = false;
                            clearTimeout(window.GORI._pCooldown);
                        }
                        const hit = checkChannelTextClick(cvs.graph, gx, gy);
                        if (hit) {
                            e.preventDefault();
                            e.stopPropagation();
                            showPicker(hit.slot, hit.sPos, hit.isInput, hit.index, hit.node);
                            window.GORI._pickerProcessed = true;
                            clearTimeout(window.GORI._pCooldown);
                            window.GORI._pCooldown = setTimeout(() => { window.GORI._pickerProcessed = false; }, 300);
                        } else if (cvs.node_over || cvs.node_dragging || cvs.mode) {
                            if (cvs.mode) cvs.mode = 0;
                            cvs.node_over = null;
                            cvs.node_dragging = null;
                            cvs.setDirty(true, true);
                        }
                    };
                    document.addEventListener('pointerdown', handlePickerClick, true);
                    // H 키(팬/이동 모드) 완전 차단 — 실수로 눌러도 손 모양 전환 방지
                    document.addEventListener('keydown', function(e) {
                        if (e.key === 'h' || e.key === 'H') {
                            e.preventDefault();
                            e.stopPropagation();
                        }
                    }, true);
                    ['mousedown', 'mouseup', 'click', 'dblclick', 'pointerup'].forEach(evt => {
                        document.addEventListener(evt, function(e) {
                            if (window.GORI._pickerProcessed) { e.preventDefault(); e.stopPropagation(); return; }
                        }, true);
                    });
                    // 픽커 + 드롭박스 영역에서 휠 줌 차단 (캡처 단계로 등록)
                    domEl.addEventListener('wheel', function(e) {
                        const ps = window.GORI?.pickerState;
                        if (!ps?.active) return;
                        const gm = window.app?.canvas?.graph_mouse;
                        if (!gm) return;
                        const { bx, by, bw, baseW, baseH, list, cur, node: pn } = ps;
                        const liveScale = window.GORI.pickerScale || ps.scale || 1.0;
                        const { h: bh } = window.GORI.BOX;
                        const displayW = baseW * liveScale;
                        const displayH = baseH * liveScale;
                        const nx = pn.pos[0], ny = pn.pos[1];
                        const hx = nx + bx, hy = ny + by;
                        const px = nx + bx, py = ny + by + bh + 1;
                        const inHover = gm[0] >= hx && gm[0] <= hx + bw && gm[1] >= hy && gm[1] <= hy + bh;
                        const inPicker = gm[0] >= px && gm[0] <= px + displayW && gm[1] >= py && gm[1] <= py + displayH;
                        if (inHover || inPicker) {
                            e.preventDefault(); e.stopPropagation();
                            const nv = e.deltaY > 0 ? cur + 1 : cur - 1;
                            ps.cur = Math.max(0, Math.min(list.length - 1, nv));
                            window.app.canvas.setDirty(true, true);
                        }
                    }, { passive: false, capture: true });
                }
                return;
            }
            setTimeout(ensureCanvasPatches, 100);
        };
        ensureCanvasPatches();

        if (!window.GORI.pasteKeyListener) {
            window.GORI.pasteKeyListener = true;
            let last = 0;
            window.addEventListener("keydown", (e) => {
                if (e.target?.tagName === "INPUT" || e.target?.tagName === "TEXTAREA" || e.target?.isContentEditable) return;
                const key = (e?.key || "").toLowerCase();
                
                if (!(e?.ctrlKey && !e?.shiftKey && (key === "v"))) return;
                const now = Date.now();
                if (now - last < 120) return;
                last = now;
                // 누산기가 정규화를 처리함
            }, true);
        }

        // 상시 감시 루프 (gori_guard.js로 분할)
        startGuardLoop(app);

        patchContextMenu();
// 6. 단축키 시스템 (G / S / Shift+S)
        // 캡처 단계(true) 사용: Load Image INPUT 등이 ESC를 가로채는 것 방지
        window.addEventListener('keydown', (e) => {
            // Load Image INPUT 등 하위 요소가 ESC를 가로채도 우리가 먼저 처리
            const key = e.key.toLowerCase();

            // [ESC] - INPUT 등에 포커스가 있어도 항상 동작 (Load Image 노드 대응)
            if (key === 'escape') {
                const popup = document.getElementById("gori-popup-container");
                if (popup) {
                    console.log("close GoRi Popup (ESC)");
                    popup.remove();
                    e.preventDefault();
                }
                // 다중 선택 완전 초기화 (ComfyUI 내부 상태까지 직접 정리)
                const canvas = app.canvas;
                const graph = app.graph;
                if (canvas) {
                    // 0. 네이티브 deselectAllNodes 먼저 호출
                    if (typeof canvas.deselectAllNodes === 'function') {
                        canvas.deselectAllNodes();
                    }
                    // 1. 모든 노드 is_selected 플래그 제거
                    graph?._nodes?.forEach(n => { n.is_selected = false; });
                    // 2. selected_nodes 완전 비우기 (Map/객체 모두)
                    if (canvas.selected_nodes) {
                        const sel = canvas.selected_nodes;
                        const keys = sel instanceof Map ? [...sel.keys()] : Object.keys(sel);
                        keys.forEach(k => {
                            if (sel instanceof Map) sel.delete(k);
                            else delete sel[k];
                        });
                    }
                    // 3. _selected_nodes 직접 정리 (내부 저장소)
                    if (canvas._selected_nodes) {
                        if (canvas._selected_nodes instanceof Map) canvas._selected_nodes.clear();
                        else canvas._selected_nodes = {};
                    }
                    // 4. 마우스 호버 + 드래그 상태 초기화 (연결선 재등장 방지)
                    canvas.node_over = null;
                    canvas.node_dragging = null;
                    // 5. 팬 모드(Pan/H 모드) 해제
                    if (canvas.mode) canvas.mode = 0;
                    // 6. 캔버스 완전 갱신
                    canvas.setDirty(true, true);
                    if (graph) graph.change();
                }
                return;
            }

            // INPUT/TEXTAREA에 포커스 있으면 나머지 단축키 무시 (ESC는 위에서 이미 처리됨)
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.isContentEditable) return;
            const nodes = app.graph._nodes;
            if (!nodes) return;

            if (!GORI_MENU.state.isActive) return;

            // [G] - 하이브리드 지능형 청소
            if (key === 'g' && !e.shiftKey) {
                e.preventDefault();
                const selectedNodes = Object.values(app.canvas.selected_nodes || {});

                if (selectedNodes.length > 0) {
                    console.log(`🧹 GoRi: 선택된 ${selectedNodes.length}개 노드 공장 초기화.`);
                    // 초기화 전에 각 채널의 전체 공유 노드 수를 미리 계산 (노드 단위, 슬롯 중복 제외)
                    const channelTotal = new Map();
                    nodes.forEach(m => {
                        const nodeChs = new Set();
                        [...(m.inputs || []), ...(m.outputs || [])].forEach(s => {
                            if (s.gori_active && s.gori_channel) nodeChs.add(s.gori_channel);
                        });
                        nodeChs.forEach(ch => channelTotal.set(ch, (channelTotal.get(ch) || 0) + 1));
                    });
                    selectedNodes.forEach(n => {
                        const chs = new Set();
                        [...(n.inputs || []), ...(n.outputs || [])].forEach(slot => {
                            if (slot.gori_active && slot.gori_channel) chs.add(slot.gori_channel);
                            slot.gori_active = false; 
                            slot.gori_auto_blocked = false;
                        });
                        // 전체 공유가 정확히 2개인 채널만 파트너 초기화 (3+이면 선택된 노드만)
                        chs.forEach(ch => {
                            if (channelTotal.get(ch) === 2) {
                                const partner = nodes.find(m =>
                                    m !== n && [...(m.inputs || []), ...(m.outputs || [])].some(t => t.gori_active && t.gori_channel === ch)
                                );
                                if (partner) {
                                    partner.setDirtyCanvas?.(true, true);
                                    [...(partner.inputs || []), ...(partner.outputs || [])].forEach(t => {
                                        if (t.gori_active && t.gori_channel === ch) {
                                            t.gori_active = false; t.gori_auto_blocked = false;
                                        }
                                    });
                                }
                            }
                        });
                        if (n.setDirtyCanvas) n.setDirtyCanvas(true, true);
                    });
                } else {
                    console.log("🧹 GoRi: 전체 유령 신호 및 비활성 슬롯 정밀 청소.");
                    const activeOuts = new Set();
                    const activeIns = new Set();
                    
                    nodes.forEach(n => {
                        n.outputs?.forEach(s => { if(s.gori_active && s.gori_channel) activeOuts.add(s.gori_channel); });
                        n.inputs?.forEach(s => { if(s.gori_active && s.gori_channel) activeIns.add(s.gori_channel); });
                    });

                    nodes.forEach(n => {
                        [...(n.inputs || []), ...(n.outputs || [])].forEach(slot => {
                            const isInput = n.inputs?.includes(slot);
                            const hasPartner = isInput ? activeOuts.has(slot.gori_channel) : activeIns.has(slot.gori_channel);
                            
                            if (!slot.gori_active || !hasPartner) {
                                slot.gori_active = false;
                            }
                        });
                        if (n.setDirtyCanvas) n.setDirtyCanvas(true, true);
                    });
                }
                app.canvas.setDirty(true, true);
            }

            // [S] - 시각적 인덱스 리셋
            if (key === 's' && !e.shiftKey) {
                e.preventDefault();
                console.log("📡 GoRi Engine: Scan & Re-indexing Triggered.");
                GORI_CORE.updateVisualIndices();

                const sortedNodes = [...nodes].sort((a, b) => {
                    if (Math.abs(a.pos[1] - b.pos[1]) > 50) return a.pos[1] - b.pos[1];
                    return a.pos[0] - b.pos[0];
                });

                let counter = 1;
                const channelMap = new Map();
                const activeInputCountByChannel = new Map();
                const activeOutputCountByChannel = new Map();

                const inc = (map, key) => map.set(key, (map.get(key) || 0) + 1);

                nodes.forEach((n) => {
                    n.inputs?.forEach((slot) => {
                        if (slot.gori_channel && !slot.gori_auto_blocked) {
                            inc(activeInputCountByChannel, slot.gori_channel);
                        }
                    });
                    n.outputs?.forEach((slot) => {
                        if (slot.gori_channel) {
                            inc(activeOutputCountByChannel, slot.gori_channel);
                        }
                    });
                });

                const channelsToRename = new Set();
                const allChs = new Set([...activeOutputCountByChannel.keys(), ...activeInputCountByChannel.keys()]);
                allChs.forEach(channel => {
                    const isManual = nodes.some(n =>
                        [...(n.inputs || []), ...(n.outputs || [])].some(s =>
                            s.gori_channel === channel && s.gori_manual
                        )
                    );
                    if (!isManual) channelsToRename.add(channel);
                });

                // 이번 S에서 이름을 바꾸지 않는 채널명은 "예약" 처리해 충돌 재사용 방지
                const reservedNames = new Set();
                nodes.forEach((n) => {
                    [...(n.inputs || []), ...(n.outputs || [])].forEach((slot) => {
                        if (slot.gori_channel && !channelsToRename.has(slot.gori_channel)) {
                            reservedNames.add(slot.gori_channel);
                        }
                    });
                });

                sortedNodes.forEach((n) => {
                    n.outputs?.forEach((slot) => {
                        if (slot.gori_channel && channelsToRename.has(slot.gori_channel) && !channelMap.has(slot.gori_channel)) {
                            let newName = `CH_${String(counter).padStart(3, '0')}`;
                            while (reservedNames.has(newName) || [...channelMap.values()].includes(newName)) {
                                counter++;
                                newName = `CH_${String(counter).padStart(3, '0')}`;
                            }
                            channelMap.set(slot.gori_channel, newName);
                            counter++;
                        }
                    });
                });

                // 중요: 채널 단위로 전체 슬롯에 동일 적용 (활성/비활성 섞여도 쌍이 안 갈라지게)
                nodes.forEach((n) => {
                    n.inputs?.forEach((slot) => {
                        if (channelMap.has(slot.gori_channel)) {
                            slot.gori_channel = channelMap.get(slot.gori_channel);
                        }
                    });
                    n.outputs?.forEach((slot) => {
                        if (channelMap.has(slot.gori_channel)) {
                            slot.gori_channel = channelMap.get(slot.gori_channel);
                        }
                    });
                });

                app.canvas.setDirty(true, true);
                console.log("✅ GoRi Engine: Visual Indexing & Sync Complete.");
            }

            // [Shift + S] - 슈퍼 어셈블러
            if (key === 's' && e.shiftKey) {
                e.preventDefault();
                console.log("⚡ GoRi Engine: Super Assembler 가동.");

                GORI_CORE.updateVisualIndices();

                if (GORI_CORE.convertWiresToGori) {
                    GORI_CORE.convertWiresToGori(nodes);
                }

                if (GORI_CORE.autoConnectByTypes) {
                    GORI_CORE.autoConnectByTypes(nodes);
                }

                app.canvas.setDirty(true, true);
                console.log("⚡ GoRi Engine: Super Assembly Complete.");
            }
        }, true);
    }
});
