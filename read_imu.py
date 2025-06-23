import piexif
import piexif.helper
import json
import sys

def read_imu_from_image(image_path):
    """
    Reads IMU data embedded in the EXIF UserComment tag of an image.

    Args:
        image_path (str): The path to the image file.

    Returns:
        dict: A dictionary containing the IMU data, or None if not found or an error occurs.
    """
    try:
        exif_dict = piexif.load(image_path)
        user_comment_bytes = exif_dict.get("Exif", {}).get(piexif.ExifIFD.UserComment)

        if user_comment_bytes:
            # Decode the UserComment
            # piexif.helper.UserComment.load handles the encoding (e.g., 'unicode', 'ascii')
            try:
                user_comment_str = piexif.helper.UserComment.load(user_comment_bytes)
            except UnicodeDecodeError:
                # Fallback for older piexif versions or different encodings if needed
                # This assumes UTF-8 if 'unicode' fails, adjust if your server uses something else
                try:
                    user_comment_str = user_comment_bytes.decode('utf-8', errors='ignore')
                    # Remove the encoding prefix if present (e.g., "UNICODE\x00\x00")
                    if user_comment_str.startswith("UNICODE"):
                        user_comment_str = user_comment_str.split('\x00\x00', 1)[-1].strip('\x00')
                    elif user_comment_str.startswith("ASCII"):
                         user_comment_str = user_comment_str.split('\x00\x00', 1)[-1].strip('\x00')

                except Exception as e_decode_fallback:
                    print(f"Error decoding UserComment with fallback: {e_decode_fallback}")
                    return None


            # The actual JSON string might be embedded within this comment string
            # print(f"Raw UserComment string: '{user_comment_str}'") # For debugging

            try:
                # Attempt to parse the string as JSON
                imu_data = json.loads(user_comment_str)
                return imu_data
            except json.JSONDecodeError as e_json:
                print(f"Failed to parse UserComment as JSON: {e_json}")
                print(f"UserComment content was: {user_comment_str}")
                return None
        else:
            print("No EXIF UserComment tag found in the image.")
            return None

    except FileNotFoundError:
        print(f"Error: Image file not found at {image_path}")
        return None
    except piexif.InvalidImageDataError:
        print(f"Error: Invalid image data or no EXIF data in {image_path}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python read_imu_from_image.py <path_to_image.jpg>")
        sys.exit(1)

    image_file = sys.argv[1]
    imu_data = read_imu_from_image(image_file)

    if imu_data:
        print("\nSuccessfully extracted IMU data:")
        print(f"  Roll: {imu_data.get('roll')}")
        print(f"  Pitch: {imu_data.get('pitch')}")
        print(f"  Yaw: {imu_data.get('yaw')}")
        print(f"  Timestamp: {imu_data.get('timestamp')}")
    else:
        print("\nCould not extract IMU data from the image.")