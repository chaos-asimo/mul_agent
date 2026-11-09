import os
import glob

# 获取uploads/images目录下所有图片文件
image_extensions = ['*.jpg', '*.jpeg', '*.png', '*.gif', '*.bmp', '*.tiff', '*.webp']
image_files = []

for ext in image_extensions:
    image_files.extend(glob.glob(os.path.join('uploads', 'images', ext)))
    image_files.extend(glob.glob(os.path.join('uploads', 'images', ext.upper())))

# 去重
image_files = list(set(image_files))

# 排序以便输出更整齐
image_files.sort()

# 打印所有找到的图片文件路径
for image_file in image_files:
    print(image_file)