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

import { GORI_RENDERER } from "./gori_render.js";
import { GORI_MENU } from "./gori_menu.js";

console.log("📦 gori_context_menu.js loaded");
window.GORI = window.GORI || {};
window.GORI.BOX = { gap: 12, pad: 4, h: 16 };

const CHANNEL_POOL = Array.from({ length: 20 }, (_, i) => "CH_" + String(i + 1).padStart(2, "0"));

let _prevHoverKey = "";
let _broadcastMap = new Map(); // channel -> {type, expiry, timer}

// io 스키마 노드 대응: slot.gori_channel이 유지되지 않으므로 node에 이중 저장
const _goriKey = (isInput, index) => (isInput ? 'i' : 'o') + index;
const _getNodeCh = (node, isInput, index) => {
    const v = node.goriCh?.[_goriKey(isInput, index)] || "";
    return v;
};
const _setNodeCh = (slot, node, isInput, index, ch) => {
    const k = _goriKey(isInput, index);
    slot.gori_channel = ch;
    if (!node.goriCh) node.goriCh = {};
    node.goriCh[k] = ch;
};
window.GORI._setNodeCh = _setNodeCh;

// ===== 채널명 픽커 박스 (상태 저장, 캔버스에 그림) =====
const showPicker = (slot, sPos, isInput, index, node) => {
    const canvas = window.app?.canvas;
    if (!canvas || !canvas.graph) { console.warn("GoRi showPicker: no canvas/graph"); return; }
    const savedCh = slot.gori_channel || _getNodeCh(node, isInput, index) || "";
    const curCh = savedCh;
    if (curCh && !slot.gori_channel) slot.gori_channel = curCh;
    const { gap, pad, h } = window.GORI.BOX;
    const tc = document.createElement('canvas').getContext('2d');
    tc.font = "italic 10px Arial";
    const cw = tc.measureText(curCh).width || 0;
    const bx = isInput ? sPos.localX + gap - pad + 0.5 : sPos.localX - gap - cw - pad + 0.5;
    const by = sPos.localY + 1.5 - h/2;
    const chMatch = (curCh || "CH_01").match(/^(CH_)(\d+)$/);
    const poolCount = chMatch ? Math.max(2, chMatch[2].length) : 2;
    const CHANNEL_POOL = Array.from({ length: 20 }, (_, i) => "CH_" + String(i + 1).padStart(poolCount, "0"));
    const usedChs = new Set();
    const connectedChs = new Set();
    canvas.graph._nodes.forEach(n => {
        const scan = (slots) => {
            if (!slots) return;
            slots.forEach(s => {
                if (!s.gori_channel) return;
                usedChs.add(s.gori_channel);
            });
        };
        scan(n.inputs);
        scan(n.outputs);
        const opposite = isInput ? (n.outputs || []) : (n.inputs || []);
        opposite.forEach(s => {
            if (!s.gori_active || !s.gori_channel) return;
            connectedChs.add(s.gori_channel);
        });
    });
    const isConnected = curCh ? connectedChs.has(curCh) : false;
    const inChs = new Set(), outChs = new Set();
    canvas.graph._nodes.forEach(n => {
        (n.inputs || []).forEach(s => { if (s.gori_active && s.gori_channel) inChs.add(s.gori_channel); });
        (n.outputs || []).forEach(s => { if (s.gori_active && s.gori_channel) outChs.add(s.gori_channel); });
    });
    const pairedSet = new Set();
    inChs.forEach(ch => { if (outChs.has(ch)) pairedSet.add(ch); });
    const showPurple = (ch) => ch !== curCh && connectedChs.has(ch) && !pairedSet.has(ch);
    let freeCh = null;
    if (curCh) {
        const m = curCh.match(/^(CH_)(\d+)$/);
        if (m) {
            const prefix = m[1], digits = m[2].length, start = parseInt(m[2], 10);
            for (let n = 1; n <= 100; n++) {
                const cand = prefix + String(start + n).padStart(digits, "0");
                if (!usedChs.has(cand) && cand !== curCh) { freeCh = cand; break; }
            }
        }
    }
    const poolPurple = [...usedChs].filter(ch => ch !== curCh && showPurple(ch));
    const list = [];
    if (curCh) list.push(curCh);
    if (isInput) {
        const now = Date.now();
        const sameNodeUsed = new Set();
        (node.inputs || []).forEach((s, i) => {
            if (i === index) return;
            const ch = s.gori_channel || _getNodeCh(node, true, i);
            if (ch && ch !== curCh) sameNodeUsed.add(ch);
        });
        _broadcastMap.forEach((val, ch) => {
            if (val.expiry <= now) { _broadcastMap.delete(ch); return; }
            if (ch === curCh) return;
            if (sameNodeUsed.has(ch)) return;
            const typeMatch = slot.type === val.type || slot.type === "*" || val.type === "*";
            if (typeMatch && !list.includes(ch)) list.push(ch);
        });
    }
    if (freeCh && !list.includes(freeCh)) list.push(freeCh);
    poolPurple.forEach(ch => { if (!list.includes(ch)) list.push(ch); });
    if (list.length === 0) return;
    if (new Set(list).size !== list.length) {
        const dedup = [...new Set(list)];
        list.length = 0;
        list.push(...dedup);
    }
    let cur = 0;
    const itemH = 14;
    const chkW = tc.measureText(" ✓").width || 0;
    const maxW = list.reduce((m, ch) => Math.max(m, tc.measureText(ch).width + (ch === slot.gori_channel ? chkW : 0)), 0);
    const pw = Math.max(cw, maxW) + pad * 2;
    const ph = itemH * Math.min(4, Math.max(2, list.length)) + 2;
    window.GORI = window.GORI || {};
    const hiddenWidgets = [];
    (node.widgets || []).forEach(w => { if (w.element) { w.element.style.visibility = 'hidden'; hiddenWidgets.push(w.element); } });
    window.GORI.pickerState = { active: true, slot, sPos, isInput, index, node, list, cur, bx, by, bw: cw + pad * 2, pw, ph, baseW: pw, baseH: ph, scale: window.GORI.pickerScale || 1.0, itemH, isConnected, connectedChs, _hiddenWidgets: hiddenWidgets };
    window.GORI.pinnedSlot = { node, slot, isInput, index };
    const ov = _getPickerOverlay();
    const now = Date.now();
    const bSet = new Set();
    _broadcastMap.forEach((val, ch) => { if (val.expiry > now) bSet.add(ch); });
    ov.innerHTML = _buildOverlayHTML(list, cur, slot, isConnected, usedChs, connectedChs, pairedSet, bSet);
    ov.style.display = 'block';
    canvas.setDirty(true, true);
};

