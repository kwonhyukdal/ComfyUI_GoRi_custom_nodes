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
 * [Part 1] gori_config.js
 * 역할: 중복 기능 노드(Set/Get, Anything Everywhere) 차단
 */

// GORI 전역 상태 저장소 - window 오염 방지 (단 하나의 window 변수만 사용)
window.GORI = window.GORI || {};

export const GORI_CONFIG = {
    // 1. 제외할 노드 명칭 리스트
    EXCLUDED_EXACT: [
        "GetNode", 
        "SetNode", 
        "Reroute", 
        "ReroutePrimitive",
        // Anything Everywhere 시리즈 추가
        "Anything Everywhere",
        "Anything Everywhere?",
        "Anything Everywhere3",
        "Seed Everywhere",
        "Prompts Everywhere"
    ],

    isExcluded: function(nodeData) {
        if (!nodeData) return false;

        const type = (nodeData.type || "").toString();
        const name = (nodeData.name || "").toString();
        
        // 2. 정확한 이름 매칭으로 차단
        if (this.EXCLUDED_EXACT.includes(type) || this.EXCLUDED_EXACT.includes(name)) {
            return true;
        }

        // 3. 키워드 매칭 (혹시 모를 변종 Anything Everywhere 노드들까지 방어)
        if (type.includes("Everywhere") || name.includes("Everywhere")) {
            return true;
        }

        return false; // 나머지는 활짝 개방!
    }
};