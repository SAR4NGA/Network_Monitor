
import os
from PIL import Image

# Path to the generated image
img_path = r"C:\Users\sar4n\.gemini\antigravity\brain\a5994f29-ddbd-4ad2-8a41-1f1b35709776\network_monitor_icon_1773984863242.png"
out_path = r"c:\Users\sar4n\desktop\antigravity\scratch\network_monitor\app_icon.ico"

try:
    img = Image.open(img_path)
    # Define icon sizes (standard Windows sizes)
    icon_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(out_path, format="ICO", sizes=icon_sizes)
    print(f"Successfully saved icon to {out_path}")
except Exception as e:
    print(f"Error converting icon: {e}")