// ===== processMouseDown 패치를 통해 채널명 좌클릭 감지 =====
const checkChannelTextClick = (graph, gx, gy) => {
    if (!graph || !graph._nodes) return null;
    for (const node of graph._nodes) {
        if (!node.size || node.flags.collapsed) continue;
        const checkText = (slots, isInput) => {
            if (!slots) return null;
            for (let i = 0; i < slots.length; i++) {
                const s = slots[i];
                if (!s.gori_channel) {
                    const saved = _getNodeCh(node, isInput, i);
                    if (saved) s.gori_channel = saved; else continue;
                }
                const p = GORI_RENDERER.getSwitchPos(node, s, isInput, i);
                if (!p) continue;
                const tc = document.createElement('canvas').getContext('2d');
                tc.font = "italic 10px Arial";
                const cw = tc.measureText(s.gori_channel).width || 0;
                const { gap, pad, h } = window.GORI.BOX;
                const hitH = 22;
                const hitPad = 8;
                const hitX = isInput ? p.localX + gap - hitPad + 0.5 : p.localX - gap - cw - hitPad + 0.5;
                const hitY = p.localY + 1.5 - hitH/2;
                const ax = node.pos[0] + hitX;
                const ay = node.pos[1] + hitY;
                if (gx >= ax && gx <= ax + cw + hitPad * 2 && gy >= ay && gy <= ay + hitH) {
                    return { slot: s, sPos: p, isInput, index: i, node };
                }
            }
            return null;
        };
        const hit = checkText(node.inputs, true) || checkText(node.outputs, false);
        if (hit) return hit;
    }
    return null;
};

let __closeWidgets = null;
let _pickerOverlay = null;

