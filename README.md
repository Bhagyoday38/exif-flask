# Flask EXIF & Video Metadata Extractor 📷🎬

    This Flask web application allows users to upload image or video files and extracts useful metadata.

    ## 🧠 Features

    - Extracts EXIF data from JPG/PNG images
    - Converts GPS coordinates to Google Maps URL
    - Extracts metadata (resolution, duration) from video files
    - Supports MP4, AVI, MOV, MKV
    - Auto-cleans uploaded files on app shutdown

    ## ⚙️ Tech Stack

    - Python Flask
    - Pillow for EXIF
    - ffmpeg-python for video metadata

    DevOps MiniProject
    Shlok Banubakode - Bhagyoday Bade - Atharva Mahale

    ## Running the App with Docker

To run the `exif-flask-app` using Docker, follow these steps:

1. Build the Docker image:

   ```bash
   docker build -t exif-flask-app .
2. run container:
   docker run -p 5001:5001 exif-flask-app
