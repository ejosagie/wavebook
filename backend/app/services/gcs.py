"""Google Cloud Storage for WaveBook shop images.

Uploads product images to a public GCS bucket using the same gcloud CLI
authentication that backup.sh uses. This avoids any extra Python dependency
because the VPS already has gcloud installed and authenticated.

When GCS is not configured (GCS_BUCKET_NAME empty), callers fall back to the
local uploads directory, so the platform keeps working during development.
"""
import io
import os
import shutil
import subprocess
import tempfile

from PIL import Image

from ..config import settings

# Public bucket dedicated to storefront product images.
# The VPS backup bucket (GCS_BACKUP_BUCKET) is separate and private.
GCS_BUCKET_NAME = settings.GCS_BUCKET_NAME

# Folder inside the bucket (empty means the bucket root)
BLOB_ROOT = f"{settings.GCS_PREFIX.strip('/')}/" if settings.GCS_PREFIX.strip('/') else ""

# Max file size per image (10 MB) — checked before resize
MAX_IMAGE_SIZE = 10 * 1024 * 1024

# Max dimension for resized images
MAX_IMAGE_DIMENSION = 800

# All images are converted to JPEG after resize for consistency and smaller files
OUTPUT_FORMAT = "jpeg"
OUTPUT_EXT = "jpg"


def gcs_enabled() -> bool:
    """True when a GCS bucket is configured for product images."""
    return bool(GCS_BUCKET_NAME)


def _resize_image(image_data: bytes) -> bytes:
    """Resize the image to max 800x800, convert to JPEG, and return compressed bytes."""
    img = Image.open(io.BytesIO(image_data))

    # Convert to RGB (handles RGBA/Palette images for JPEG output)
    if img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")
    elif img.mode != "RGB":
        img = img.convert("RGB")

    # Resize maintaining aspect ratio
    img.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.Resampling.LANCZOS)

    # Save as JPEG with quality optimization
    output = io.BytesIO()
    img.save(output, format="JPEG", quality=85, optimize=True)
    return output.getvalue()


def _find_gcloud():
    """Find the gcloud binary, checking common install locations."""
    gcloud = shutil.which("gcloud")
    if gcloud:
        return gcloud
    candidates = [
        "/usr/lib/google-cloud-sdk/bin/gcloud",
        "/root/google-cloud-sdk/bin/gcloud",
        "/usr/local/google-cloud-sdk/bin/gcloud",
        "/opt/google-cloud-sdk/bin/gcloud",
        "/usr/bin/gcloud",
        os.path.expanduser("~/google-cloud-sdk/bin/gcloud"),
    ]
    for path in candidates:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


def _gcloud_env():
    """Build environment variables needed for gcloud CLI to work in systemd services."""
    env = os.environ.copy()
    sdk_dirs = [
        "/usr/lib/google-cloud-sdk",
        "/root/google-cloud-sdk",
        "/usr/local/google-cloud-sdk",
        "/opt/google-cloud-sdk",
        os.path.expanduser("~/google-cloud-sdk"),
    ]
    for sdk_dir in sdk_dirs:
        lib_path = os.path.join(sdk_dir, "lib")
        if os.path.isdir(lib_path):
            existing = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = lib_path + (":" + existing if existing else "")
            if "CLOUDSDK_PYTHON" not in env:
                env["CLOUDSDK_PYTHON"] = "python3"
            env["CLOUDSDK_ROOT"] = sdk_dir
            break
    return env


def _run_gcloud(args: list[str]) -> tuple[bool, str]:
    """Run a gcloud storage command and return (success, error_message)."""
    gcloud_bin = _find_gcloud()
    if not gcloud_bin:
        return False, "gcloud CLI not found. Ensure the Google Cloud SDK is installed and on PATH."
    try:
        result = subprocess.run(
            [gcloud_bin, "storage"] + args,
            capture_output=True,
            text=True,
            check=True,
            env=_gcloud_env(),
        )
        return True, result.stdout or ""
    except subprocess.CalledProcessError as e:
        return False, e.stderr or e.stdout or "gcloud command failed"
    except FileNotFoundError:
        return False, "gcloud CLI not found. Ensure the Google Cloud SDK is installed and on PATH."


def upload_shop_image(business_id: int, product_id: int, image_data: bytes) -> str:
    """
    Upload a single product image to GCS using gcloud storage cp.
    Images are automatically resized to max 800x800 and converted to JPEG.

    Args:
        business_id: Business owner id.
        product_id: The product id this image belongs to.
        image_data: Raw bytes of the image file.

    Returns:
        Public HTTPS URL of the uploaded object.

    Raises:
        ValueError: If the file is too large or not a supported image type.
        RuntimeError: If gcloud upload fails.
    """
    if not image_data or len(image_data) > MAX_IMAGE_SIZE:
        raise ValueError("Image missing or larger than 10 MB")

    # Auto-resize and convert to JPEG
    resized_data = _resize_image(image_data)

    blob_name = f"{BLOB_ROOT}shop-images/{business_id}/{product_id}.{OUTPUT_EXT}"
    gs_path = f"gs://{GCS_BUCKET_NAME}/{blob_name}"

    with tempfile.NamedTemporaryFile(suffix=f".{OUTPUT_EXT}", delete=False) as tmp:
        tmp.write(resized_data)
        tmp_path = tmp.name

    try:
        # Upload with correct content type
        ok, err = _run_gcloud(["cp", "--content-type", "image/jpeg", tmp_path, gs_path])
        if not ok:
            raise RuntimeError(f"Upload failed: {err}")

        # Bucket is already configured for public access, no ACL step needed
        return f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{blob_name}"
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def delete_shop_image(business_id: int, product_id: int) -> None:
    """Delete a product image from GCS (all legacy extensions)."""
    for ext in ("jpg", "png", "jpeg", "webp", "gif"):
        blob_name = f"{BLOB_ROOT}shop-images/{business_id}/{product_id}.{ext}"
        gs_path = f"gs://{GCS_BUCKET_NAME}/{blob_name}"
        ok, _ = _run_gcloud(["rm", gs_path])
        if ok:
            return


def build_image_url(business_id: int, product_id: int, ext: str = "jpg") -> str:
    """Build a deterministic GCS public URL for an image."""
    return (
        f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/"
        f"{BLOB_ROOT}shop-images/{business_id}/{product_id}.{ext}"
    )