const _getPickerOverlay = () => {
    if (!_pickerOverlay) {
        _pickerOverlay = document.createElement('div');
        _pickerOverlay.id = 'gori-picker-overlay';
        _pickerOverlay.style.cssText = 'position:fixed;z-index:9999;pointer-events:auto;background:#000;border:1px solid #333;border-radius:2.5px;font:italic 10px/14px Arial;padding:1px 0;display:none;';
        document.body.appendChild(_pickerOverlay);
        const st = document.createElement('style');
        st.textContent = '#gori-picker-overlay::-webkit-scrollbar{width:6px}#gori-picker-overlay::-webkit-scrollbar-track{background:transparent}#gori-picker-overlay::-webkit-scrollbar-thumb{background:rgba(255,255,255,0.25);border-radius:3px}';
        document.head.appendChild(st);
        _pickerOverlay.addEventListener('pointerdown', (e) => {
            const ps = window.GORI?.pickerState;
            if (!ps?.active || !ps.node) return;
            const cvs = window.app?.canvas;
            if (!cvs) return;
            const rect = _pickerOverlay.getBoundingClientRect();
            const relY = e.clientY - rect.top;
            const liveScale = window.GORI.pickerScale || ps.scale || 1.0;
            const s = cvs?.ds?.scale || 1;
            const lineH = ps.itemH * liveScale * s;
            const idx = Math.floor((relY - 1) / lineH);
            const si = Math.max(0, Math.min(ps.list.length - 4, ps.cur - 1));
            const displayCount = Math.min(4, ps.list.length - si);
            if (idx >= 0 && idx < displayCount) {
                const itemIdx = si + idx;
                if (itemIdx >= 0 && itemIdx < ps.list.length) {
                    e.preventDefault();
                    e.stopPropagation();
                    const clickedChannel = ps.list[itemIdx];
                    if (clickedChannel === ps.slot.gori_channel && !ps.isInput && ps.slot.gori_active) {
                        triggerBroadcast(ps.slot, ps.node);
                        closePicker();
                        ps.node.setDirtyCanvas(true, true);
                        return;
                    }
                    _setNodeCh(ps.slot, ps.node, ps.isInput, ps.index, clickedChannel);
                    ps.slot.gori_manual = true;
                    ps.slot.gori_active = true;
                    ps.slot.gori_auto_blocked = false;
                    if (ps.isInput) {
                        const idx = ps.list.indexOf(clickedChannel);
                        if (idx >= 0) {
                            ps.list.splice(idx, 1);
                            if (window.GORI.updatePickerOverlay) window.GORI.updatePickerOverlay(cvs);
                        }
                    }
                    ps.node.setDirtyCanvas(true, true);
                    if (ps.node.graph) ps.node.graph._version++;
                    closePicker();
                    cvs.setDirty(true, true);
                }
            }
        });
        _pickerOverlay.addEventListener('wheel', (e) => {
            const ps = window.GORI?.pickerState;
            if (!ps?.active) return;
            e.preventDefault();
            e.stopPropagation();
            const delta = e.deltaY > 0 ? 1 : -1;
            let nc = ps.cur + delta;
            nc = Math.max(0, Math.min(ps.list.length - 1, nc));
            if (nc !== ps.cur) {
                ps.cur = nc;
                const cvs = window.app?.canvas;
                if (cvs) {
                    if (window.GORI.updatePickerOverlay) window.GORI.updatePickerOverlay(cvs);
                    cvs.setDirty(true, true);
                }
            }
        }, { passive: false });
    }
    return _pickerOverlay;
};

const _buildOverlayHTML = (list, cur, slot, isConnected, usedSet, connSet, pairedSet, broadcastSet) => {
    const si = Math.max(0, Math.min(list.length - 4, cur - 1));
    const vi = Math.min(4, list.length - si);
    let html = '';
    for (let i = si; i < si + vi && i < list.length; i++) {
        const isCur = list[i] === slot.gori_channel;
        const isBroadcast = broadcastSet && broadcastSet.has(list[i]);
        const color = isCur ? '#69f0ae' : (isBroadcast ? '#ce93d8' : (connSet.has(list[i]) && !pairedSet.has(list[i]) ? '#ce93d8' : (usedSet.has(list[i]) ? '#fff' : '#555')));
        const bg = i === cur ? 'rgba(255,255,255,0.1)' : 'transparent';
        let txt = list[i];
        if (isCur && isConnected) txt += ' ✓';
        html += `<div style="padding:0 4px;color:${color};background:${bg};white-space:nowrap;">${txt}</div>`;
    }
    if (list.length > 4) {
        const thumbH = Math.max(8, (4 / list.length) * 100);
        const thumbTop = (cur / (list.length - 1)) * (100 - thumbH);
        html += `<div style="position:absolute;right:1px;top:2px;bottom:2px;width:4px;border-radius:2px;background:rgba(255,255,255,0.08);pointer-events:none;"><div style="position:absolute;left:0;width:100%;height:${thumbH}%;top:${thumbTop}%;border-radius:2px;background:rgba(255,255,255,0.3);pointer-events:none;"></div></div>`;
    }
    return html;
};

