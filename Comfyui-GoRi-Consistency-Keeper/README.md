# 🛡️ (GoRi) Consistency Keeper

> 🌐 [English version](README.en.md)
>
> ☕ 도움이 됐다면 커피 한 잔: [PayPal로 후원하기](https://paypal.me/GoRi57788)

샘플러가 뽑은 latent를 원본·카메라 기준 latent 쪽으로 당겨
신원·구도 틀어짐을 줄이는 2차 패스 노드. **다시 그리지 않는다**
(재인코딩·재샘플링 없음).

## 배선

```text
LoadImage → VAE Encode ── original_latent ──→ ┐
(GoRi) Camera Director Skills ── reference_latent_out ── camera_latent ──→ (GoRi) Consistency Keeper ── latent_out ──→ VAE Decode → SaveImage
KSampler ── LATENT ── sampled_latent ──→ ┘
같은 VAE ── vae ──→ ┘ (손 마스크용, 선택. 미연결이면 전역 당김)
```

## 위젯

| 위젯 | 기본값 | 설명 |
|---|---|---|
| `strength_camera` | 0.2 | 연출 방향 당김 (카메라 기준, -1.0~1.0) |
| `strength_original` | 0.2 | 원본 신원 당김 (-1.0~1.0) |

음수는 **안티-레퍼런스** (닮음 밀어내기). 틀어짐이 크면 노드가 스스로
당김을 감쇠시킨다 ("융합하되 변형 없이" — 콘솔에 감쇠 알림).
조명 흐름이 다르면(Retinex 근사: 저주파 명암 비교) 추가로 감쇠된다.

## 인체 마스크 가중 당김 (선택)

`vae`를 연결하면 인체 영역만 골라 당긴다 (MediaPipe 포즈 분할 마스크 —
미설치면 조용히 전역 당김으로 동작, 별도 설정 없음). 배경은 그대로 두고
신체 전체를 커버한다. 손가락 개수 자체는 고치지 못한다 (디테일러 영역).

0이면 해당 기준 생략. 기준 latent 미연결·크기 불일치(배치·채널)도 건너뛰고
콘솔에 알린다. 공간 크기가 다르면 bicubic 리사이즈로 맞춘다.

## 세팅 가이드

기본값(`strength_camera` 0.2 / `strength_original` 0.2) 그대로 시작.

| 증상 | 조절 |
|---|---|
| 얼굴이 원본과 다름 | `original`을 0.5~0.6으로 올림 |
| 구도·조명이 샘플러 멋대로 | `camera`를 0.5~0.6으로 올림 |
| 눌어붙은 느낌·밋밋함 | 둘 다 0.15~0.2로 내림 (과다 당김) |
| 기준 하나만 쓸 때 | 안 쓰는 쪽 0 또는 미연결 |

한 번에 하나씩 0.1 단위로 조절 (둘 다 올리면 과해짐). 연산이 가벼워
VRAM·속도 부담은 없음.

## 겹쳐보임(고스트) 대처

얼굴·몸이 이중으로 겹쳐 보이면 기준 latent와 결과물 구도가 다른 것이다.
latent 블렌드는 같은 구도에서만 성립한다:

1. 기준 이미지를 결과물과 같은 구도·포즈로 맞춘다 (가장 확실)
2. 강도를 0.1~0.15까지 낮춘다
3. 콘솔에 "구도가 많이 다름" 경고가 뜨면 위 둘 중 하나 실행

## 한계

- 일관성 당김 전용. 손가락 6개 같은 파손을 다시 그려주진 못한다
  (그건 FaceDetailer 같은 디테일러 영역).
- 검증: `python tests/test_node.py`

## 라이선스

MIT. 방법론 참고: PuLID 논문(Apache 2.0), 내장 LatentBlend.
코드 복제 없음 — 직접 구현.
