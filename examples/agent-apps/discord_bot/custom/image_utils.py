"""
Image utilities for Discord bot multimodal support.

Handles:
- Downloading images from URLs (with caching)
- Extracting frames from animated GIFs
- Converting images to base64 data URLs
"""

import asyncio
import base64
import io
import time
from dataclasses import dataclass

import httpx
from PIL import Image

from kohakuterrarium.utils.logging import get_logger

logger = get_logger("kohakuterrarium.custom.image_utils")

# Simple in-memory cache for downloaded images
# Key: URL, Value: (bytes, timestamp)
_image_cache: dict[str, tuple[bytes, float]] = {}
_CACHE_TTL = 300.0  # 5 minutes
_CACHE_MAX_SIZE = 100  # Max cached images


def _clean_cache() -> None:
    """Remove expired entries from cache."""
    now = time.time()
    expired = [url for url, (_, ts) in _image_cache.items() if now - ts > _CACHE_TTL]
    for url in expired:
        del _image_cache[url]

    # If still too large, remove oldest entries
    if len(_image_cache) > _CACHE_MAX_SIZE:
        sorted_items = sorted(_image_cache.items(), key=lambda x: x[1][1])
        for url, _ in sorted_items[: len(_image_cache) - _CACHE_MAX_SIZE]:
            del _image_cache[url]


@dataclass
class ProcessedImage:
    """Represents a processed image ready for LLM input."""

    data_url: str  # data:image/png;base64,...
    source_type: str  # "attachment", "emoji", "sticker", "gif_frame"
    source_name: str  # filename, emoji name, etc.
    frame_info: str | None = None  # "frame 1/3 (first)" for GIF frames


async def download_image(url: str, timeout: float = 10.0) -> bytes | None:
    """Download image from URL with caching."""
    # Check cache first
    if url in _image_cache:
        data, ts = _image_cache[url]
        if time.time() - ts < _CACHE_TTL:
            logger.debug("Image cache hit", extra={"url": url[:50]})
            return data
        else:
            del _image_cache[url]

    # Download
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=timeout, follow_redirects=True)
            if response.status_code == 200:
                data = response.content
                # Cache the result
                _clean_cache()
                _image_cache[url] = (data, time.time())
                return data
            logger.warning(
                "Failed to download image",
                extra={"url": url[:100], "status": response.status_code},
            )
    except Exception as e:
        logger.warning(
            "Error downloading image", extra={"url": url[:100], "error": str(e)}
        )
    return None


def image_to_data_url(image_data: bytes, mime_type: str = "image/png") -> str:
    """Convert image bytes to data URL."""
    b64 = base64.b64encode(image_data).decode("utf-8")
    return f"data:{mime_type};base64,{b64}"


def convert_image_to_jpeg(image_data: bytes, quality: int = 85) -> bytes | None:
    """
    Convert any image format to JPEG using PIL.

    This ensures compatibility with vision APIs that don't accept GIF/WebP.
    JPEG is smaller than PNG for most images.
    """
    try:
        img = Image.open(io.BytesIO(image_data))
        # Convert to RGB (JPEG doesn't support alpha)
        if img.mode in ("RGBA", "LA", "PA", "P"):
            # Create white background for transparency
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            if img.mode in ("RGBA", "LA", "PA"):
                background.paste(img, mask=img.split()[-1])  # Use alpha as mask
                img = background
            else:
                img = img.convert("RGB")
        elif img.mode != "RGB":
            img = img.convert("RGB")

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=quality, optimize=True)
        return buffer.getvalue()
    except Exception as e:
        logger.warning("Failed to convert image to JPEG", extra={"error": str(e)})
        return None