const closePicker = () => {
    __closeWidgets = window.GORI?.pickerState?._hiddenWidgets;
    window.GORI.pickerState = { active: false };
    window.GORI.pinnedSlot = null;
    const ov = _getPickerOverlay();
    ov.style.display = 'none';
    requestAnimationFrame(() => {
        if (__closeWidgets) { __closeWidgets.forEach(el => el.style.visibility = ''); __closeWidgets = null; }
    });
};

const triggerBroadcast = (slot, node) => {
    if (!slot.gori_active || !slot.gori_channel) return;
    const ch = slot.gori_channel;
    if (_broadcastMap.has(ch)) return;
    const expiry = Date.now() + 15000;
    const timer = setTimeout(() => {
        _broadcastMap.delete(ch);
        if (window.app?.canvas) window.app.canvas.setDirty(true, true);
        console.log(`📡 GoRi Broadcast: ${ch} 방송 종료`);
    }, 15000);
    _broadcastMap.set(ch, { type: slot.type, expiry, timer });
    console.log(`📡 GoRi Broadcast: ${ch} (${slot.type}) 15초간 방송 시작`);
    if (window.app?.canvas) window.app.canvas.setDirty(true, true);
};

export const isBroadcastChannel = (ch) => _broadcastMap.has(ch);
export const consumeBroadcast = (ch) => {
    const entry = _broadcastMap.get(ch);
    if (entry) {
        clearTimeout(entry.timer);
        _broadcastMap.delete(ch);
        if (window.app?.canvas) window.app.canvas.setDirty(true, true);
    }
};
export { showPicker, checkChannelTextClick, closePicker, triggerBroadcast };

