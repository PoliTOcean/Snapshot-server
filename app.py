import flask
import json
import os
import subprocess
import datetime
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import paho.mqtt.client as paho_mqtt # Added
import piexif # Added
import piexif.helper # Added

app = flask.Flask(__name__)

CONFIG_FILE = 'config.json'
SNAPSHOT_DIR = 'snapshots'
# Ensure snapshot directory exists
os.makedirs(SNAPSHOT_DIR, exist_ok=True)

# --- MQTT Configuration and Globals ---
MQTT_BROKER_HOST = "127.0.0.1"
MQTT_BROKER_PORT = 1883
MQTT_TOPIC = "status/"
mqtt_client = None

latest_imu_data = {
    "roll": None,
    "pitch": None,
    "yaw": None,
    "timestamp": None
}
imu_data_lock = threading.Lock()

def on_connect(client, userdata, flags, rc):
    """MQTT connect callback."""
    if rc == 0:
        app.logger.info(f"Connected to MQTT Broker at {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT}")
        client.subscribe(MQTT_TOPIC)
        app.logger.info(f"Subscribed to topic: {MQTT_TOPIC}")
    else:
        app.logger.error(f"Failed to connect to MQTT Broker, return code {rc}")

def on_message(client, userdata, msg):
    """MQTT message callback to process IMU data."""
    global latest_imu_data, imu_data_lock
    try:
        payload = json.loads(msg.payload.decode())
        # app.logger.debug(f"Received MQTT message on {msg.topic}: {payload}")
        if "roll" in payload and "pitch" in payload and "yaw" in payload:
            with imu_data_lock:
                latest_imu_data["roll"] = payload["roll"]
                latest_imu_data["pitch"] = payload["pitch"]
                latest_imu_data["yaw"] = payload["yaw"]
                latest_imu_data["timestamp"] = time.time() # Record when data was processed
            # app.logger.debug(f"Updated IMU data: {latest_imu_data}")
    except json.JSONDecodeError:
        app.logger.error(f"Failed to decode JSON from MQTT message: {msg.payload}")
    except Exception as e:
        app.logger.error(f"Error processing MQTT message: {e}")

def get_current_imu_data():
    """Safely get a copy of the latest IMU data."""
    with imu_data_lock:
        return latest_imu_data.copy()

def init_mqtt_client():
    """Initializes and starts the MQTT client."""
    global mqtt_client
    try:
        # Using a unique client_id can be helpful if multiple instances run
        client_id = f"snapshot_server_imu_{os.getpid()}"
        mqtt_client = paho_mqtt.Client(client_id=client_id, protocol=paho_mqtt.MQTTv311)
        mqtt_client.on_connect = on_connect
        mqtt_client.on_message = on_message
        # Add username/password if your broker requires authentication
        # mqtt_client.username_pw_set(username="your_user", password="your_password")
        mqtt_client.connect(MQTT_BROKER_HOST, MQTT_BROKER_PORT, 60)
        mqtt_client.loop_start() # Starts a background thread for MQTT network loop
        app.logger.info("MQTT client initialized and loop started.")
    except Exception as e:
        app.logger.error(f"Failed to initialize MQTT client: {e}")