def extract_animated_frames(
    image_data: bytes,
    sample_positions: list[str] | None = None,
    jpeg_quality: int = 85,
) -> list[tuple[bytes, str]]:
    """
    Extract frames from animated GIF/APNG/WebP and convert to JPEG.

    Args:
        image_data: Raw image bytes (GIF/APNG/WebP)
        sample_positions: Which frames to extract: "first", "middle", "last"
                         Default: ["first", "middle", "last"]
        jpeg_quality: JPEG compression quality (1-100)

    Returns:
        List of (frame_bytes_as_jpeg, position_description) tuples
    """
    if sample_positions is None:
        sample_positions = ["first", "middle", "last"]

    try:
        img = Image.open(io.BytesIO(image_data))

        # Get total frame count
        try:
            n_frames = img.n_frames
        except AttributeError:
            n_frames = 1

        def frame_to_jpeg(frame_img: Image.Image) -> bytes:
            """Convert a frame to JPEG bytes."""
            # Convert to RGB (JPEG doesn't support alpha)
            if frame_img.mode in ("RGBA", "LA", "PA", "P"):
                background = Image.new("RGB", frame_img.size, (255, 255, 255))
                if frame_img.mode == "P":
                    frame_img = frame_img.convert("RGBA")
                if frame_img.mode in ("RGBA", "LA", "PA"):
                    background.paste(frame_img, mask=frame_img.split()[-1])
                    frame_img = background
                else:
                    frame_img = frame_img.convert("RGB")
            elif frame_img.mode != "RGB":
                frame_img = frame_img.convert("RGB")

            buffer = io.BytesIO()
            frame_img.save(buffer, format="JPEG", quality=jpeg_quality, optimize=True)
            return buffer.getvalue()

        if n_frames <= 1:
            # Not animated, return as single frame converted to JPEG
            return [(frame_to_jpeg(img), "static image")]

        # Calculate frame indices to extract
        frame_indices: list[tuple[int, str]] = []
        for pos in sample_positions:
            if pos == "first":
                frame_indices.append(
                    (0, f"sampled frame 1/{n_frames} from animated image (first)")
                )
            elif pos == "middle":
                mid = n_frames // 2
                frame_indices.append(
                    (
                        mid,
                        f"sampled frame {mid + 1}/{n_frames} from animated image (middle)",
                    )
                )
            elif pos == "last":
                frame_indices.append(
                    (
                        n_frames - 1,
                        f"sampled frame {n_frames}/{n_frames} from animated image (last)",
                    )
                )

        # Remove duplicates while preserving order
        seen = set()
        unique_indices = []
        for idx, desc in frame_indices:
            if idx not in seen:
                seen.add(idx)
                unique_indices.append((idx, desc))

        # Extract frames and convert to JPEG
        frames: list[tuple[bytes, str]] = []
        for frame_idx, description in unique_indices:
            try:
                img.seek(frame_idx)
                frame = img.copy()
                frames.append((frame_to_jpeg(frame), description))
            except EOFError:
                break

        logger.debug(
            "Extracted animated frames",
            extra={"total_frames": n_frames, "extracted": len(frames)},
        )
        return frames

    except Exception as e:
        logger.warning("Failed to extract animated frames", extra={"error": str(e)})
        return []


async def process_image_url(
    url: str,
    source_type: str,
    source_name: str,
    is_animated: bool = False,
    sample_positions: list[str] | None = None,
    jpeg_quality: int = 85,
) -> list[ProcessedImage]:
    """
    Process an image URL into ProcessedImage objects.

    All images are converted to JPEG for API compatibility and smaller size.
    For animated images (GIF/APNG/WebP), extracts sample frames.

    Args:
        url: Image URL
        source_type: Type of source ("attachment", "emoji", "sticker")
        source_name: Name/identifier of the source
        is_animated: Whether the image is known to be animated
        sample_positions: Frame positions to sample for animated images
        jpeg_quality: JPEG compression quality (1-100)

    Returns:
        List of ProcessedImage objects (multiple for animated images)
    """
    image_data = await download_image(url)
    if image_data is None:
        return []

    # Check if it's animated (GIF, APNG, or animated WebP)
    is_gif = image_data[:6] in (b"GIF87a", b"GIF89a")
    is_webp = image_data[:4] == b"RIFF" and image_data[8:12] == b"WEBP"
    might_be_animated = is_animated or is_gif or is_webp

    if might_be_animated:
        # Try to extract frames (works for GIF, APNG, animated WebP)
        frames = extract_animated_frames(image_data, sample_positions, jpeg_quality)
        if frames:
            results = []
            for frame_data, frame_desc in frames:
                data_url = image_to_data_url(frame_data, "image/jpeg")
                # Determine source type based on frame description
                if "animated" in frame_desc:
                    frame_source_type = f"{source_type}_animated_frame"
                else:
                    frame_source_type = source_type
                results.append(
                    ProcessedImage(
                        data_url=data_url,
                        source_type=frame_source_type,
                        source_name=source_name,
                        frame_info=frame_desc if "animated" in frame_desc else None,
                    )
                )
            return results

    # Static image or animation processing failed - convert to JPEG
    jpeg_data = convert_image_to_jpeg(image_data, jpeg_quality)
    if jpeg_data:
        data_url = image_to_data_url(jpeg_data, "image/jpeg")
        return [
            ProcessedImage(
                data_url=data_url,
                source_type=source_type,
                source_name=source_name,
            )
        ]

    # Conversion failed
    logger.warning(
        "Failed to process image",
        extra={"source": source_name, "source_type": source_type},
    )
    return []


async def process_multiple_images(
    items: list[
        tuple[str, str, str, bool]
    ],  # (url, source_type, source_name, is_animated)
    max_images: int = 10,
    gif_sample_positions: list[str] | None = None,
) -> list[ProcessedImage]:
    """
    Process multiple image URLs concurrently.

    Args:
        items: List of (url, source_type, source_name, is_animated) tuples
        max_images: Maximum total images to return
        gif_sample_positions: Frame positions to sample for GIFs

    Returns:
        List of ProcessedImage objects
    """
    if not items:
        return []

    # Process concurrently
    tasks = [
        process_image_url(url, src_type, src_name, is_anim, gif_sample_positions)
        for url, src_type, src_name, is_anim in items
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Flatten and filter results
    processed: list[ProcessedImage] = []
    for result in results:
        if isinstance(result, list):
            processed.extend(result)
        elif isinstance(result, Exception):
            logger.warning("Image processing failed", extra={"error": str(result)})

        if len(processed) >= max_images:
            break

    return processed[:max_images]
