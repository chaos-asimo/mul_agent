import os


def count_image_files(directory):
    """
    Recursively count all image files in a directory.
    
    Args:
        directory (str): The root directory to start searching from.
        
    Returns:
        int: Total number of image files found.
    """
    # Define common image file extensions
    image_extensions = {
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif',
        '.webp', '.svg', '.ico', '.raw', '.cr2', '.nef', '.arw'
    }
    
    count = 0
    for root, dirs, files in os.walk(directory):
        for filename in files:
            # Get the file extension (case-insensitive)
            _, ext = os.path.splitext(filename)
            if ext.lower() in image_extensions:
                count += 1
                print(f"Found image: {os.path.join(root, filename)}")
    
    return count


if __name__ == "__main__":
    # You can change this to any directory you want to scan
    target_directory = "."  # Current directory
    
    print(f"Scanning directory: {target_directory}")
    print("-" * 50)
    
    total_images = count_image_files(target_directory)
    
    print("-" * 50)
    print(f"Total image files found: {total_images}")