# --- EXIF Metadata Helper ---
def _embed_imu_metadata_in_image(filepath, imu_data_to_embed, camera_config):
    """Embeds IMU data as JSON into the image's EXIF UserComment tag, applying camera-specific offsets.
    Returns True on success, False on failure.
    """
    if not os.path.exists(filepath):
        app.logger.error(f"File not found for metadata embedding: {filepath}")
        return False

    # Apply offsets
    adjusted_imu_data = imu_data_to_embed.copy()
    roll_offset = float(camera_config.get('roll_offset', 0.0))
    pitch_offset = float(camera_config.get('pitch_offset', 0.0))
    yaw_offset = float(camera_config.get('yaw_offset', 0.0))

    if adjusted_imu_data.get("roll") is not None:
        try:
            adjusted_imu_data["roll"] = float(adjusted_imu_data["roll"]) + roll_offset
        except (ValueError, TypeError):
            app.logger.warning(f"Could not apply roll offset for {camera_config['name']}, invalid roll data: {adjusted_imu_data.get('roll')}")
    if adjusted_imu_data.get("pitch") is not None:
        try:
            adjusted_imu_data["pitch"] = float(adjusted_imu_data["pitch"]) + pitch_offset
        except (ValueError, TypeError):
            app.logger.warning(f"Could not apply pitch offset for {camera_config['name']}, invalid pitch data: {adjusted_imu_data.get('pitch')}")
    if adjusted_imu_data.get("yaw") is not None:
        try:
            adjusted_imu_data["yaw"] = float(adjusted_imu_data["yaw"]) + yaw_offset
        except (ValueError, TypeError):
            app.logger.warning(f"Could not apply yaw offset for {camera_config['name']}, invalid yaw data: {adjusted_imu_data.get('yaw')}")
    
    # Format to string with fixed precision after offset application if desired, or keep as float
    # For simplicity, keeping as float for JSON dump. Could format here:
    # adjusted_imu_data["roll"] = f"{adjusted_imu_data['roll']:.3f}" if adjusted_imu_data["roll"] is not None else None
    # etc.

    relevant_imu_data = {
        k: adjusted_imu_data[k] for k in ["roll", "pitch", "yaw", "timestamp"]
        if k in adjusted_imu_data and adjusted_imu_data[k] is not None
    }

    if not relevant_imu_data or not any(k in relevant_imu_data for k in ["roll", "pitch", "yaw"]):
        app.logger.info(f"No relevant IMU data (roll, pitch, yaw) after adjustments to embed for {filepath}")
        return True # No data to embed is not an error in embedding itself.

    try:
        imu_json_string = json.dumps(relevant_imu_data)
        user_comment_payload = piexif.helper.UserComment.dump(imu_json_string, encoding='unicode')

        try:
            exif_dict = piexif.load(filepath)
            # Ensure all standard IFD dictionaries exist if piexif.load provided a partial structure
            for ifd_name in ["0th", "Exif", "GPS", "Interop", "1st"]:
                if ifd_name not in exif_dict or not isinstance(exif_dict[ifd_name], dict):
                    exif_dict[ifd_name] = {}
            if "thumbnail" not in exif_dict: # Thumbnail data is not a dict
                 exif_dict["thumbnail"] = None

        except piexif.InvalidImageDataError:
            app.logger.info(f"No valid existing EXIF data in {filepath}, creating new structure.")
            exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "Interop": {}, "1st": {}, "thumbnail": None}
        except Exception as e: # Catch other piexif load errors
            app.logger.error(f"Error loading existing EXIF from {filepath}: {e}. Attempting to create new EXIF.")
            exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "Interop": {}, "1st": {}, "thumbnail": None}

        # Add UserComment to the Exif IFD
        exif_dict["Exif"][piexif.ExifIFD.UserComment] = user_comment_payload
        
        # Add a Software tag to 0th IFD for better compatibility/structure
        exif_dict["0th"][piexif.ImageIFD.Software] = "SnapshotServer/PiexifV1"
        
        exif_bytes = piexif.dump(exif_dict)
        piexif.insert(exif_bytes, filepath)
        app.logger.info(f"Attempted to embed IMU data into {filepath}. UserComment: {imu_json_string}")

        # ---- Verification Step ----
        try:
            verify_exif_dict = piexif.load(filepath)
            retrieved_user_comment_bytes = verify_exif_dict.get("Exif", {}).get(piexif.ExifIFD.UserComment)
            
            if retrieved_user_comment_bytes:
                retrieved_comment_str = piexif.helper.UserComment.load(retrieved_user_comment_bytes)
                if retrieved_comment_str == imu_json_string:
                    app.logger.info(f"VERIFICATION SUCCESS: UserComment correctly written and read back from {filepath}.")
                    return True # Embedding and verification successful
                else:
                    app.logger.warning(f"VERIFICATION MISMATCH: UserComment content differs in {filepath}.")
                    app.logger.warning(f"  Expected: '{imu_json_string}'")
                    app.logger.warning(f"  Retrieved: '{retrieved_comment_str}'")
                    app.logger.debug(f"Full verified EXIF (mismatch): {json.dumps(verify_exif_dict, default=lambda o: str(o))}")
                    return False # Content mismatch is a failure
            else:
                app.logger.warning(f"VERIFICATION FAILED: UserComment tag not found in {filepath} after insert.")
                app.logger.debug(f"Full verified EXIF (tag not found): {json.dumps(verify_exif_dict, default=lambda o: str(o))}")
                return False # Tag not found is a critical failure
        except Exception as e_verify:
            app.logger.error(f"VERIFICATION EXCEPTION: Error during EXIF verification for {filepath}: {e_verify}")
            app.logger.debug(f"EXIF data at time of verification exception: {json.dumps(exif_dict, default=lambda o: str(o))}")
            return False # If verification itself fails, consider embedding failed
        # ---- End Verification Step ----

    except FileNotFoundError: # Should be caught by initial check, but good practice
        app.logger.error(f"File disappeared before metadata embedding: {filepath}")
        return False
    except Exception as e:
        app.logger.error(f"Failed to embed IMU metadata into {filepath}: {e}")
        return False


