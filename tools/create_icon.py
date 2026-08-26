from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
SIZE = 256
image = Image.new("RGBA", (SIZE, SIZE), "#075e91")
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((0, 0, SIZE - 1, SIZE - 1), radius=52, fill="#075e91")
draw.rounded_rectangle((39, 180, 217, 190), radius=5, fill="#9fd7ef")
try:
    font = ImageFont.truetype(r"C:\Windows\Fonts\seguisb.ttf", 92)
except OSError:
    font = ImageFont.load_default()
box = draw.textbbox((0, 0), "LA", font=font)
draw.text(((SIZE - (box[2] - box[0])) / 2, 52), "LA", font=font, fill="white")
image.save(ROOT / "assets" / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
