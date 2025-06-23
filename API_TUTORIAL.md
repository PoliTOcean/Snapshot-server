# Snapshot Server API Tutorial

This document provides a guide to using the Snapshot Server API.

**Base URL**: `http://<your_server_ip>:88` (e.g., `http://localhost:88`)

---

## 1. List Available Cameras

Retrieves the current camera configurations.

*   **Endpoint**: `/api/cameras`
*   **Method**: `GET`
*   **Description**: Returns a JSON list of all configured cameras.
*   **Example Request (curl)**:
    ```bash
    curl http://localhost:88/api/cameras
    ```
*   **Example Successful Response (200 OK)**:
    ```json
    [
      {
        "name": "main_camera",
        "device_path": "/dev/video0",
        "type": "v4l2",
        "width": 1920,
        "height": 1080,
        "pixel_format": "MJPG",
        "stereo": false,
        "service_name": null
      },
      {
        "name": "right_camera",
        "device_path": "/dev/video2",
        "type": "stream_interrupt",
        "width": 1280,
        "height": 720,
        "pixel_format": "YUYV",
        "stereo": true,
        "service_name": "mjpg_streamer_right.service"
      }
    ]
    ```
*   **Example Error Response (if no cameras configured, 404 Not Found might be returned by some endpoints, but `/api/cameras` should return an empty list)**:
    ```json
    []
    ```

---

## 2. Take a Snapshot from a Specific Camera

Triggers a snapshot for a single specified camera.

*   **Endpoint**: `/api/snapshot/<camera_name>`
*   **Method**: `GET` or `POST`
*   **Description**: Captures an image from the camera identified by `<camera_name>`.
*   **Example Request (curl, using POST)**:
    ```bash
    curl -X POST http://localhost:88/api/snapshot/main_camera
    ```
*   **Example Successful Response (200 OK)**:
    ```json
    {
      "success": true,
      "filename": "snapshot_main_camera_20231027_100000123456.jpg",
      "message": "Snapshot taken: snapshot_main_camera_20231027_100000123456.jpg",
      "image_url_path": "/snapshots/snapshot_main_camera_20231027_100000123456.jpg"
    }
    ```
*   **Example Error Response (404 Not Found - Camera not found)**:
    ```json
    {
      "success": false,
      "error": "Camera not found"
    }
    ```
*   **Example Error Response (500 Internal Server Error - Capture failed)**:
    ```json
    {
      "success": false,
      "error": "Capture failed: <detailed error message>"
    }
    ```

---

## 3. Take Snapshots from All Cameras

Triggers snapshots for all configured cameras.

*   **Endpoint**: `/api/snapshot/all`
*   **Method**: `GET` or `POST`
*   **Description**: Captures images from all configured cameras. The operation is considered successful overall, but individual camera captures might fail. Check the `status` for each camera in the results.
*   **Example Request (curl, using POST)**:
    ```bash
    curl -X POST http://localhost:88/api/snapshot/all
    ```
*   **Example Successful Response (200 OK)**:
    ```json
    {
      "results": [
        {
          "camera_name": "main_camera",
          "status": "success",
          "filename": "api_all_cams_main_camera_20231027_100100123456.jpg",
          "image_url_path": "/snapshots/api_all_cams_main_camera_20231027_100100123456.jpg"
        },
        {
          "camera_name": "right_camera",
          "status": "failure",
          "error": "Snapshot file not created or too small"
        }
      ]
    }
    ```
*   **Example Error Response (404 Not Found - No cameras configured)**:
    ```json
    {
      "success": false,
      "error": "No cameras configured",
      "results": []
    }
    ```

---

## 4. Take Snapshots from Stereo Cameras

Triggers snapshots for all cameras marked as 'stereo' in the configuration.

*   **Endpoint**: `/api/snapshot/stereo`
*   **Method**: `GET` or `POST`
*   **Description**: Captures images from all cameras configured for stereo. The operation is considered successful overall, but individual camera captures might fail. Check the `status` for each camera in the results.
*   **Example Request (curl, using POST)**:
    ```bash
    curl -X POST http://localhost:88/api/snapshot/stereo
    ```
*   **Example Successful Response (200 OK)**:
    ```json
    {
      "results": [
        {
          "camera_name": "left_stereo_cam",
          "status": "success",
          "filename": "api_stereo_left_stereo_cam_20231027_100200123456.jpg",
          "image_url_path": "/snapshots/api_stereo_left_stereo_cam_20231027_100200123456.jpg"
        },
        {
          "camera_name": "right_stereo_cam",
          "status": "success",
          "filename": "api_stereo_right_stereo_cam_20231027_100200123456.jpg",
          "image_url_path": "/snapshots/api_stereo_right_stereo_cam_20231027_100200123456.jpg"
        }
      ]
    }
    ```
*   **Example Error Response (404 Not Found - No stereo cameras configured)**:
    ```json
    {
      "success": false,
      "error": "No stereo cameras configured",
      "results": []
    }
    ```

---

**Note on Image URLs**: The `image_url_path` returned is relative to the server's base URL. To download or view an image, prepend the server's base URL (e.g., `http://localhost:88/snapshots/your_image_filename.jpg`).
