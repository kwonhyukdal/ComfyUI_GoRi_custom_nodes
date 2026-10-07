# -*- coding: utf-8 -*-
"""VAE 축소 비율 학습·인코딩/디코딩·캐시."""

from __future__ import annotations

try:
    from .kp_math import *  # noqa: F403
    from .kp_math import _note_once  # __all__ 밖 — 명시 임포트가 필요하다
except ImportError:  # 스탠드얼론/테스트 실행용
    from kp_math import *  # noqa: F403
    from kp_math import _note_once


__all__ = [
"_VAE_PIXEL_FACTOR_FALLBACK", "_VAE_FACTOR_BY_CLASS", "_vae_factor_key", "_vae_pixel_factor_for", "_vae_pixel_factor_learn", "_encode_image_ref", "_decode_capped", "_latent_cache_key", "_decode_small", "_release_vram"
]


def _release_vram() -> None:
    """GPU 조각 반납. 마스크용 VAE 디코드 잔재 정리 (실패 무시).

    왜(Why) MPS도 같이 비우는가: macOS(M1/M2/M3)는 CUDA가 아니라 MPS 메모리
    파서를 쓴다. cuda만 비우면 맥에서는 아무것도 하지 않으므로, 이 노드가
    디코드한 잔재가 통합 캐시에 남는다. hasattr 가드로 없는 환경도 안전.
    왜(Why) gc.collect(0) 인가 (2026-10-02 실측, 카메라와 동일):
    풀 collect 는 106ms·수집 0개. gen 0은 0.5ms.
    """
    try:
        import gc as _gc
        _gc.collect(0)
        try:
            import torch as _t
            if hasattr(_t, "cuda") and _t.cuda.is_available():
                _t.cuda.empty_cache()
            mps = getattr(_t, "mps", None)
            if mps is not None and hasattr(mps, "empty_cache"):
                try:
                    if mps.is_available():
                        mps.empty_cache()
                except Exception:
                    pass
        except Exception:
            pass
    except Exception:
        pass




# VAE 가 latent 1칸을 몇 픽셀 이미지로 복원하는지 못 알아낼 때의 임시값.
# **8 은 SD 계열 기준이고 Qwen 은 16 이다.** 실패했을 때만 쓰는 안전망이며
# 정상 경로에서는 쓰이지 않는다.
_VAE_PIXEL_FACTOR_FALLBACK = 8


# VAE 의 "latent 1칸 = 이미지 몇 픽셀" 을 기억하는 **보조 맵**이다.
# production 은 `_vae_pixel_factor_for` 의 `spacial_compression_decode()`
# 경로가 1순위라 이 맵을 지나지 않는다 — 메서드가 없는 테스트 가짜 전용.
# **프로브로 재지 않는다** — 2026-10-01 실측으로 프로브는 사치다:
# 6.9GB 모델이 VRAM 에 오른 상태에서 128/256/512 인코딩을 시도하면 ms 가
# 아니라 초 단위가 걸렸고, 그 여파로 하네스 폴링이 타임아웃났다.
# 실제 디코드를 **이미 하고 있으니** 거기서 비율을 읽으면 공짜다.
# 왜(Why) 키가 클래스인가: `id()` 는 GC 뒤 주소를 재사용하므로 쓰면
# 엉뚱한 VAE 의 배율이 나온다(실측 50회 중 35회 재사용). 단, production
# VAE 는 전부 한 클래스라(nodes.py:862) 이 키는 아키텍처를 구분하지
# 못한다 — 그래서 아래 spacial 경로가 1순위가 되었다.
_VAE_FACTOR_BY_CLASS = {}


def _vae_factor_key(vae):
    """VAE 를 구조적으로 구분하는 키.

    왜(Why) 이 키가 이제는 **가짜 VAE 전용**인가 (2026-10-04 감사
    실측): production VAE 는 전부 `comfy.sd.VAE` 한 클래스라
    (nodes.py:862) 이 키로 Wan 과 Qwen 을 구분할 수 없다 — 슬롯이
    하나라 배율이 서로 새어 오염된다. production 은
    `_vae_pixel_factor_for` 의 `spacial_compression_decode()` 경로가
    1순위라 이 키를 지나지 않는다. 메서드가 없는 테스트 가짜를 위한
    안전망으로만 남긴다.

    왜(Why) `id()` 가 아니라 클래스인가: `id()` 는 주소 재사용 때문에
    위험하다 (Jev 게이트가 명시적으로 금지).
    """
    t = type(vae)
    return (getattr(t, "__module__", ""),
            getattr(t, "__qualname__", None) or getattr(t, "__name__", "?"))


