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

export const patchAltDragMultiClone = () => {
    const canvas = window.app?.canvas;
    if (!canvas) return false;
    if (canvas.__goriPDMultiPatched) return true;

    if (!window.GORI._pdCaptureDone) {
        window.GORI._pdCaptureDone = true;

        document.addEventListener('pointerdown', (e) => {
            window.GORI._altDragActive = false;
            window.GORI._altDragSingle = false;
            window.GORI._altDragBeforeIds = null;
            const altDown = e.altKey || e.getModifierState?.('Alt') || false;
            if (!altDown) return;
            if (!window.app?.canvas?.graph) return;
            const c = window.app.canvas;
            if (typeof c.adjustMouseEvent === 'function') c.adjustMouseEvent(e);
            let cx = e.canvasX, cy = e.canvasY;
            if (cx == null) {
                const rect = c.canvas?.getBoundingClientRect?.();
                if (rect) { cx = e.clientX - rect.left; cy = e.clientY - rect.top; }
            }
            const node = c.graph?.getNodeOnPos(cx, cy);
            if (!node || !c.selected_nodes) return;
            const isMap = c.selected_nodes instanceof Map;
            const inSel = isMap ? c.selected_nodes.has(node.id) : !!c.selected_nodes[node.id];

            // capture phase에서는 클릭한 노드가 아직 selected_nodes에 없을 수 있음
            if (!inSel) {
                window.GORI._altDragIntCh = new Map();
                window.GORI._altDragCloneMap = new Map();
                window.GORI._altDragIds = new Set();
                window.GORI._altDragActive = true;
                window.GORI._altDragSingle = true;
                return;
            }

            const allSelected = (isMap ? [...c.selected_nodes.values()] : Object.values(c.selected_nodes)).filter(n => n && n.id != null);
            const otherNodes = allSelected.filter(n => n.id !== node.id);

            const gr = c.graph;
            const allSel = [node, ...otherNodes];

            const intCh = new Map();
            for (const src of allSel) {
                if (!src.outputs) continue;
                for (const out of src.outputs) {
                    if (!out.gori_active || !out.gori_channel) continue;
                    for (const tgt of allSel) {
                        if (tgt === src || !tgt.inputs) continue;
                        if (tgt.inputs.some(inp => inp.gori_active && inp.gori_channel === out.gori_channel)) {
                            if (!intCh.has(out.gori_channel)) {
                                intCh.set(out.gori_channel, `ALT_${Date.now().toString(36)}_${intCh.size}`);
                            }
                        }
                    }
                }
            }

            window.GORI._altDragIntCh = intCh;
            window.GORI._altDragCloneMap = new Map();
            window.GORI._altDragIds = new Set();
            window.GORI._altDragActive = true;
            window.GORI._altDragSingle = (allSelected.length === 1);

            // 다른 선택 노드들만 클론 (clicked 노드는 LiteGraph가 처리)
            const cloneMap = new Map();
            for (const orig of otherNodes) {
                try {
                    const clone = orig.clone();
                    if (clone) {
                        clone.id = null;
                        gr.add(clone);
                        window.GORI._altDragIds.add(clone.id);
                        cloneMap.set(orig.id, clone);
                    }
                } catch (er) { console.error('🐛 altDrag clone err:', er); }
            }
            if (!cloneMap.size) return;

            if (isMap) {
                otherNodes.forEach(n => c.selected_nodes.delete(n.id));
                cloneMap.forEach(cl => c.selected_nodes.set(cl.id, cl));
            } else {
                otherNodes.forEach(n => delete c.selected_nodes[n.id]);
                cloneMap.forEach(cl => c.selected_nodes[cl.id] = cl);
            }

            window.GORI._altDragCloneList = [...cloneMap.values()];
            window.GORI._altDragClickNode = node;
            window.GORI._altDragBeforeIds = new Set(gr._nodes.map(n => n.id));
            window.GORI._altDragOrigPos = [node.pos[0], node.pos[1]];
        }, true);

        document.addEventListener('pointerup', () => {
            window.GORI._altDragActive = false;
            window.GORI._altDragCloneList = null;
            window.GORI._altDragClickNode = null;
            window.GORI._altDragBeforeIds = null;
            window.GORI._altDragOrigPos = null;
            window.GORI._altDragLastPos = null;
            if (window.GORI._altDragIntCh instanceof Map) window.GORI._altDragIntCh.clear();
            if (window.GORI._altDragIds instanceof Set) window.GORI._altDragIds.clear();
            if (window.GORI._altDragCloneMap instanceof Map) window.GORI._altDragCloneMap.clear();
            window.GORI._altDragIntCh = null;
            window.GORI._altDragIds = null;
            window.GORI._altDragCloneMap = null;
            window.GORI._altDragSingle = false;
        }, true);
    }

    if (!window.GORI._altDragSyncReg) {
        window.GORI._altDragSyncReg = true;
        const sync = () => {
            requestAnimationFrame(sync);
            const clones = window.GORI._altDragCloneList;
            if (!clones?.length || !window.GORI._altDragActive) return;
            const gr = window.app?.canvas?.graph;
            const cn = window.GORI._altDragClickNode;
            if (!gr || !cn) return;
            const beforeIds = window.GORI._altDragBeforeIds;
            if (!beforeIds) return;
            const clicked = gr._nodes.find(n => !beforeIds.has(n.id) && n.type === cn.type);
            if (!clicked) return;
            if (!window.GORI._altDragLastPos) {
                const origPos = window.GORI._altDragOrigPos;
                if (origPos) {
                    const initDx = clicked.pos[0] - origPos[0];
                    const initDy = clicked.pos[1] - origPos[1];
                    if (initDx || initDy) {
                        for (const c of clones) {
                            c.pos[0] += initDx;
                            c.pos[1] += initDy;
                        }
                    }
                }
                window.GORI._altDragLastPos = [clicked.pos[0], clicked.pos[1]];
                return;
            }
            const dx = clicked.pos[0] - window.GORI._altDragLastPos[0];
            const dy = clicked.pos[1] - window.GORI._altDragLastPos[1];
            if (dx || dy) {
                for (const c of clones) {
                    c.pos[0] += dx;
                    c.pos[1] += dy;
                }
            }
            window.GORI._altDragLastPos = [clicked.pos[0], clicked.pos[1]];
        };
        requestAnimationFrame(sync);
    }

    canvas.__goriPDMultiPatched = true;
    return true;
};