# --- Configuration Helpers ---
def load_config():
    if not os.path.exists(CONFIG_FILE):
        return []
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return []

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

def get_camera_config(camera_name):
    config = load_config()
    for cam in config:
        if cam['name'] == camera_name:
            return cam
    return None

# --- Command Execution Helper ---
def _run_command(command_list, timeout=15):
    """Runs a shell command and returns (success, output_or_error_message)."""
    app.logger.info(f"Running command: {' '.join(command_list)}")
    try:
        process = subprocess.run(command_list, capture_output=True, text=True, timeout=timeout, check=False)
        if process.returncode == 0:
            app.logger.info(f"Command successful: {' '.join(command_list)}. Output: {process.stdout.strip()}")
            return True, process.stdout.strip()
        else:
            app.logger.error(f"Command failed: {' '.join(command_list)}\nStderr: {process.stderr.strip()} (Code: {process.returncode})")
            return False, f"Error: {process.stderr.strip()} (Code: {process.returncode})"
    except subprocess.TimeoutExpired:
        app.logger.error(f"Command timed out: {' '.join(command_list)}")
        return False, "Error: Command timed out"
    except FileNotFoundError:
        app.logger.error(f"Command not found: {command_list[0]}")
        return False, f"Error: Command {command_list[0]} not found. Ensure it's installed and in PATH."
    except Exception as e:
        app.logger.error(f"Exception running command {' '.join(command_list)}: {e}")
        return False, f"Error: Exception {e}"

# --- Device Busy Check ---
def is_device_busy(device_path, logger):
    """Checks if a V4L2 device is busy."""
    # This command lists controls. If it fails with "Device or resource busy", it's busy.
    # Other errors might mean different issues (e.g., device not found).
    command = ['v4l2-ctl', '-d', device_path, '--list-controls']
    logger.info(f"Checking if device {device_path} is busy with command: {' '.join(command)}")
    try:
        proc = subprocess.run(
            command,
            capture_output=True, text=True, timeout=3, check=False
        )
        # Typical exit code for busy can be 1 or 255, stderr contains "Device or resource busy"
        if proc.returncode != 0:
            stderr_lower = proc.stderr.lower()
            if "busy" in stderr_lower or "eagain" in stderr_lower: # EAGAIN can also mean busy
                logger.warning(f"Device {device_path} reported busy: {proc.stderr.strip()}")
                return True
            else:
                # Other error, device might be unusable but not strictly "busy" by another app
                logger.warning(f"v4l2-ctl check on {device_path} failed (code {proc.returncode}): {proc.stderr.strip()}")
                return False # Or True if any error means we can't proceed
        logger.info(f"Device {device_path} is not busy.")
        return False # Command succeeded, device is responsive
    except subprocess.TimeoutExpired:
        logger.error(f"Timeout checking if device {device_path} is busy.")
        return True # Assume busy or inaccessible if timeout
    except FileNotFoundError:
        logger.error(f"v4l2-ctl command not found for busy check. Please ensure v4l-utils is installed.")
        return True # Cannot check, assume problematic
    except Exception as e:
        logger.error(f"Error checking if device {device_path} is busy: {e}")
        return True # Unknown error, assume problematic