def _vae_pixel_factor_for(vae) -> int:
    """이 VAE 의 배율. VAE 가 스스로 아는 값이면 그것을 쓴다.

    왜(Why) 1순위가 `spacial_compression_decode` 인가 (2026-10-04
    감사 실측): production 의 VAE 는 전부 `comfy.sd.VAE` 한
    클래스라(nodes.py:862) 클래스 키로 Wan 과 Qwen 을 구분할 수
    없다. 아키텍처 배율(8/16/…)은 VAE 가 자기 메서드로 이미
    들고 있다. 학습 맵은 이 메서드가 없는 가짜 VAE (테스트) 전용
    안전망이다.
    """
    if vae is None:
        return _VAE_PIXEL_FACTOR_FALLBACK
    try:
        _f = vae.spacial_compression_decode()
        if isinstance(_f, (int, float)) and 1 <= _f <= 64:
            return int(_f)
    except Exception:
        pass
    try:
        return _VAE_FACTOR_BY_CLASS.get(_vae_factor_key(vae),
                                        _VAE_PIXEL_FACTOR_FALLBACK)
    except Exception:
        return _VAE_PIXEL_FACTOR_FALLBACK


def _vae_pixel_factor_learn(vae, latent, decoded) -> int:
    """디코드 결과로 축소 비율을 배운다. 값을 돌려준다.

    production 은 호출 전 이미 `spacial_compression_decode` 로 정확한
    값을 가졌으므로 이 learn 은 가짜 VAE (메서드 없음) 전용이다.

    왜(Why) 별도 프로브가 아닌가: 위 주석 — 프로브는 비싸고, 디코드는 이미
    하고 있다. `decoded` 의 높이가 latent 높이의 몇 배인지만 보면 끝이다.

    왜(Why) 실패해도 조용히 두는가: 실패해도 이전 값(안전망 또는
    spacial 이 준 값)이 그대로 남는다 — 새로 나빠지는 것이 아니다.
    배율은 최적화 파라미터라 틀어도 **결과물의 정확성**을 해치지 않고 속도만
    달라진다.
    """
    try:
        if vae is None or latent is None or decoded is None:
            return _vae_pixel_factor_for(vae)
        lh = int(latent.shape[-2])
        # 왜(Why) 축을 채널로 고르나 (2026-10-04 감사 실측):
        # production decoded 는 BHWC 다 (comfy.sd.VAE.decode 의
        # movedim(1,-1), sd.py:1347). 그때 shape[-2] 는 W 이라
        # W_img / H_lat 을 배율로 배우게 된다 — 비정사각에서 틀리고
        # 정사각에서만 우연히 맞는다. 테스트 가짜는 BCHW 라
        # shape[-2] 가 H 인 반대 상황이라 검사가 통과해 못 찾았다.
        # 마지막 축이 1/3/4 면 채널이 마지막(BHWC)이므로 H 는 [-3],
        # 아니면 BCHW 이므로 H 는 [-2].
        _sh = getattr(decoded, "shape", None)
        if _sh is None or len(_sh) != 4:
            return _vae_pixel_factor_for(vae)
        ih = int(_sh[-3]) if int(_sh[-1]) in (1, 3, 4) else int(_sh[-2])
        if lh > 0 and ih > 0 and ih % lh == 0:
            f = ih // lh
            if 1 <= f <= 64:
                _VAE_FACTOR_BY_CLASS[_vae_factor_key(vae)] = f
    except Exception:
        pass
    return _vae_pixel_factor_for(vae)


