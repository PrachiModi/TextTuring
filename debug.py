import os
from PIL import Image

def extract_image_metadata(directory):
    for root, _, files in os.walk(directory):
        for file in files:
            if file.lower().endswith(('.png', '.jpg', '.jpeg')):
                path = os.path.join(root, file)
                try:
                    with Image.open(path) as img:
                        print(f"File: {path}")
                        print(f"Format: {img.format}")
                        print(f"Size: {img.size}")
                        dpi = img.info.get('dpi')
                        if dpi:
                            print(f"DPI: {dpi[0]}, {dpi[1]} (rounded: {round(dpi[0])}, {round(dpi[1])})")
                        else:
                            print("DPI: Not set")
                        print("Other info:", img.info)
                        print("---")
                except Exception as e:
                    print(f"Error: {path} - {e}")

dir_path = '/Users/prachi.modi/Downloads/QS_7050X_1RU 3/Graphics/Taiwan_RoHS'
extract_image_metadata(dir_path)