# --- Snapshot Core Logic ---
def capture_image(camera_config, base_filename_prefix="snapshot"):
    """Captures an image from the specified camera and embeds IMU data."""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S%f")
    filename = f"{base_filename_prefix}_{camera_config['name']}_{timestamp}.jpg"
    filepath = os.path.join(SNAPSHOT_DIR, filename)

    app.logger.info(f"Taking snapshot for {camera_config['name']}")

    service_stopped = False
    service_name = None
    
    if camera_config['type'] == 'stream_interrupt':
        service_name = camera_config.get('service_name')
        if service_name:
            app.logger.info(f"Stopping service {service_name}")
            _run_command(['sudo', 'systemctl', 'stop', service_name])
            service_stopped = True
            time.sleep(1)  # Wait for service to stop

    # Simple v4l2-ctl capture
    cmd_capture = [
        'v4l2-ctl', '-d', camera_config['device_path'],
        f"--set-fmt-video=width={camera_config['width']},height={camera_config['height']},pixelformat={camera_config['pixel_format']}",
        '--stream-mmap', '--stream-count=1', f'--stream-to={filepath}'
    ]

    capture_ok, msg_capture = _run_command(cmd_capture, timeout=30)

    # Restart service if needed
    if service_stopped and service_name:
        app.logger.info(f"Restarting service {service_name}")
        _run_command(['sudo', 'systemctl', 'restart', service_name])

    if not capture_ok:
        return False, f"Capture failed: {msg_capture}", None

    # Simple file check
    if not os.path.exists(filepath) or os.path.getsize(filepath) < 1000:
        # Clean up failed/small capture file before returning
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
                app.logger.info(f"Removed incomplete/small file: {filepath}")
            except OSError as e_rm:
                app.logger.error(f"Error removing incomplete file {filepath}: {e_rm}")
        return False, "Snapshot file not created or too small", None
        
    # Embed IMU data
    current_imu = get_current_imu_data()
    if not _embed_imu_metadata_in_image(filepath, current_imu, camera_config):
        # Embedding failed. The image file exists but lacks metadata.
        # Report as failure to indicate the full operation wasn't successful.
        # The file is kept for potential debugging.
        error_msg = f"Image captured ({filename}), but failed to embed IMU metadata."
        app.logger.error(f"Snapshot for {camera_config['name']}: {error_msg}")
        return False, error_msg, filename # Return filename so caller knows what file was affected
            
    app.logger.info(f"Snapshot successful: {filename}")
    return True, filepath, filename