def _encode_image_ref(vae, image):
    """IMAGE 텐서 -> 원본 기준 latent. 실패하면 None.

    왜(Why) 이 함수가 필요한가 (2026-10-01 실측으로 확정):
    `TextEncodeQwenImage21` 의 `latent` 출력은 **전부 0 인 빈 캔버스**다
    (`comfy_extras/nodes_qwen.py:181`). Qwen Edit 에는 "원본 latent" 라는
    개념이 없고, 원본은 `positive`/`negative` 컨디셔닝 안의
    `reference_latents` 로 들어간다(같은 파일 179행).

    즉 워크플로가 Latent 형식으로 넘겨주는 원본에는 **내용이 없다.** 그 상태로
    `MSE(생성결과, 전부 0)` 을 계산했으므로 로그에
    `original 틀어짐 MSE=14.06` 처럼 나오던 숫자는 **무의미했다.**
    게다가 정규화 값이 분모 0 으로 `n/a` 였는데, 그것이 결정적 단서였다.

    → 원본을 **이미지**로 받고 여기서 직접 인코딩한다. 이 노드는 이미 latent 를
    디코드하므로 vae 를 갖고 있고, 대칭적으로 인코딩도 할 수 있다.

    why(why): we do not resize. measured 2026-10-01: resizing to the sampled
    grid needs a factor we do not know on the first pass (fallback 8, Qwen is
    16) and produced an invalid 416x632 -> 'Calculated padded input size per
    channel: (1 x 625)'. The workflow already hands us the original resized to
    the canvas, so encoding as-is lets the VAE pick the grid. That removes the
    need to know the factor and removes the wrong-size path entirely.

    왜(Why) ComfyUI 의 VAEEncode 와 같은 순서인가: `movedim(-1, 1)` 로
    (B,H,W,C) 를 (B,C,H,W) 로 옮기고 앞 3채널만 쓴다. ComfyUI 고유 규약이라
    순서를 바꾸면 VAE 가 조용히 이상한 값을 낸다.

    크기가 비교 기준과 다르면 `_match_spatial` 이 보간으로 맞춰 준다. 그러면
    기준 자체가 리샘플된 값이 되어 "얼마나 다른가" 에 리샘플 차이가 섞이지만,
    **배율을 모른 채로 틀린 크기로 인코딩하는 것**(실측: 1x625 오류)보다
    확실히 낫다. 이 절차를 되돌리지 말 것.
    """
    if vae is None or image is None:
        return None
    try:
        import torch as _t
        # 왜(Why) 전치하지 않는가 (2026-10-01 실측): ComfyUI 의 `VAE.encode` 는
        # **(B,H,W,C) 를 받는다.** 내부에서 크롭을 하고 나서 전치한다:
        #     def encode(self, pixel_samples):        # ← (B,H,W,C)
        #         pixel_samples = self.vae_encode_crop_pixels(pixel_samples)
        #         pixel_samples = pixel_samples.movedim(-1, 1)     # 여기서 전치
        # 원래 `VAEEncode` 노드도 `vae.encode(pixels)` 로 그대로
        # 넘긴다. 내가 미리 `movedim(-1, 1)` 하면 **전치가 두 번** 되고,
        # ComfyUI 는 dims 를 (3, 1544, ...) 로 읽어 크롭까지 망가뜨린다
        # (실측: "Calculated padded input size per channel: (1 x 1601)").
        # 주석에 "전치해야 한다"고 적어둔 것이 정확히 반대였다.
        px = image[..., :3]
        if px.dtype != _t.float32:
            px = px.to(dtype=_t.float32)
        # 큰 텐서를 굳이 CPU 에 만들지 않는다 — 대상 장치에서 직접 만든다.
        px = px.to(device=getattr(vae, "device", None) or px.device)
        # 크기 정리는 `vae_encode_crop_pixels` 가 **spacial_compression_encode()
        # (=16) 배수로 중앙 크롭** 한다. 내가 추가로 맞추지 않는다 —
        # 여기서 리사이즈하면 내용이 바뀌고, 크롭이 하는 일만 헛돌게 된다.
        lat = vae.encode(px)
        del px
        _release_vram()
        return lat
    except Exception as _ie:
        # 왜(Why) 로그를 여기 남기지 않나 (2026-10-04 감사 52차): 유일한
        # 호출부(run 의 original_image 분기)가 실패 시 "인코딩 실패 —
        # original_latent 경로로 진행합니다" 를 항상 남긴다. 여기서 또
        # 남기면 한 실패에 경고 2개가 찍힌다.
        # 갱신 (2026-10-07 감사): 호출부의 경고는 **원인을 모른다** — 원인
        # 한 줄은 중복이 아니라 보완이다. 프로세스당 한 번만 말한다.
        _note_once("encode_image_ref",
                   "[GoRi Consistency Keeper] ⚠ original_image 인코딩 예외 "
                   "(%s: %s)" % (type(_ie).__name__, str(_ie)[:80]))
        _release_vram()
        return None


