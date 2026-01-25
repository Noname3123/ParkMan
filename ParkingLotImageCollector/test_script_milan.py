import requests
import os
from datetime import datetime
import time
import logging

# Configure logging: This provides a more robust way to track script activity and errors
# than simple print statements, especially for long-running processes.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
# --- Configuration ---
# The public URL of the camera image.
# This should be a direct link to the image itself (e.g., ending in .jpg, .png).
CAMERA_URL = "http://89.97.231.70:8083/cgi-bin/DownloadLiveImage" 
 
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
    """Fetches an image from the camera URL and saves it with a timestamp."""
    try:
        # Make the HTTP GET request to the camera URL
        logging.info(f"Attempting to fetch image from: {CAMERA_URL}")
        
        # Add a User-Agent header to mimic a browser, which can sometimes prevent blocking
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        # The timeout is important to prevent the script from hanging indefinitely
        # stream=True is CRITICAL for handling MJPEG streams. It prevents requests
        # from downloading the entire infinite stream at once.
        response = requests.get(CAMERA_URL, headers=headers, timeout=15, stream=True)

        # Check if the request was successful (HTTP status code 200)
        response.raise_for_status() 
        logging.info(f"Successfully received response from {CAMERA_URL}. Status: {response.status_code}")
        logging.debug(f"Response headers: {response.headers}") # Log headers at DEBUG level for verbosity

        # --- Logic to handle MJPEG stream ---
        # We will read the stream until we find the end of a JPEG image (0xFFD9).
        stream_data = b''
        image_data = None
        # The End Of Image (EOI) marker for a JPEG file.
        soi_marker = b'\xff\xd8'
        eoi_marker = b'\xff\xd9'

        for chunk in response.iter_content(chunk_size=1024):
            stream_data += chunk
            start_index = stream_data.find(soi_marker)
            if start_index != -1:
                # Found the start of an image, now look for the end
                end_index = stream_data.find(eoi_marker, start_index)
                if end_index != -1:
                    # A complete image is found
                    image_data = stream_data[start_index : end_index + 2]
                    logging.info("Found complete JPEG frame in stream. Captured one frame.")
                    break
        else: # This 'else' on a 'for' loop runs if the loop completes without a 'break'
            logging.error("Could not find a complete JPEG frame in the stream.")
            return # Exit the function if no image was captured

        # Determine file extension from Content-Type header for better accuracy
        content_type = response.headers.get('Content-Type', '').lower()
        extension = '.jpg' # Default
        if 'image/jpeg' in content_type:
            extension = '.jpg'
        elif 'image/png' in content_type:
            extension = '.png'
        else:
            logging.warning(f"Could not determine image type from Content-Type: {content_type}. Defaulting to {extension}")
            
        # Generate a unique filename using the current date and time
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"parking_spot_{timestamp}{extension}"
        filepath = os.path.join(SAVE_DIRECTORY, filename)

        # Save the image content to a file
        with open(filepath, 'wb') as f:
            f.write(image_data)
        
        logging.info(f"Successfully saved image: {filepath}")

    except requests.exceptions.RequestException as e:
        # Handle network errors, bad URLs, timeouts, etc.
        logging.error(f"Error fetching image from {CAMERA_URL}: {e}")
    except Exception as e:
        # Handle other potential errors (e.g., file saving issues)
        logging.error(f"An unexpected error occurred: {e}")

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
