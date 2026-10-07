# -*- coding: utf-8 -*-
"""공용 유틸: 로그, 한 번 로그, 파일 로더, 위치."""

from __future__ import annotations

import json
import os
import sys

__all__ = [
"_log", "_note_once", "_load", "HERE", "_ONCE_SEEN"
]


# 왜(Why) realpath인가: macOS/Linux 개발에서는 `custom_nodes/노드폴더`를 개발
# 폴더로 심볼릭 링크하는 것이 흔하다. abspath는 링크 경로를 그대로 쓰므로
# keywords_ko_en.json·presets.json을 못 찾아 내장 기본값으로 조용히 떨어진다
# (사용자에게는 "설정이 안 먹힌 것처럼" 보인다). realpath는 링크를 따라간다.
HERE = os.path.dirname(os.path.realpath(__file__))


def _log(msg: str) -> None:
    """Windows(cp949 등) 콘솔에서도 인코딩 오류로 노드가 죽지 않게 한다."""
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        print(msg.encode(enc, "replace").decode(enc, errors="replace"),
              flush=True)


_ONCE_SEEN = set()


def _note_once(key: str, msg: str) -> None:
    """같은 키의 메시지를 **한 번만** 말한다.

    왜(Why) 조용한 실패에 로그를 붙이면서도 스팸을 피하는가 (2026-10-01):
    `except Exception: return None` 이 이 파일에 **45곳** 있다. 전부 로그를
    남기면 사용자가 읽을 수 없다 — 그래서 "그냥 한 번" 이 정답이다.
    키퍼의 `_note_once` 와 같은 계약이며, 그쪽이 먼저 있었다.

    왜(Why) 조용한 실패가 문제인가: numpy 부재도 `except Exception` 에 걸려
    "시트 아님" 이 되고, 그 결과 시트 참조가 **조용히 withheld** 된다
    (2026-10-01 실측: 카메라 노드가 한 장짜리 사진을 시트로 오판해 기준
    latent 를 의도적으로 뺐고, 키퍼는 "camera 기준 없음" 으로 죽었다).
    """
    if key in _ONCE_SEEN:
        return
    _ONCE_SEEN.add(key)
    _log(msg)


def _load(name: str, fallback):
    try:
        with open(os.path.join(HERE, name), encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as e:  # 파일 손상/누락에도 노드는 뜨게 한다
        _log(f"[Camera Director] {name} 로드 실패: {e} → 내장 기본값 사용")
        return fallback