def _decode_capped(vae, latent, max_pixels=None):
    """VAE 디코드 — 픽셀 수가 상한을 넘으면 latent 를 먼저 줄인다.

    카메라 노드와 같은 규율(`QWEN_REF_MAX_PIXELS`). latent 축은 줄이되 종횡비는
    유지한다(면적 보간이라 비율이 어느 축이든 유지된다). 실패하면 원본 그대로
    디코드한다 — 상한은 최적화이지 동작 조건이 아니다.
    """
    try:
        import torch.nn.functional as _f
        h = int(latent.shape[-2])
        w = int(latent.shape[-1])
        # 왜(Why) 더 이상 8 을 박지 않는가 (2026-10-01): 이 8 은 SD 계열
        # 기준이고 Qwen 은 16 이다. 그 차이로 픽셀 상한이 **4배 느슨하게**
        # 동작했다 — 즉 상한이 있어도 실제로는 상한을 못 넘는다.
        # 값은 `_vae_pixel_factor_for` 가 준다 — production VAE 는
        # 자기 메서드(spacial_compression_decode)로 **첫 호출부터**
        # 정확하다. 이전 디코드에서 배우는 경로는 가짜 VAE 전용이다.
        _fac = _vae_pixel_factor_for(vae)
        px = float(max(1, h) * max(1, w) * _fac * _fac)
        cap = _DECODE_MAX_PIXELS if max_pixels is None else int(max_pixels)
        if px <= cap:
            img = vae.decode(latent)
            # 왜(Why) 결과를 버리지 않는가: `_vae_pixel_factor_learn` 은
            # 배율을 돌려주는데, 그 값을 그대로 반환하면 디코드된 이미지가
            # 숫자로 바뀌고 디코딩이 조용히 무력화된다(실측: 마스크·캐시·
            # 디코드 검사 8건이 한꺼번에 깨졌다). 배율은 부수 효과이므로 버린다.
            _vae_pixel_factor_learn(vae, latent, img)
            return img
        scale = (cap / px) ** 0.5
        nh = max(8, int(h * scale))
        nw = max(8, int(w * scale))
        small = _f.interpolate(latent.float(), size=(nh, nw), mode="area")
        img = vae.decode(small)
        # 배율은 축소 전/후 어느 격자에서 읽어도 같다 — 둘 다 같은 비율이다.
        _vae_pixel_factor_learn(vae, small, img)
        del small
        _release_vram()
        return img
    except Exception:
        # 왜(Why) release 후 재시도인가 (2026-10-04 감사): 위 경로가
        # OOM 으로 죽었다면 VRAM 이 아직 차 있다 — 그 상태로 4배 큰
        # 전 해상도 디코드를 바로 시도하면 두 번째 OOM 이 난다.
        _release_vram()
        # 왜(Why) 이 fallback 을 지키나 (2026-10-04 감사 4차):
        # "축소를 안 탔으면 같은 부르기 재시도는 보장 실패" 라고
        # raise 로 고쳤다가 실측으로 되돌렸다. 예외는 shape 접근·learn
        # 등 decode **전후** 어디서나 나는데, 이 fallback 은 그 복구
        # 경로다 — 실측(2026-10-04 감사 6차): raise 로 바꾸면
        # `tests/verify_cache_full.py` 의 "키가 없어도 디코드는
        # 수행된다" 1건만 실패하고, 그 입력은 `T.ones(4)` **1차원**
        # 이다(2차원은 shape[-2] 가 안 터진다). 중복 부르기의 비용은
        # 1회 decode 뿐이고 그조차 성공할 수 있다.
        return vae.decode(latent)