export const patchContextMenu = () => {
    if (!LGraphCanvas) { setTimeout(() => patchContextMenu(), 200); return false; }
    if (LGraphCanvas.prototype.__goriContextMenuPatched) return true;

    window.GORI = window.GORI || {};
    window.GORI.hoveredSlot = null;

    const onMouseMove = () => {
        if (!GORI_MENU.state.isActive) { window.GORI.hoveredSlot = null; return; }
        const canvas = window.app?.canvas;
        if (!canvas || !canvas.graph) return;
        const graph = canvas.graph;
        const mx = canvas.graph_mouse[0];
        const my = canvas.graph_mouse[1];
        window.GORI.hoveredSlot = null;
        graph._nodes.forEach(node => {
            if (!node.size || node.flags.collapsed) return;
            const check = (slots, isInput) => {
                if (!slots) return;
                slots.forEach((slot, i) => {
                    if (!slot.gori_channel) return;
                    const sPos = GORI_RENDERER.getSwitchPos(node, slot, isInput, i);
                    if (!sPos) return;
                    const chText = slot.gori_channel || "";
                    const tc = document.createElement('canvas').getContext('2d');
                    tc.font = "italic 10px Arial";
                    const cw = tc.measureText(chText).width || 0;
                    const { gap } = window.GORI.BOX;
                    const hitH = 22;
                    const hitPad = 8;
                    const hitX = isInput ? sPos.localX + gap - hitPad + 0.5 : sPos.localX - gap - cw - hitPad + 0.5;
                    const hitW = cw + hitPad * 2;
                    const hitY = sPos.localY + 1.5 - hitH/2;
                    const ax = node.pos[0] + hitX;
                    const ay = node.pos[1] + hitY;
                    if (mx >= ax && mx <= ax + hitW && my >= ay && my <= ay + hitH) {
                        window.GORI.hoveredSlot = { node, slot, isInput, index: i };
                    }
                });
            };
            check(node.inputs, true);
            check(node.outputs, false);
        });
    };
    const afterMove = () => {
        const canvas = window.app?.canvas;
        if (!canvas) return;
        const h = window.GORI.hoveredSlot;
        const key = h ? `${h.node.id}:${h.isInput ? 'in' : 'out'}:${h.index}` : "";
        if (key !== _prevHoverKey) {
            _prevHoverKey = key;
            canvas.setDirty(true, true);
        }
    };
    const handler = (e) => { onMouseMove(); afterMove(); };
    document.addEventListener('mousemove', handler);

    const originalContextMenu = LGraphCanvas.prototype.processContextMenu;
    LGraphCanvas.prototype.processContextMenu = function(node, e) {
        if (node) {
            const mX = this.graph_mouse[0];
            const mY = this.graph_mouse[1];
            const textHit = checkChannelTextClick(this.graph, mX, mY);
            if (textHit) {
                const oldVal = textHit.slot.gori_channel || "";
                const newVal = prompt("📡 고리 엔진 - 채널 이름 설정:", oldVal);
                if (newVal !== null) {
                    _setNodeCh(textHit.slot, textHit.node, textHit.isInput, textHit.index, newVal.trim());
                    textHit.slot.gori_manual = true;
                    if (textHit.slot.gori_channel !== "") textHit.slot.gori_active = true;
                    textHit.node.setDirtyCanvas(true, true);
                    if (textHit.node.graph) textHit.node.graph._version++;
                }
                return;
            }
            const ps = window.GORI.pickerState;
            if (ps && ps.active && ps.node) {
                const pn = ps.node;
                const { bh } = window.GORI.BOX;
                const pGX = pn.pos[0] + ps.bx;
                const pGY = pn.pos[1] + ps.by + bh + 1;
                const scale = window.GORI.pickerScale || ps.scale || 1.0;
                if (mX >= pGX && mX <= pGX + ps.baseW * scale && mY >= pGY && mY <= pGY + ps.baseH * scale) {
                    const oldVal = ps.slot.gori_channel || "";
                    const newVal = prompt("📡 고리 엔진 - 채널 이름 설정:", oldVal);
                    if (newVal !== null) {
                        _setNodeCh(ps.slot, ps.node, ps.isInput, ps.index, newVal.trim());
                        ps.slot.gori_manual = true;
                        if (ps.slot.gori_channel !== "") ps.slot.gori_active = true;
                        ps.node.setDirtyCanvas(true, true);
                        if (ps.node.graph) ps.node.graph._version++;
                    }
                    return;
                }
            }
        }
        return originalContextMenu.apply(this, arguments);
    };
    window.GORI.drawPicker = function() {};
    window.GORI.updatePickerOverlay = function(cvs) {
        const ps = window.GORI?.pickerState;
        const ov = _getPickerOverlay();
        if (!ps?.active) { ov.style.display = 'none'; return; }
        const { node, bx, by, baseW, baseH, itemH, list, cur, slot, isInput } = ps;
        const liveScale = window.GORI.pickerScale || ps.scale || 1.0;
        const { h: bh } = window.GORI.BOX;
        const gx = node.pos[0] + bx;
        const gy = node.pos[1] + by + bh + 1;
        const va = cvs?.ds?.visible_area;
        const s = cvs?.ds?.scale || 1;
        const canvasEl = cvs?.canvas;
        const rect = canvasEl?.getBoundingClientRect();
        const usedSet = new Set();
        const connSet = new Set();
        const pairedSet = new Set();
        const graph = window.app?.canvas?.graph;
        if (graph) {
            const inChs = new Set(), outChs = new Set();
            graph._nodes.forEach(n => {
                const scan = (slots) => {
                    if (!slots) return;
                    slots.forEach(sl => { if (sl.gori_channel) usedSet.add(sl.gori_channel); });
                };
                scan(n.inputs);
                scan(n.outputs);
                (n.inputs || []).forEach(sl => { if (sl.gori_active && sl.gori_channel) inChs.add(sl.gori_channel); });
                (n.outputs || []).forEach(sl => { if (sl.gori_active && sl.gori_channel) outChs.add(sl.gori_channel); });
                const opposite = isInput ? (n.outputs || []) : (n.inputs || []);
                opposite.forEach(sl => {
                    if (!sl.gori_active || !sl.gori_channel) return;
                    connSet.add(sl.gori_channel);
                });
            });
            inChs.forEach(ch => { if (outChs.has(ch)) pairedSet.add(ch); });
        }
        const isConnected = slot.gori_channel ? connSet.has(slot.gori_channel) : false;
        const now = Date.now();
        const bSet = new Set();
        _broadcastMap.forEach((val, ch) => { if (val.expiry > now) bSet.add(ch); });
        ov.innerHTML = _buildOverlayHTML(list, cur, slot, isConnected, usedSet, connSet, pairedSet, bSet);
        const fontSize = Math.max(8, Math.round(10 * liveScale));
        const displayW = baseW * liveScale;
        if (va && rect) {
            ov.style.left = (gx - va[0]) * s + rect.left + 'px';
            ov.style.top = (gy - va[1]) * s + rect.top + 'px';
        } else {
            ov.style.left = gx + 'px';
            ov.style.top = gy + 'px';
        }
        ov.style.width = (displayW * s) + 'px';
        ov.style.fontSize = (fontSize * s) + 'px';
        ov.style.lineHeight = (itemH * liveScale * s) + 'px';
        ov.style.display = 'block';
        ov.style.maxHeight = '';
        ov.style.overflow = 'hidden';
    };
    LGraphCanvas.prototype.__goriContextMenuPatched = true;
    return true;
};