def capture_stereo_simple(cameras, base_filename_prefix="stereo"):
    """Capture from stereo cameras sequentially with minimal delay and embed IMU data."""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S%f")
    results = []
    
    app.logger.info(f"Starting sequential v4l2-ctl stereo capture for {len(cameras)} cameras")
    
    # Stop services if needed
    services_to_restart = []
    for camera_config in cameras:
        if camera_config['type'] == 'stream_interrupt':
            service_name = camera_config.get('service_name')
            if service_name:
                app.logger.info(f"Stopping service {service_name}")
                _run_command(['sudo', 'systemctl', 'stop', service_name])
                services_to_restart.append(service_name)
    
    if services_to_restart:
        time.sleep(2)  # Wait for services to stop
    
    # Capture sequentially with minimal delay
    start_time = time.time()
    
    for i, camera_config in enumerate(cameras):
        filename = f"{base_filename_prefix}_{camera_config['name']}_{timestamp}.jpg"
        filepath = os.path.join(SNAPSHOT_DIR, filename)
        
        app.logger.info(f"Sequential capture {i+1}/{len(cameras)}: {camera_config['name']}")
        
        cmd_capture = [
            'v4l2-ctl', '-d', camera_config['device_path'],
            f"--set-fmt-video=width={camera_config['width']},height={camera_config['height']},pixelformat={camera_config['pixel_format']}",
            '--stream-mmap', '--stream-count=1', f'--stream-to={filepath}'
        ]
        
        capture_start = time.time()
        capture_ok, msg_capture = _run_command(cmd_capture, timeout=30)
        capture_time = (time.time() - capture_start) * 1000
        
        if capture_ok and os.path.exists(filepath) and os.path.getsize(filepath) > 1000:
            # Embed IMU data
            current_imu = get_current_imu_data()
            embedding_successful = _embed_imu_metadata_in_image(filepath, current_imu, camera_config)

            if embedding_successful:
                results.append({
                    "success": True,
                    "camera_name": camera_config['name'],
                    "image_url": flask.url_for('serve_snapshot', filename=filename),
                    "download_url": flask.url_for('download_snapshot', filename=filename),
                    "filename": filename,
                    "capture_time_ms": capture_time
                })
                file_size = os.path.getsize(filepath)
                app.logger.info(f"Sequential capture successful for {camera_config['name']}: {filename} ({file_size} bytes, {capture_time:.1f}ms)")
            else:
                # Image captured, but metadata embedding failed.
                error_msg = f"Image captured ({filename}), but failed to embed IMU metadata."
                results.append({
                    "success": False,
                    "camera_name": camera_config['name'],
                    "error": error_msg,
                    "filename": filename # Include filename for reference
                })
                app.logger.error(f"Sequential capture for {camera_config['name']}: {error_msg}")
        else:
            error_msg = f"v4l2-ctl failed: {msg_capture}" if not capture_ok else "File not created or too small"
            # Clean up failed/small capture file
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                    app.logger.info(f"Removed problematic stereo capture file: {filepath}")
                except OSError as e_rm:
                    app.logger.error(f"Error removing problematic stereo file {filepath}: {e_rm}")
            results.append({
                "success": False,
                "camera_name": camera_config['name'],
                "error": error_msg
            })
            app.logger.error(f"Sequential capture failed for {camera_config['name']}: {error_msg}")
        
        # Very small delay between cameras for stereo
        if i < len(cameras) - 1:
            time.sleep(0.05)  # 50ms delay
    
    total_time = (time.time() - start_time) * 1000
    app.logger.info(f"Sequential stereo capture completed in {total_time:.1f}ms")
    
    # Restart services
    for service_name in services_to_restart:
        app.logger.info(f"Restarting service {service_name}")
        _run_command(['sudo', 'systemctl', 'restart', service_name])
    
    # Summary
    successful_captures = [r for r in results if r['success']]
    app.logger.info(f"Sequential stereo capture summary: {len(successful_captures)}/{len(cameras)} cameras successful")
    
    return results

def _process_snapshot_requests(cameras_to_snapshot, base_filename_prefix="snapshot"):
    """Process camera snapshots sequentially - simple and reliable."""
    results = []
    
    app.logger.info(f"Taking sequential snapshots for {len(cameras_to_snapshot)} cameras")
    
    for cam_config in cameras_to_snapshot:
        success, result_path_or_msg, filename = capture_image(cam_config, base_filename_prefix)
        if success:
            results.append({
                "success": True,
                "camera_name": cam_config['name'],
                "image_url": flask.url_for('serve_snapshot', filename=filename),
                "download_url": flask.url_for('download_snapshot', filename=filename),
                "filename": filename
            })
        else:
            results.append({
                "success": False,
                "camera_name": cam_config['name'],
                "error": result_path_or_msg
            })
        
        # Small delay between cameras
        time.sleep(0.05)
    
    return results