def _latent_cache_key(latent):
    """latent 의 내용을 나타내는 캐시 키. (shape_tuple, sha1_hex) 또는 None.

    왜(Why) `id()` 가 아니라 내용인가 (2026-10-03 실측):
    CPython 은 GC 뒤 주소를 재배정한다. 실측 400개 연속 텐서 → 캐시 항목 2개,
    주소 재사용 398회. 그리고 재사용이 **틀린 픽셀**로 이어진다:
    프로브(tests/probe_cache_collision.py) 기준
        강한 참조 유지   20회 중 20회 정확
        참조 하나씩 해제  60회 중 **56회 오답**
    즉 `id()` 키는 "대부분 맞는데 가끔 엉뚱한 결과" 라 가장 나쁜 상태다.
    위의 `_VAE_FACTOR_BY_CLASS` 도 같은 이유로 클래스 키로 바꿨다(2026-10-01).

    왜(Why) pooled 인가, flat sha1 이 아닌가 (probe_key_cost.py 실측):
        shape              flat_ms   pooled_ms
        (1,16,64,64)         0.120      0.057
        (1,16,128,128)       0.797      0.067    ← 이 노드가 가장 많이 보는 크기
        (1,16,256,256)       2.879      0.168
        (1,16,512,512)      10.983      0.463
    큰 텐서일수록 pooled 가 훨씬 싸고(24배), 이 캐시는 VAE 디코드를 피하려고
    존재하는데 해시 비용이 디코드보다 크면 목적이 없다. VAE 디코드는
    128 latent → 2048px 이미지 수준이므로 수십 밀리초 이상이고 0.067ms 로
    회수된다. 카메라의 `_thumb_digest` 와 같은 방식이며 거기도 블록 평균이
    필요했다(점 샘플은 8px 워터마크 200개 중 199개를 못 잡아냈고,
    블록 평균은 0/200).
    구분 실패 위험: 1원소 변화와 1채널 변화를 둘 다 구분함을 같은 프로브가
    확인했다. 값이 0/1 사이로 클리핑되므로 키는 float32 원본에서 읽는다.
    **배치는 첫 원소만** 본다(2026-10-04 감사 5차 실측: batch 2 의 두 번째
    원소만 바꿔도 키가 같다). 현재 캐시 경로는 전부 `not _multi` 뒤라
    batch>1 이 여기 안 오지만, `not _multi` 를 하나라도 풀면 전부 조용히
    첫 원소로 디코드된다.

    실패하면 None 을 돌려 호출부가 **캐시를 쓰지 않게** 한다. 키를 못 만드는
    것보다 틀린 키로 엉뚱한 픽셀을 주는 것이 훨씬 나쁘다.
    """
    try:
        import hashlib as _hl
        import numpy as _np
        import torch as _t
        import torch.nn.functional as _tf
        # 왜(Why) 풀링을 장치에서 하는가 (2026-10-04 감사):
        # 전체 latent 를 CPU 로 옮기는 전송은 이 키를
        # 만들려는 목적(디코드 회피, 수십 ms) 의 10분의 1
        # 이상이 될 수 있다(512² latent = 16MB 전송).
        # 풀링은 장치에서 돌리고 **16x16 결과(16KB, 채널 유지)** 만
        # 옮긴다. 키는 한 실행 안의 캐시에서만 쓰이므로
        # (`_dcache` — run() 지역) 장치별 부동소수점
        # 순서 차이가 키를 뒤집지 않는다.
        if hasattr(latent, "detach") and hasattr(latent, "ndim"):
            shape = tuple(int(d) for d in latent.shape)
            if len(shape) < 2:
                return None
            t = latent.detach().float()
            while t.ndim < 4:
                t = t.unsqueeze(0)
            if t.shape[0] != 1:
                t = t[:1]
            pooled = _tf.adaptive_avg_pool2d(t, (16, 16))
            digest = _hl.sha1(
                pooled.detach().cpu().numpy().tobytes()).hexdigest()
            return (shape, digest)
        a = _np.asarray(latent, dtype=_np.float32)
        shape = tuple(int(d) for d in a.shape)
        if a.ndim < 2:
            return None
        t = _t.from_numpy(_np.ascontiguousarray(a)).float()
        while t.ndim < 4:
            t = t.unsqueeze(0)
        if t.shape[0] != 1:
            t = t[:1]
        pooled = _tf.adaptive_avg_pool2d(t, (16, 16))
        return (shape, _hl.sha1(pooled.numpy().tobytes()).hexdigest())
    except Exception:
        return None


