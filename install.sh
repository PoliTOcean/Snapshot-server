#!/bin/bash

# Define the project directory (assuming the script is in the project root)
PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
VENV_DIR="$PROJECT_DIR/.venv"
PYTHON_EXECUTABLE="python3" # Default to python3
MIN_PYTHON_MAJOR=3
MIN_PYTHON_MINOR=8 # Requiring Python 3.8 or newer

echo "--- Snapshot Server Installation Script ---"
echo "Project directory: $PROJECT_DIR"
echo "Virtual environment will be created at: $VENV_DIR"

# --- Check Python Version ---
echo ""
echo "1. Checking Python version..."
if ! command -v $PYTHON_EXECUTABLE &> /dev/null; then
    echo "Error: $PYTHON_EXECUTABLE is not installed."
    echo "Please install Python $MIN_PYTHON_MAJOR.$MIN_PYTHON_MINOR or newer and ensure '$PYTHON_EXECUTABLE' is in your PATH."
    exit 1
fi

PYTHON_VERSION_FULL=$($PYTHON_EXECUTABLE -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PYTHON_MAJOR=$(echo $PYTHON_VERSION_FULL | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION_FULL | cut -d. -f2)

echo "Found Python version: $PYTHON_VERSION_FULL"

if [ "$PYTHON_MAJOR" -lt "$MIN_PYTHON_MAJOR" ] || ([ "$PYTHON_MAJOR" -eq "$MIN_PYTHON_MAJOR" ] && [ "$PYTHON_MINOR" -lt "$MIN_PYTHON_MINOR" ]); then
    echo "Error: Python version $PYTHON_VERSION_FULL found. Version $MIN_PYTHON_MAJOR.$MIN_PYTHON_MINOR or newer is required."
    echo "Please upgrade your Python installation."
    exit 1
else
    echo "Python version $PYTHON_VERSION_FULL meets requirements. OK."
fi

# --- Check for pip ---
echo ""
echo "2. Checking for pip..."
if ! $PYTHON_EXECUTABLE -m pip --version &> /dev/null; then
    echo "Error: pip for $PYTHON_EXECUTABLE is not available."
    echo "Please ensure pip is installed for your Python version."
    echo "On Debian/Ubuntu, you might be able to install it with: sudo apt install python3-pip"
    exit 1
else
    echo "pip found. OK."
fi

# --- Create Virtual Environment ---
echo ""
echo "3. Creating virtual environment in $VENV_DIR..."
if [ -d "$VENV_DIR" ]; then
    echo "Virtual environment already exists at $VENV_DIR. Skipping creation."
else
    $PYTHON_EXECUTABLE -m venv "$VENV_DIR"
    if [ $? -ne 0 ]; then
        echo "Error: Failed to create virtual environment."
        exit 1
    fi
    echo "Virtual environment created successfully."
fi

# --- Install Python Dependencies ---
echo ""
echo "4. Installing Python dependencies from requirements.txt into $VENV_DIR..."
# Use the pip from the virtual environment
"$VENV_DIR/bin/pip" install -r "$PROJECT_DIR/requirements.txt"
if [ $? -ne 0 ]; then
    echo "Error: Failed to install Python dependencies."
    echo "Ensure '$PROJECT_DIR/requirements.txt' exists and is valid."
    exit 1
fi
echo "Python dependencies installed successfully."

# --- Install System Dependencies (v4l-utils and ffmpeg) ---
echo ""
echo "5. Installing system dependencies: v4l-utils and ffmpeg..."
if command -v apt-get &> /dev/null; then
    echo "Using apt-get (Debian/Ubuntu based system detected)."
    sudo apt-get update
    sudo apt-get install -y v4l-utils ffmpeg libopencv-dev
    if [ $? -ne 0 ]; then
        echo "Warning: Failed to install v4l-utils and ffmpeg automatically using apt-get."
        echo "Please install them manually (e.g., 'sudo apt-get install v4l-utils ffmpeg')."
    else
        echo "v4l-utils and ffmpeg installed successfully via apt-get."
    fi
elif command -v yum &> /dev/null; then
    echo "Using yum (Fedora/CentOS/RHEL based system detected)."
    sudo yum install -y v4l-utils ffmpeg opencv-devel
    if [ $? -ne 0 ]; then
        echo "Warning: Failed to install v4l-utils and ffmpeg automatically using yum."
        echo "Please install them manually (e.g., 'sudo yum install v4l-utils ffmpeg')."
    else
        echo "v4l-utils and ffmpeg installed successfully via yum."
    fi
else
    echo "Warning: Could not detect apt-get or yum. You may need to install v4l-utils and ffmpeg manually."
    echo "Please ensure v4l-utils and ffmpeg are installed for the snapshot functionality to work."
fi

# --- Final Instructions ---
echo ""
echo "--- Installation Setup Complete ---"
echo ""
echo "To run the application:"
echo "1. Activate the virtual environment: source \"$VENV_DIR/bin/activate\""
echo "2. Navigate to the project directory: cd \"$PROJECT_DIR\""
echo "3. Run the Flask app: python app.py"
echo ""
echo "IMPORTANT: If you use cameras of type 'stream_interrupt',"
echo "ensure the user running the Flask application has passwordless sudo permission"
echo "for specific systemctl commands. Example /etc/sudoers entry (replace 'your_flask_user'):"
echo "your_flask_user ALL=(ALL) NOPASSWD: /bin/systemctl stop camera_stream_*, /bin/systemctl restart camera_stream_*"
echo "(Ensure the path /bin/systemctl is correct for your system)."
echo ""
echo "Once the server is running, you can access the web interface at http://<your_raspberry_pi_ip>:88"
echo "--------------------------------"

exit 0