# --- Web UI Routes ---
@app.route('/')
def index():
    return flask.render_template('index.html')

@app.route('/settings', methods=['GET'])
def settings_page():
    config = load_config()
    return flask.render_template('settings.html', cameras=config)

@app.route('/settings/add', methods=['POST'])
def add_camera():
    config = load_config()
    try:
        new_camera = {
            "name": flask.request.form['name'],
            "device_path": flask.request.form['device_path'],
            "type": flask.request.form['type'],
            "width": int(flask.request.form['width']),
            "height": int(flask.request.form['height']),
            "pixel_format": flask.request.form['pixel_format'].upper(),
            "stereo": flask.request.form.get('stereo') == 'on',
            "service_name": flask.request.form.get('service_name', None),
            "roll_offset": float(flask.request.form.get('roll_offset', 0.0) or 0.0),
            "pitch_offset": float(flask.request.form.get('pitch_offset', 0.0) or 0.0),
            "yaw_offset": float(flask.request.form.get('yaw_offset', 0.0) or 0.0)
        }
        if not new_camera['name'] or not new_camera['device_path']:
            flask.flash("Name and Device Path are required.", "error")
            return flask.redirect(flask.url_for('settings_page'))

        if any(cam['name'] == new_camera['name'] for cam in config):
            flask.flash(f"Camera with name '{new_camera['name']}' already exists.", "error")
            return flask.redirect(flask.url_for('settings_page'))
            
        if new_camera['type'] == 'stream_interrupt' and not new_camera['service_name']:
            flask.flash("Service Name is required for stream_interrupt type cameras.", "error")
            return flask.redirect(flask.url_for('settings_page'))


        config.append(new_camera)
        save_config(config)
        flask.flash(f"Camera '{new_camera['name']}' added successfully.", "success")
    except Exception as e:
        flask.flash(f"Error adding camera: {e}", "error")
    return flask.redirect(flask.url_for('settings_page'))

@app.route('/settings/delete/<camera_name>', methods=['POST'])
def delete_camera(camera_name):
    config = load_config()
    config = [cam for cam in config if cam['name'] != camera_name]
    save_config(config)
    flask.flash(f"Camera '{camera_name}' deleted.", "success")
    return flask.redirect(flask.url_for('settings_page'))

@app.route('/snapshots/<filename>')
def serve_snapshot(filename):
    return flask.send_from_directory(SNAPSHOT_DIR, filename)

@app.route('/download/<filename>')
def download_snapshot(filename):
    return flask.send_from_directory(SNAPSHOT_DIR, filename, as_attachment=True)

# --- UI Snapshot Triggers (POST requests from JS) ---
@app.route('/ui/snapshot/<camera_name>', methods=['POST'])
def ui_snapshot_camera(camera_name):
    cam_config = get_camera_config(camera_name)
    if not cam_config:
        return flask.jsonify({"success": False, "error": "Camera not found"})
    
    success, result, filename = capture_image(cam_config)
    if success:
        return flask.jsonify({
            "success": True, 
            "image_url": flask.url_for('serve_snapshot', filename=filename),
            "download_url": flask.url_for('download_snapshot', filename=filename),
            "filename": filename,
            "camera_name": camera_name
        })
    else:
        return flask.jsonify({"success": False, "error": result, "camera_name": camera_name})

@app.route('/ui/snapshot/all', methods=['POST'])
def ui_snapshot_all():
    config = load_config()
    if not config:
        return flask.jsonify({"success": False, "error": "No cameras configured", "results": []})
    
    snapshot_results = _process_snapshot_requests(config, "all_cams")
    return flask.jsonify({"success": True, "results": snapshot_results}) # Overall success is true, check individual results

