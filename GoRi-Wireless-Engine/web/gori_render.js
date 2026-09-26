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

/* 
 * [Part 2] gori_render.js
 * 역할: 스위치 위치 계산, 베지어 곡선 렌더링 및 시각적 인덱스(#001) 배지 표시
 * 수정 사항: 직접 수치 조절이 가능하도록 상세 한글 주석 및 가이드 추가
 */

import { GORI_MENU } from "./gori_menu.js";

export const GORI_RENDERER = {
    _tempCtx: document.createElement('canvas').getContext('2d'),

    // 노드 우측 상단에 고리 인덱스 배지를 그리는 함수
    drawIndexBadge: function(ctx, node) {
        const hasOrder = node.gori_selection_order !== undefined;
        const hasIndex = node.gori_index !== undefined;
        if ((!hasOrder && !hasIndex) || node.flags.collapsed) return;

        const indexText = hasOrder
            ? String(node.gori_selection_order)
            : `GR-${String(node.gori_index).padStart(3, '0')}`;

        ctx.save();

        // --- [수치 조절 가이드 영역] ---

        // 1. 폰트 크기 및 스타일
        ctx.font = "bold 14px sans-serif";
        const textWidth = ctx.measureText(indexText).width;

        // 2. 배지 상자의 크기 (Width: 가로, Height: 세로)
        const badgeWidth = textWidth + 10;  // 10: 좌우 패딩 합계
        const badgeHeight = 21;             // 💡 조절: 이 값을 키우면 하단 여백이 늘어납니다

        // 3. 배지의 전체 위치 (X: 가로 좌표, Y: 세로 좌표)
        const posX = node.size[0] - badgeWidth - 5; // 5: 오른쪽 끝에서의 이격 거리
        const posY = -LiteGraph.NODE_TITLE_HEIGHT + 4.5;

        // ------------------------------

        ctx.beginPath();
        this.roundRect(ctx, posX, posY, badgeWidth, badgeHeight, 3);

        if (hasOrder) {
            // ★ 시퀀스 모드: 보라색 배지 + 흰 테두리 + 검정 숫자
            ctx.fillStyle = "rgba(188, 149, 255, 1.0)";
            ctx.fill();
            ctx.strokeStyle = "#ffffff";
            ctx.lineWidth = 0.8;
            ctx.stroke();
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.fillStyle = "#000000";
            ctx.fillText(indexText, posX + badgeWidth / 2, posY + (badgeHeight / 2) - 0.6);
        } else {
            // 기본 모드: 검정 배지 + 초록 테두리 + 흰색 GR-###
            ctx.fillStyle = "rgba(0, 0, 0, 0.75)";
            ctx.fill();
            ctx.strokeStyle = "#00ff88";
            ctx.lineWidth = 0.8;
            ctx.stroke();
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.fillStyle = "#ffffff";
            ctx.fillText(indexText, posX + badgeWidth / 2, posY + (badgeHeight / 2) - 0.6);
        }

        ctx.restore();
    },

    // 라운드 사각형 헬퍼 함수
    roundRect: function(ctx, x, y, w, h, r) {
        if (w < 2 * r) r = w / 2;
        if (h < 2 * r) r = h / 2;
        ctx.beginPath();
        ctx.moveTo(x + r, y);
        ctx.arcTo(x + w, y, x + w, y + h, r);
        ctx.arcTo(x + w, y + h, x, y + h, r);
        ctx.arcTo(x, y + h, x, y, r);
        ctx.arcTo(x, y, x + w, y, r);
        ctx.closePath();
    },

    // 스위치 버튼의 위치를 계산하는 함수
    getSwitchPos: function(node, slot, isInput, index) {
        const slotPos = node.getConnectionPos(isInput, index);
        const label = slot.label || slot.name || "";
        
        this._tempCtx.font = "bold 12px Arial";
        const tw = this._tempCtx.measureText(label).width || 35;
        
        const sx = isInput ? 15 + tw + 15 : node.size[0] - 15 - tw - 15;
        return { 
            x: node.pos[0] + sx, 
            y: slotPos[1], 
            localX: sx, 
            localY: slotPos[1] - node.pos[1] 
        };
    },
// 실제 선과 버튼을 그리는 함수
    drawVisuals: function(ctx, node, app) {
        if (!node.size || node.flags.collapsed) return;

        // 인덱스 배지 표시 토글 상태일 때만 표시
        if (GORI_MENU.state.showIndexBadge) {
            this.drawIndexBadge(ctx, node);
        }

        const isMainNode = app.canvas.node_over === node || !!app.canvas.selected_nodes[node.id];

        const drawGroup = (slots, isInput) => {
            if (!slots) return;
            slots.forEach((slot, i) => {
                if (isInput && slot.widget) {
                    if (slot.gori_active && slot.gori_channel && GORI_MENU.state.isActive) {
                        const cp = node.getConnectionPos(isInput, i);
                        const lx = cp[0] - node.pos[0];
                        const ly = cp[1] - node.pos[1];
                        // 연결된 출력 포트의 색상 찾기
                        let slotColor = "#ffff00";
                        (app.graph?._nodes || []).forEach(n => {
                            if (n === node || !n.outputs) return;
                            n.outputs.forEach(o => {
                                if (o.gori_active && o.gori_channel === slot.gori_channel) {
                                    slotColor = o.color || LGraphCanvas.link_type_colors[o.type] || "#ffff00";
                                }
                            });
                        });
                        ctx.beginPath();
                        ctx.arc(lx, ly, 5, 0, Math.PI * 2);
                        ctx.fillStyle = slotColor;
                        ctx.fill();
                        // widget 입력도 연결선 표시
                        this.drawConnections(ctx, node, slot, isInput, i, slotColor, isMainNode, app);
                    }
                    return;
                }
                
                const sPos = this.getSwitchPos(node, slot, isInput, i);
                const slotColor = slot.color || LGraphCanvas.link_type_colors[slot.type] || (isInput ? "#ffff00" : "#00ff00");

                // 엔진 활성 상태일 때만 연결선 렌더링
                if (slot.gori_active && slot.gori_channel && GORI_MENU.state.isActive) {
                    this.drawConnections(ctx, node, slot, isInput, i, slotColor, isMainNode, app);
                }

                if (slot.gori_channel && GORI_MENU.state.isActive) {
                    ctx.save();
                    ctx.fillStyle = slot.gori_active ? "rgba(255,255,255,0.9)" : "rgba(180,180,180,0.8)";
                    ctx.font = "italic 10px Arial";
                    const textWidth = ctx.measureText(slot.gori_channel).width;
                    const textX = isInput ? sPos.localX + 12 : sPos.localX - textWidth - 12;
                    ctx.fillText(slot.gori_channel, textX, sPos.localY + 5);
                    ctx.restore();
                }
                if (slot.gori_active && GORI_MENU.state.isActive) {
                    const dotX = isInput ? sPos.localX - 3 : sPos.localX + 3;
                    ctx.beginPath();
                    ctx.arc(dotX, sPos.localY + 1, 5, 0, Math.PI * 2);
                    ctx.fillStyle = slotColor;
                    ctx.fill();
                }
            });
        };

        drawGroup(node.inputs, true);
        drawGroup(node.outputs, false);
    },

    // 연결선(베지어 곡선) 상세 로직
    drawConnections: function(ctx, node, slot, isInput, i, slotColor, isMainNode, app) {
        let partners = [];
        app.graph._nodes.forEach(n => {
            if (node === n) return;
            const ts = isInput ? n.outputs : n.inputs;
            ts?.forEach((t, ti) => {
                if (t.gori_active && t.gori_channel === slot.gori_channel) {
                    partners.push(n.getConnectionPos(!isInput, ti));
                }
            });
        });

        if (partners.length > 0) {
            const rs = node.getConnectionPos(isInput, i);
            
            // 소켓 부분에 강조 점 그리기
            ctx.save();
            ctx.beginPath();
            ctx.arc(rs[0]-node.pos[0], rs[1]-node.pos[1], 6, 0, Math.PI*2);
            ctx.fillStyle = slotColor; 
            ctx.globalAlpha = 0.8; 
            ctx.fill();
            ctx.restore();

            // 선택된 노드일 때만 베지어 곡선 연결선 표시
            if (isMainNode) {
                partners.forEach(p => {
                    ctx.save();
                    const x1 = rs[0]-node.pos[0], y1 = rs[1]-node.pos[1];
                    const x2 = p[0]-node.pos[0], y2 = p[1]-node.pos[1];
                    const cp = Math.min(Math.abs(x2-x1)*0.5, 150);
                    
                    ctx.beginPath(); 
                    ctx.lineWidth = 3; 
                    ctx.strokeStyle = slotColor; 
                    ctx.globalAlpha = 0.5; 
                    
                    ctx.moveTo(x1, y1);
                    ctx.bezierCurveTo(
                        x1 + (isInput ? -cp : cp), y1, 
                        x2 + (isInput ? cp : -cp), y2, 
                        x2, y2
                    );
                    ctx.stroke(); 
                    ctx.restore();
                });
            }
        }
    }
};