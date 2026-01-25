### NOTE: WILL NEED TO INSTALL FFMPEG ON THE SYSTEM FOR THIS TO WORK ###
import requests
import os
from datetime import datetime
import time
import logging

import cv2
import vlc
# Configure logging: This provides a more robust way to track script activity and errors
# than simple print statements, especially for long-running processes.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
# --- Configuration ---
# The WebSocket URL that tunnels the RTSP stream.
WEBSOCKET_URL = "ws://67.61.139.162:8080/rtsp-over-websocket"
VIDEO_RESOLUTION = (1280, 720) # IMPORTANT: Find the correct resolution from the web player
 
# The directory where you want to save the images.
# The script will create this directory if it doesn't exist.
SAVE_DIRECTORY = "parking_spot_images"

# Time to wait between captures, in seconds.
# 1 hour = 3600 seconds.
CAPTURE_INTERVAL = 5 

def create_save_directory():
    """Creates the directory for saving images if it doesn't already exist."""
    try:
        if not os.path.exists(SAVE_DIRECTORY):
            os.makedirs(SAVE_DIRECTORY)
            logging.info(f"Created directory: {SAVE_DIRECTORY}")
    except OSError as e:
        logging.error(f"Error creating directory {SAVE_DIRECTORY}: {e}")
        # Exit the script if we can't create the directory
        exit()
        
def capture_and_save_image():
    """Captures a frame from an RTSP-over-WebSocket stream using python-vlc."""
    try:
        # Generate a unique filename using the current date and time
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"parking_spot_{timestamp}.jpg"
        filepath = os.path.join(SAVE_DIRECTORY, filename)

        # VLC options for handling RTSP-over-WebSocket
        # We must specify the subprotocol and custom headers here.
        # Each option and its value must be a separate element in the list.
        vlc_options = [
            '--no-xlib', # Don't create a GUI window
            '--http-header', 'User-Agent: Mozilla/5.0',
            '--http-header', 'Origin: http://67.61.139.162:8080',
            '--rtsp-ws-subprotocol', 'binary'
        ]

        # Create a VLC instance
        instance = vlc.Instance(vlc_options)
        player = instance.media_player_new()

        # Create a media object from the URL
        media = instance.media_new(WEBSOCKET_URL)
        player.set_media(media)

        # Start playing the video
        player.play()
        logging.info(f"VLC starting playback for {WEBSOCKET_URL}")

        # Give VLC a moment to connect and buffer the video
        time.sleep(3) 

        # Take a snapshot
        result = player.video_take_snapshot(0, filepath, 0, 0)
        player.stop()

        if result == 0:
            logging.info(f"Successfully saved image: {filepath}")
        else:
            logging.error("VLC failed to take a snapshot.")
        
    except Exception as e:
        logging.error(f"An unexpected error occurred during VLC capture: {e}")

def main():
    """Main function to run the image capture loop."""
    logging.info("Starting image capture script...")
    create_save_directory()
    
    try:
        while True:
            logging.info(f"--- Initiating capture cycle ---")
            capture_and_save_image()
            logging.info(f"Waiting for {CAPTURE_INTERVAL / 60} minutes before next capture...")
            time.sleep(CAPTURE_INTERVAL)
    except KeyboardInterrupt:
        logging.info("Script stopped by user. Exiting.")

if __name__ == "__main__":
    main()