@app.route('/ui/snapshot/stereo', methods=['POST'])
def ui_snapshot_stereo():
    config = load_config()
    stereo_cameras = [cam for cam in config if cam.get('stereo')]
    if not stereo_cameras:
        return flask.jsonify({"success": False, "error": "No stereo cameras configured", "results": []})

    # Use simple approach for stereo capture
    snapshot_results = capture_stereo_simple(stereo_cameras, "stereo")
    return flask.jsonify({"success": True, "results": snapshot_results})


# --- API Endpoints ---
@app.route('/api/cameras', methods=['GET'])
def api_get_cameras():
    config = load_config()
    return flask.jsonify(config)

@app.route('/api/snapshot/<camera_name>', methods=['GET', 'POST']) # Allow GET for simple API tests
def api_snapshot_camera(camera_name):
    cam_config = get_camera_config(camera_name)
    if not cam_config:
        return flask.jsonify({"success": False, "error": "Camera not found"}), 404
    
    success, result, filename = capture_image(cam_config)
    if success:
        return flask.jsonify({
            "success": True, 
            "filename": filename,
            "message": f"Snapshot taken: {filename}",
            # For API, providing full URL might be useful if client is remote
            "image_url_path": flask.url_for('serve_snapshot', filename=filename, _external=False) 
        })
    else:
        return flask.jsonify({"success": False, "error": result}), 500

@app.route('/api/snapshot/all', methods=['GET', 'POST'])
def api_snapshot_all():
    config = load_config()
    if not config:
        return flask.jsonify({"success": False, "error": "No cameras configured", "results": []}), 404
    
    api_results = []
    # Using the same processing logic, but tailoring the response for API
    snapshot_results = _process_snapshot_requests(config, "api_all_cams") 
    for res in snapshot_results:
        if res['success']:
            api_results.append({
                "camera_name": res['camera_name'], 
                "status": "success", 
                "filename": res['filename'],
                "image_url_path": flask.url_for('serve_snapshot', filename=res['filename'], _external=False)
            })
        else:
            api_results.append({
                "camera_name": res['camera_name'], 
                "status": "failure", 
                "error": res['error']
            })
    return flask.jsonify({"results": api_results})

@app.route('/api/snapshot/stereo', methods=['GET', 'POST'])
def api_snapshot_stereo():
    config = load_config()
    stereo_cameras = [cam for cam in config if cam.get('stereo')]
    if not stereo_cameras:
        return flask.jsonify({"success": False, "error": "No stereo cameras configured", "results": []}), 404

    # Use simple approach for API stereo capture
    snapshot_results = capture_stereo_simple(stereo_cameras, "api_stereo")
    api_results = []
    for res in snapshot_results:
        if res['success']:
            api_results.append({
                "camera_name": res['camera_name'], 
                "status": "success", 
                "filename": res['filename'],
                "image_url_path": flask.url_for('serve_snapshot', filename=res['filename'], _external=False)
            })
        else:
            api_results.append({
                "camera_name": res['camera_name'], 
                "status": "failure", 
                "error": res['error']
            })
    return flask.jsonify({"results": api_results})


if __name__ == '__main__':
    # Set process to be less aggressive
    import os
    import resource
    
    try:
        # Lower process priority
        os.nice(10)  # Higher nice value = lower priority
        
        # Limit CPU usage
        resource.setrlimit(resource.RLIMIT_CPU, (30, 60))  # Limit CPU time
        
        # Set I/O priority to idle class (requires ionice)
        try:
            subprocess.run(['ionice', '-c', '3', '-p', str(os.getpid())], check=False)
        except:
            pass
            
    except Exception as e:
        print(f"Could not set process limits: {e}")
    
    app.secret_key = os.urandom(24)
    init_mqtt_client()
    
    # Use Werkzeug with limited threads
    from werkzeug.serving import make_server
    
    server = make_server(
        host='0.0.0.0', 
        port=88, 
        app=app,
        threaded=True,
        processes=1  # Single process
    )
    
    # Set thread limits
    server.max_children = 2  # Limit concurrent requests
    
    print("Starting snapshot server with real-time optimizations...")
    server.serve_forever()
