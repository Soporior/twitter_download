"""
Organize existing assets into images/videos folders
"""
import os
import shutil

def organize_user_folder(user_path):
    """Organize a single user's folder into images/videos subfolders"""
    images_path = os.path.join(user_path, 'images')
    videos_path = os.path.join(user_path, 'videos')

    # Create subfolders if not exist
    os.makedirs(images_path, exist_ok=True)
    os.makedirs(videos_path, exist_ok=True)

    moved_images = 0
    moved_videos = 0

    # Move files
    for filename in os.listdir(user_path):
        filepath = os.path.join(user_path, filename)

        # Skip if it's a directory or subfolder
        if os.path.isdir(filepath):
            continue

        # Classify by extension
        if filename.endswith('.mp4'):
            dest = os.path.join(videos_path, filename)
            shutil.move(filepath, dest)
            moved_videos += 1
        elif filename.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
            dest = os.path.join(images_path, filename)
            shutil.move(filepath, dest)
            moved_images += 1
        # Skip other files (md, csv already deleted, etc.)

    return moved_images, moved_videos

def main():
    assets_path = 'D:/twitter_download/assets'

    total_users = 0
    total_images = 0
    total_videos = 0

    for user_folder in os.listdir(assets_path):
        user_path = os.path.join(assets_path, user_folder)
        if not os.path.isdir(user_path):
            continue

        imgs, vids = organize_user_folder(user_path)
        if imgs > 0 or vids > 0:
            print(f"{user_folder}: {imgs} images, {vids} videos")
            total_users += 1
            total_images += imgs
            total_videos += vids

    print(f"\nTotal: {total_users} users organized")
    print(f"Moved {total_images} images, {total_videos} videos")

if __name__ == '__main__':
    main()
