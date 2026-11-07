"""Inference backends: SAM 3D Body (real, GPU) and a deterministic mock.

Both return, per frame, MHR70-shaped (70, 3) RIGHT-hand keypoints (or None when
no hand pose was recovered). Left-hand images are mirrored before inference,
because the SAM 3D Body hand decoder is right-hand only (see angles.py).
Images are only ever held in memory.
"""

from __future__ import annotations

import logging
import math
import os
import sys
import threading
import time
from pathlib import Path
from typing import List, Optional

import numpy as np

from angles import FINGERS, MHR70_RIGHT_HAND_IDX, synthetic_right_keypoints

log = logging.getLogger("hand_mesh")

HERE = Path(__file__).resolve().parent
VENDOR_DIR = HERE / "vendor" / "sam-3d-body"
DEFAULT_HF_REPO = "facebook/sam-3d-body-vith"
CKPT_FILES = ("model_config.yaml", "model.ckpt", "assets/mhr_model.pt")


class BackendUnavailable(Exception):
    pass


# ---------------------------------------------------------------------------
# Mock
# ---------------------------------------------------------------------------

_MOCK_BASE = {
    "index": {"mcp": 48.0, "pip": 62.0, "dip": 18.0},
    "middle": {"mcp": 52.0, "pip": 68.0, "dip": 20.0},
    "ring": {"mcp": 55.0, "pip": 66.0, "dip": 19.0},
    "pinky": {"mcp": 58.0, "pip": 60.0, "dip": 16.0},
}


class MockBackend:
    name = "mock"
    model = "mock"
    device = "cpu"

    def __init__(self, reason: Optional[str] = None):
        self.reason = reason

    @property
    def model_loaded(self) -> bool:
        return True

    @property
    def status(self) -> str:
        return "ready"

    def infer(self, images: List[np.ndarray], hand_side: str) -> List[Optional[np.ndarray]]:
        """Deterministic: depends only on the number of frames and their order."""
        n = len(images)
        out = []
        for k in range(n):
            jitter = 3.0 * math.sin(1.7 * k + n)
            angles = {f: {j: v + jitter * (1 + 0.3 * i) for j, v in _MOCK_BASE[f].items()}
                      for i, f in enumerate(FINGERS)}
            c, s = math.cos(0.4 * k), math.sin(0.4 * k)
            rigid = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])  # view change around y
            out.append(synthetic_right_keypoints(angles, rigid))
        return out


# ---------------------------------------------------------------------------
# SAM 3D Body
# ---------------------------------------------------------------------------


def _describe_hf_error(e: Exception, repo: str) -> str:
    try:
        from huggingface_hub.errors import GatedRepoError, LocalEntryNotFoundError, RepositoryNotFoundError
    except Exception:  # pragma: no cover
        GatedRepoError = LocalEntryNotFoundError = RepositoryNotFoundError = ()  # type: ignore
    from huggingface_hub import get_token

    if isinstance(e, GatedRepoError):
        if not get_token():
            return f"Hugging Face token not found: run `hf auth login` (access to {repo} is gated)"
        return f"access to {repo} not granted yet (gated repo): request access on huggingface.co and wait for approval"
    if isinstance(e, RepositoryNotFoundError):
        if not get_token():
            return f"Hugging Face token not found: run `hf auth login` ({repo})"
        return f"repository {repo} not found or not accessible with the current token"
    if isinstance(e, LocalEntryNotFoundError):
        return f"cannot download {repo} (offline?) and no local copy: {e}"
    return f"{type(e).__name__}: {e}"


