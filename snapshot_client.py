import requests
import json

class SnapshotClientError(Exception):
    """Custom exception for SnapshotClient errors."""
    def __init__(self, message, status_code=None, response_text=None):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text

class SnapshotClient:
    """
    A Python client for interacting with the Snapshot Server API.
    """
    def __init__(self, base_url="http://localhost:88"):
        """
        Initializes the client.
        Args:
            base_url (str): The base URL of the Snapshot Server (e.g., "http://localhost:88").
        """
        if base_url.endswith('/'):
            base_url = base_url[:-1]
        self.base_url = base_url
        self.api_base_url = f"{self.base_url}/api"

    def _request(self, method, endpoint, params=None, data=None):
        """Helper function to make HTTP requests."""
        url = f"{self.api_base_url}{endpoint}"
        try:
            response = requests.request(method, url, params=params, json=data, timeout=45) # Increased timeout for capture
            response.raise_for_status()  # Raises HTTPError for bad responses (4XX or 5XX)
            return response.json()
        except requests.exceptions.HTTPError as e:
            error_message = f"HTTP error occurred: {e}"
            try:
                error_details = e.response.json()
                if "error" in error_details:
                    error_message = f"API Error: {error_details['error']}"
                elif "message" in error_details: # some flask errors might use message
                     error_message = f"API Error: {error_details['message']}"
            except json.JSONDecodeError:
                pass # Stick with the original HTTP error message
            raise SnapshotClientError(error_message, status_code=e.response.status_code, response_text=e.response.text) from e
        except requests.exceptions.RequestException as e:
            raise SnapshotClientError(f"Request failed: {e}") from e

    def get_cameras(self):
        """
        Retrieves the list of configured cameras.
        Returns:
            list: A list of camera configuration dictionaries.
        Raises:
            SnapshotClientError: If the API request fails.
        """
        return self._request("GET", "/cameras")

    def snapshot_camera(self, camera_name):
        """
        Takes a snapshot from a specific camera.
        Args:
            camera_name (str): The name of the camera.
        Returns:
            dict: API response, typically including success status, filename, and image URL path.
        Raises:
            SnapshotClientError: If the API request fails or camera is not found.
        """
        return self._request("POST", f"/snapshot/{camera_name}")

    def snapshot_all_cameras(self):
        """
        Takes snapshots from all configured cameras.
        Returns:
            dict: API response, typically a list of results for each camera.
        Raises:
            SnapshotClientError: If the API request fails.
        """
        return self._request("POST", "/snapshot/all")

    def snapshot_stereo_cameras(self):
        """
        Takes snapshots from all configured stereo cameras.
        Returns:
            dict: API response, typically a list of results for each stereo camera.
        Raises:
            SnapshotClientError: If the API request fails.
        """
        return self._request("POST", "/snapshot/stereo")

    def get_image_url(self, image_path):
        """
        Constructs the full URL for an image given its path from an API response.
        Args:
            image_path (str): The relative image path (e.g., "/snapshots/image.jpg").
        Returns:
            str: The full URL to the image.
        """
        if image_path.startswith('/'):
            return f"{self.base_url}{image_path}"
        return f"{self.base_url}/{image_path}"

if __name__ == "__main__":
    # Example Usage:
    # Replace with your server's IP if not running locally
    # client = SnapshotClient(base_url="http://your_raspberry_pi_ip:88")
    client = SnapshotClient(base_url="http://10.0.0.254:88")

    print("--- Testing Snapshot Client ---")

    try:
        # 1. Get list of cameras
        print("\n1. Fetching cameras...")
        cameras = client.get_cameras()
        if cameras:
            print(f"Found {len(cameras)} cameras:")
            for cam in cameras:
                print(f"  - {cam['name']} ({cam['device_path']})")
        else:
            print("No cameras configured on the server.")
            # exit() # Exit if no cameras for further tests

        # 2. Snapshot a specific camera (if any cameras are configured)
        if cameras:
            first_camera_name = cameras[0]['name']
            print(f"\n2. Taking snapshot from '{first_camera_name}'...")
            try:
                snap_result = client.snapshot_camera(first_camera_name)
                print(f"Snapshot result for {first_camera_name}: {snap_result}")
                if snap_result.get("success"):
                    image_url = client.get_image_url(snap_result['image_url_path'])
                    print(f"  Image URL: {image_url}")
            except SnapshotClientError as e:
                print(f"Error snapshotting {first_camera_name}: {e}")
        else:
            print("\n2. Skipping single camera snapshot (no cameras configured).")


        # 3. Snapshot all cameras
        print("\n3. Taking snapshot from all cameras...")
        try:
            all_snaps_result = client.snapshot_all_cameras()
            print(f"Snapshot all result: {all_snaps_result}")
            if all_snaps_result.get("results"):
                for res in all_snaps_result["results"]:
                    if res.get("status") == "success":
                         image_url = client.get_image_url(res['image_url_path'])
                         print(f"  {res['camera_name']}: SUCCESS - {image_url}")
                    else:
                         print(f"  {res['camera_name']}: FAILED - {res.get('error')}")
        except SnapshotClientError as e:
            print(f"Error snapshotting all cameras: {e}")


        # 4. Snapshot stereo cameras
        print("\n4. Taking snapshot from stereo cameras...")
        try:
            stereo_snaps_result = client.snapshot_stereo_cameras()
            print(f"Snapshot stereo result: {stereo_snaps_result}")
            if stereo_snaps_result.get("results"):
                 for res in stereo_snaps_result["results"]:
                    if res.get("status") == "success":
                         image_url = client.get_image_url(res['image_url_path'])
                         print(f"  {res['camera_name']}: SUCCESS - {image_url}")
                    else:
                         print(f"  {res['camera_name']}: FAILED - {res.get('error')}")
            elif stereo_snaps_result.get("error"): # Handle case where no stereo cameras are configured
                print(f"Could not take stereo snapshots: {stereo_snaps_result.get('error')}")

        except SnapshotClientError as e:
            print(f"Error snapshotting stereo cameras: {e}")

    except SnapshotClientError as e:
        print(f"\nAn API client error occurred:")
        print(f"  Message: {e}")
        if e.status_code:
            print(f"  Status Code: {e.status_code}")
        if e.response_text:
            print(f"  Response: {e.response_text[:200]}...") # Print first 200 chars

    print("\n--- Test complete ---")
