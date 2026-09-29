"""Crop the three Canvas calendar-feed screenshots used by the onboarding guide.

Inputs are the read-only attachment copies; outputs land in frontend/assets/guide/.
The Canvas feed URL in the third shot is blurred on purpose: it is a private
per-account token and must not be published.
"""

from pathlib import Path

from PIL import Image, ImageFilter

ATTACHMENTS = Path.home() / ".dsh" / "attachments" / "v1" / "objects"
OUTPUT = Path(__file__).resolve().parents[1] / "frontend" / "assets" / "guide"

SHOTS = [
    {
        "source": ATTACHMENTS / "18" / "18647a50fc38d486ced18e49e76e5437a3e7db58df4897667bfe47b89d7dc4ee",
        "output": "canvas-calendar-entry.jpg",
        "box": (0, 0, 660, 452),
        "blur": None,
    },
    {
        "source": ATTACHMENTS / "b9" / "b9b6e109c567fab8f5c7eef6a59b92ec7a254a3d43277c7022ead030e1438fc8",
        "output": "canvas-calendar-feed.jpg",
        "box": (1700, 800, 2760, 1320),
        "blur": None,
    },
    {
        "source": ATTACHMENTS / "1c" / "1ca1b1793fe50fdcf558cf4a5fb48fe51d1ee3d929f46f554fdefac9bb005135",
        "output": "canvas-calendar-feed-copy.jpg",
        "box": (960, 500, 1820, 1000),
        "blur": (1044, 812, 1724, 862),
    },
]


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for shot in SHOTS:
        image = Image.open(shot["source"]).convert("RGB")
        cropped = image.crop(shot["box"])
        if shot["blur"]:
            left, top, right, bottom = shot["blur"]
            box = (
                max(left - shot["box"][0], 0),
                max(top - shot["box"][1], 0),
                min(right - shot["box"][0], cropped.width),
                min(bottom - shot["box"][1], cropped.height),
            )
            region = cropped.crop(box).filter(ImageFilter.GaussianBlur(7))
            cropped.paste(region, box)
        target = OUTPUT / shot["output"]
        cropped.save(target, "JPEG", quality=86, optimize=True, progressive=True)
        print(f"{target.name}: {cropped.width}x{cropped.height} {target.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