class Sam3dBackend:
    name = "sam3d"
    model = "sam-3d-body"

    def __init__(self):
        self.repo = os.environ.get("HAND_MESH_HF_REPO", DEFAULT_HF_REPO)
        self.ckpt_dir = os.environ.get("HAND_MESH_CHECKPOINT_DIR") or None
        self.box_scale = float(os.environ.get("HAND_MESH_BOX_SCALE", "1.0"))
        self.device = "cuda"
        self._status = "not_loaded"
        self.reason: Optional[str] = None
        self._model = None
        self._transform_hand = None
        self._gpu_lock = threading.Lock()

    @property
    def model_loaded(self) -> bool:
        return self._model is not None

    @property
    def status(self) -> str:
        return self._status

    # -- loading -----------------------------------------------------------
    def _resolve_checkpoint(self) -> Path:
        if self.ckpt_dir:
            d = Path(self.ckpt_dir)
            missing = [f for f in CKPT_FILES if not (d / f).exists()]
            if missing:
                raise BackendUnavailable(f"HAND_MESH_CHECKPOINT_DIR={d} is missing {missing}")
            return d
        from huggingface_hub import hf_hub_download

        self._status = "downloading"
        paths = []
        try:
            for f in CKPT_FILES:  # uses the token cached by `hf auth login`
                paths.append(hf_hub_download(repo_id=self.repo, filename=f))
        except Exception as e:  # noqa: BLE001
            raise BackendUnavailable(_describe_hf_error(e, self.repo)) from e
        return Path(paths[0]).parent

    def load(self) -> None:
        t0 = time.time()
        try:
            import torch

            if not torch.cuda.is_available():
                raise BackendUnavailable("CUDA is not available (SAM 3D Body needs an NVIDIA GPU)")
            if str(VENDOR_DIR) not in sys.path:
                sys.path.insert(0, str(VENDOR_DIR))
            os.environ.setdefault("MOMENTUM_ENABLED", "0")  # use the TorchScript MHR in the checkpoint
            # Import first so a broken install is reported before a 2+ GB download.
            from sam_3d_body.data.transforms import (
                Compose,
                GetBBoxCenterScale,
                TopdownAffine,
                VisionTransformWrapper,
            )
            from sam_3d_body.models.meta_arch import SAM3DBody
            from sam_3d_body.utils.checkpoint import load_state_dict
            from sam_3d_body.utils.config import get_config
            from torchvision.transforms import ToTensor

            ckpt_dir = self._resolve_checkpoint()
            self._status = "loading"
            cfg = get_config(str(ckpt_dir / "model_config.yaml"))
            cfg.defrost()
            cfg.MODEL.MHR_HEAD.MHR_MODEL_PATH = str(ckpt_dir / "assets" / "mhr_model.pt")
            if cfg.MODEL.BACKBONE.get("FLASH_ATTN", False):
                try:
                    import flash_attn  # noqa: F401
                except ImportError:
                    cfg.MODEL.BACKBONE.FLASH_ATTN = False
            cfg.freeze()

            model = SAM3DBody(cfg)
            ckpt = torch.load(str(ckpt_dir / "model.ckpt"), map_location="cpu", weights_only=False)
            load_state_dict(model, ckpt.get("state_dict", ckpt), strict=False)
            del ckpt
            model = model.to("cuda").eval()

            # Same hand-crop transform as SAM3DBodyEstimator.transform_hand
            self._transform_hand = Compose(
                [
                    GetBBoxCenterScale(padding=0.9),
                    TopdownAffine(input_size=cfg.MODEL.IMAGE_SIZE, use_udp=False),
                    VisionTransformWrapper(ToTensor()),
                ]
            )
            self._model = model
            self.device = f"cuda:0 ({torch.cuda.get_device_name(0)})"
            self._status = "ready"
            self.reason = None
            log.info("SAM 3D Body loaded from %s in %.1fs", self.repo if not self.ckpt_dir else ckpt_dir, time.time() - t0)
        except BackendUnavailable as e:
            self._status = "failed"
            self.reason = str(e)
            raise
        except Exception as e:  # noqa: BLE001
            self._status = "failed"
            self.reason = f"{type(e).__name__}: {e}"
            raise BackendUnavailable(self.reason) from e

    # -- inference ---------------------------------------------------------
    def _box(self, h: int, w: int) -> np.ndarray:
        # Frames are already cropped around the hand (MediaPipe box + 20%), so the
        # whole frame (optionally scaled about its centre) is the hand box. No detector.
        side_w, side_h = w * self.box_scale, h * self.box_scale
        cx, cy = w / 2.0, h / 2.0
        return np.array([[cx - side_w / 2, cy - side_h / 2, cx + side_w / 2, cy + side_h / 2]], dtype=np.float32)

    def infer(self, images: List[np.ndarray], hand_side: str) -> List[Optional[np.ndarray]]:
        if self._model is None:
            raise BackendUnavailable(self.reason or f"model is {self._status}")
        import torch
        from sam_3d_body.data.utils.prepare_batch import prepare_batch
        from sam_3d_body.utils import recursive_to

        results: List[Optional[np.ndarray]] = []
        with self._gpu_lock, torch.no_grad():
            for img in images:
                if hand_side == "left":
                    img = np.ascontiguousarray(img[:, ::-1])  # hand decoder is right-hand only
                h, w = img.shape[:2]
                batch = prepare_batch(img, self._transform_hand, self._box(h, w))
                batch = recursive_to(batch, "cuda")
                self._model._initialize_batch(batch)
                out = self._model.forward_step(batch, decoder_type="hand")["mhr_hand"]
                kp3d = out["pred_keypoints_3d"][0].float().cpu().numpy()
                kp2d_crop = out["pred_keypoints_2d_cropped"][0].float().cpu().numpy()
                del batch, out
                hand2d = kp2d_crop[MHR70_RIGHT_HAND_IDX]
                # Upstream validity check (run_inference, CRITERIA 3): hand keypoints inside the crop.
                if not np.all(np.isfinite(kp3d[MHR70_RIGHT_HAND_IDX])) or np.abs(hand2d).max() >= 0.5:
                    results.append(None)
                else:
                    results.append(kp3d)
        return results


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