def _decode_small(vae, latent, scale: float = 0.5):
    """latent → 축소 해상도 RGB numpy 배열(H,W,3). 실패 시 None.

    왜(Why) 기본 0.5인가: 패널 구조는 가로 해상도가 있어야 보인다(1/4로
    줄이면 6패널 시트의 패널 폭이 몇 픽셀까지 줄어 판별이 무너진다).
    샘플러 결과는 MediaPipe 랜드마크만 쓰므로 더 작아도 된다 → 호출부가 0.25.
    단, 아래 4MP 픽셀 예산이 걸리면 배율이 0.23 까도 내려갈 수 있다 —
    판정은 히스토그램 정규화라 해상도에 둔감하지만 무한정 작아지는 건
    아니다(예산이 하한이다).
    """
    try:
        import torch as _t
        import numpy as _np
        if vae is None or latent is None:
            return None
        import torch.nn.functional as _f
        s = float(scale)
        if not (0.05 <= s <= 1.0):
            return None
        # 왜(Why) 축소 디코드에도 상한이 필요한가 (2026-10-04
        # 감사): 0.5 배는 예외가 아니다. 74MP 캐릭터 시트
        # 참조를 0.5 배로 디코드하면 **18MP** 가 되어
        # `_DECODE_RETRY_PIXELS`(4MP — 이 노드가 실측에서
        # 감당한 최댓값) 를 4 배 넘는다. RTX 3080 10GB 에서
        # 2MP 통째 디코드가 멈춘 전례가 있는 구간이다
        # (`_DECODE_MAX_PIXELS` 주석). 상한 안으로 배율을
        # 더 낮춘다. 판정은 해상도에 둔감하다(시그니처는
        # 히스토그램 총합 정규화 — `analyze_reference_sheet`
        # 주석). 다만 6패널 시트의 패널 폭이 몇 픽셀로 줄면
        # 판별이 무너지므로(이 함수 docstring) 상한은 재시도
        # 디코드와 같은 4MP 로 둔다. "0.23 배 이상" 은 74MP 실측에서
        # 나온 수치라 **보장이 아니다** — 100MP 라면 0.20 이 된다
        # (실제 하한은 아래 `max(0.05, ...)`).
        _lh = int(latent.shape[-2])
        _lw = int(latent.shape[-1])
        _px = float(max(1, _lh) * max(1, _lw)
                    * _vae_pixel_factor_for(vae) ** 2 * s * s)
        if _px > _DECODE_RETRY_PIXELS:
            s = max(0.05, s * (_DECODE_RETRY_PIXELS / _px) ** 0.5)
        with _t.no_grad():
            small = (_f.interpolate(latent.float(), scale_factor=s, mode="area")
                     if s < 1.0 else latent.float())
            img = vae.decode(small)
        if hasattr(img, "detach"):
            img = img.detach().cpu()
        arr = img.numpy() if hasattr(img, "numpy") else _np.asarray(img)
        arr = _np.asarray(arr, dtype=_np.float32)
        out_s = _as_rgb_hwc(arr)
        # 왜(Why) release (2026-10-04 감사): 이 헬퍼는 **디코드가
        # 일어난** exit 에서 release 한다 (초기 return 두 곳은 할당 전).
        # 호출부가 나중에 release 해도 지금 이 자리가 마지막이 되는
        # 경로가 있다. (`_decode_latent_rgb` / `_decode_capped` 는
        # 호출부 위임이라 여기와 규칙이 다르다.)
        _release_vram()
        return out_s
    except Exception:
        _release_vram()
        return None
