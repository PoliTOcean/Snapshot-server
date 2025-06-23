# Snapshot Server

Snapshot Server is a Flask-based web application that allows you to manage and capture images from V4L2 (Video4Linux2) cameras connected to your system, typically a Linux machine like a Raspberry Pi. It provides a web interface for configuration and triggering snapshots, as well as a REST API for programmatic control.

## Features

*   **Web Interface**:
    *   Configure multiple cameras (name, device path, resolution, pixel format, type).
    *   Mark cameras for stereo capture.
    *   Specify services to stop/restart for cameras that require exclusive access (e.g., `mjpg-streamer`).
    *   Trigger snapshots for individual cameras, all cameras, or stereo pairs.
    *   View and download captured snapshots.
*   **REST API**:
    *   List configured cameras.
    *   Trigger snapshots for individual, all, or stereo cameras.
    *   (See [API_TUTORIAL.md](API_TUTORIAL.md) for detailed API documentation).
*   **Snapshot Modes**:
    *   **Single Camera**: Capture from one specified camera.
    *   **All Cameras**: Capture from all configured cameras. Services are stopped once at the beginning and restarted once at the end to minimize downtime.
    *   **Stereo Cameras**: Capture sequentially from cameras marked as 'stereo' with minimal delay for good timing synchronization.
*   **Camera Control**: Uses `v4l2-ctl` for direct camera interaction, ensuring reliable capture.
*   **Service Interruption Handling**: Can automatically stop and restart specified system services (e.g., a streaming service) around the snapshot process to free up camera devices.

## Requirements

*   Python 3.x
*   Flask
*   `v4l-utils` (provides `v4l2-ctl` command-line tool)
*   `requests` (for the Python client library)

## Setup and Installation

1.  **Clone the repository (if applicable) or download the files.**

2.  **Install `v4l-utils`**:
    This package provides the `v4l2-ctl` utility, which is essential for camera control.
    ```bash
    sudo apt-get update
    sudo apt-get install v4l-utils
    ```

3.  **Install Python dependencies**:
    It's recommended to use a virtual environment.
    ```bash
    python3 -m venv venv
    source venv/bin/activate  # On Linux/macOS
    # venv\Scripts\activate  # On Windows

    pip install Flask requests
    ```

4.  **Permissions for `sudo systemctl` (if using `stream_interrupt` camera type)**:
    The application uses `sudo systemctl stop/restart <service_name>` if a camera is of type `stream_interrupt` and a `service_name` is provided. Ensure the user running the Flask application has passwordless sudo privileges for these specific commands. This can typically be configured in the `/etc/sudoers` file (e.g., using `visudo`).
    **Example for allowing `systemctl` commands for a specific service without a password for user `pi`**:
    ```
    pi ALL=(ALL) NOPASSWD: /bin/systemctl stop my_camera_service.service
    pi ALL=(ALL) NOPASSWD: /bin/systemctl restart my_camera_service.service
    ```
    Replace `my_camera_service.service` with the actual service names you intend to use. **Be cautious when editing sudoers.**

## Running the Server

Navigate to the project directory.

**For Development (with higher CPU usage):**
You can use the built-in Flask development server:
```bash
python app.py
```
By default, `app.py` now runs with `debug=False` to reduce idle CPU. If you need debugging features, you can temporarily change `debug=False` to `debug=True` in `app.py`.


## Configuration

1.  Access the web interface (e.g., `http://rasperryIP:88`).
2.  Navigate to the "Settings" page.
3.  Add your cameras:
    *   **Name**: A unique name for the camera (e.g., "main_cam", "right_eye").
    *   **Device Path**: The V4L2 device path (e.g., `/dev/video0`, or a persistent symlink like `/dev/camera-main-photo`).
    *   **Type**:
        *   `v4l2`: Standard V4L2 camera.
        *   `stream_interrupt`: A camera whose device might be in use by another service (e.g., `mjpg-streamer`). Provide the `Service Name` to stop/restart.
    *   **Width/Height**: Desired capture resolution.
    *   **Pixel Format**: Camera's pixel format (e.g., `MJPG`, `YUYV`).
    *   **Stereo**: Check if this camera is part of a stereo pair.
    *   **Service Name**: (Only for `stream_interrupt` type) The systemd service name to stop before capture and restart after (e.g., `mjpg_streamer.service`).

Configuration is saved in `config.json`.

## Using the API

The server exposes a REST API for programmatic control.
Refer to [API_TUTORIAL.md](API_TUTORIAL.md) for detailed endpoints and usage examples.

## Python Client Library

A Python client library (`snapshot_client.py`) is provided to simplify interaction with the API.

**Example Usage:**
```python
from snapshot_client import SnapshotClient, SnapshotClientError

# Replace with your server's IP if not running locally
client = SnapshotClient(base_url="http://your_server_ip:88")

try:
    cameras = client.get_cameras()
    print("Available cameras:", [cam['name'] for cam in cameras])

    if cameras:
        result = client.snapshot_camera(cameras[0]['name'])
        if result.get('success'):
            print(f"Snapshot taken: {result['filename']}")
            print(f"Image URL: {client.get_image_url(result['image_url_path'])}")
        else:
            print(f"Error: {result.get('error')}")

except SnapshotClientError as e:
    print(f"Client Error: {e}")
```
See `snapshot_client.py` for more examples.


## IMU Data
By default IMU data coming from MQTT Topic (at this moment from Oceanix) are saved as metadata of the image for the photosphere task (imu version).
MQTT address and topic are configurable from app.py