class BackendManager:
    """HAND_MESH_BACKEND = auto (default) | sam3d | mock.

    auto : try SAM 3D Body in the background; on failure fall back to mock (logged).
    sam3d: SAM 3D Body only; while loading/failed, /v1/angles returns MESH_UNAVAILABLE.
    mock : mock only.
    """

    def __init__(self, requested: Optional[str] = None):
        self.requested = (requested or os.environ.get("HAND_MESH_BACKEND") or "auto").strip().lower()
        if self.requested not in ("auto", "sam3d", "mock"):
            raise ValueError(f"HAND_MESH_BACKEND must be sam3d|mock (got {self.requested!r})")
        self.sam3d: Optional[Sam3dBackend] = None
        self.active = None
        self.fallback_reason: Optional[str] = None
        if self.requested == "mock":
            self.active = MockBackend()
        else:
            self.sam3d = Sam3dBackend()

    def start(self, background: bool = True) -> None:
        if self.sam3d is None:
            log.info("hand-mesh backend: mock (HAND_MESH_BACKEND=mock)")
            return
        if background:
            threading.Thread(target=self._load, name="sam3d-loader", daemon=True).start()
        else:
            self._load()

    def _load(self) -> None:
        try:
            self.sam3d.load()
            self.active = self.sam3d
            log.info("hand-mesh backend: sam3d (%s)", self.sam3d.device)
        except BackendUnavailable as e:
            if self.requested == "auto":
                self.fallback_reason = str(e)
                self.active = MockBackend(reason=str(e))
                log.warning("SAM 3D Body unavailable -> FALLING BACK TO MOCK backend. Reason: %s", e)
            else:
                log.error("SAM 3D Body unavailable (HAND_MESH_BACKEND=sam3d, no fallback): %s", e)

    def current(self):
        """Backend to use now, or raise BackendUnavailable."""
        if self.active is not None:
            return self.active
        s = self.sam3d
        if s.status == "failed":
            raise BackendUnavailable(s.reason or "SAM 3D Body failed to load")
        raise BackendUnavailable(f"SAM 3D Body is {s.status}")

    def health(self) -> dict:
        b = self.active
        s = self.sam3d
        info = {
            "ok": b is not None,
            "backend": b.name if b is not None else "sam3d",
            "device": b.device if b is not None else (s.device if s else "cpu"),
            "model_loaded": bool(b is not None and b.model_loaded),
            "model": b.model if b is not None else "sam-3d-body",
            "requested_backend": self.requested,
        }
        if s is not None:
            info["sam3d"] = {"status": s.status, "repo": s.repo, "reason": s.reason}
        if self.fallback_reason:
            info["fallback_reason"] = self.fallback_reason
        return info
