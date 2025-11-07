from __future__ import annotations

from typing import List

from PIL import Image


def sample_frames(video_path: str, frames_per_min: int, max_frames: int) -> List[Image.Image]:
    try:
        import cv2  # lazy import to avoid hard dependency in dry-run
    except Exception as e:
        raise RuntimeError("缺少 OpenCV（opencv-python）。请先 `pip install -r requirements.txt` 后再运行非 dry-run 模式。") from e

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"无法打开视频: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration_sec = total_frames / fps if total_frames > 0 else 0

    if duration_sec <= 0:
        # Fallback: sample first max_frames frames
        interval = max(1, int(fps))
    else:
        frames_needed = int((duration_sec / 60.0) * frames_per_min)
        frames_needed = max(1, min(frames_needed, max_frames))
        step = max(1, int(total_frames / frames_needed))
        interval = step

    frames: List[Image.Image] = []
    idx = 0
    while True:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        if not ok:
            break
        # Convert BGR to RGB and to PIL
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(rgb)
        frames.append(pil)
        if len(frames) >= max_frames:
            break
        idx += interval

    cap.release()
    return frames
