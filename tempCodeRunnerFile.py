from flask import Flask, render_template, request, url_for, send_from_directory
from werkzeug.utils import secure_filename
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
import os
import atexit
import ffmpeg
import subprocess
import json

app = Flask(__name__)

# Set allowed file extensions and max file size
ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png'}
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv'}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max file size
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
app.config['UPLOAD_FOLDER'] = 'uploads'

# Function to check if the uploaded file is an allowed image type
def allowed_image_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS

# Function to check if the uploaded file is an allowed video type
def allowed_video_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_VIDEO_EXTENSIONS

# Function to extract EXIF data from images
def get_exif_data(image_path):
    try:
        image = Image.open(image_path)
        exif_data = image._getexif()
        if exif_data:
            exif_dict = {}
            for tag, value in exif_data.items():
                tag_name = TAGS.get(tag, tag)
                exif_dict[tag_name] = value
            return exif_dict
    except Exception as e:
        print(f"Error getting EXIF data: {e}")
    return None

# Function to convert GPS data from DMS (Degrees, Minutes, Seconds) to Decimal Degrees
def dms_to_decimal(dms):
    if not dms:
        return None
    degrees, minutes, seconds = dms
    return degrees + (minutes / 60.0) + (seconds / 3600.0)

# Function to extract GPS coordinates from EXIF data in images
def get_gps_coordinates_from_image(exif_data):
    gps_info = exif_data.get('GPSInfo') if exif_data else None
    if gps_info:
        gps_coords = {}
        for key, value in gps_info.items():
            tag_name = GPSTAGS.get(key, key)
            gps_coords[tag_name] = value
        
        lat = gps_coords.get('GPSLatitude')
        lon = gps_coords.get('GPSLongitude')
        
        if lat and lon:
            latitude = dms_to_decimal(lat)
            longitude = dms_to_decimal(lon)
            
            # Adjust sign based on hemisphere (N/S for latitude, E/W for longitude)
            if gps_coords.get('GPSLatitudeRef') == 'S':
                latitude = -latitude
            if gps_coords.get('GPSLongitudeRef') == 'W':
                longitude = -longitude
            
            return latitude, longitude
    return None, None

# Function to extract video metadata
def get_video_metadata(video_path):
    try:
        metadata = ffmpeg.probe(video_path, v='error', select_streams='v:0', show_entries='stream=codec_name,width,height,r_frame_rate,duration', format='json')
        metadata = json.loads(metadata)
        video_stream = metadata.get('streams', [])[0]
        width = video_stream.get('width')
        height = video_stream.get('height')
        duration = video_stream.get('duration')
        return {'width': width, 'height': height, 'duration': duration}
    except Exception as e:
        print(f"Error extracting video metadata: {e}")
    return None

# Cleanup function to delete uploaded files
def cleanup_uploads():
    for file in os.listdir(app.config['UPLOAD_FOLDER']):
        os.remove(os.path.join(app.config['UPLOAD_FOLDER'], file))

# Register cleanup at app exit
atexit.register(cleanup_uploads)

# Route to upload image or video and extract metadata
@app.route("/", methods=["GET", "POST"])
def index():
    file_url = None
    if request.method == "POST":
        # Get the uploaded image or video file
        uploaded_file = request.files.get('file')
        
        if uploaded_file:
            filename = secure_filename(uploaded_file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            uploaded_file.save(file_path)
            
            # Generate the URL for the uploaded file (for preview)
            file_url = url_for('uploaded_file', filename=filename)
            
            # Extract metadata based on file type
            if allowed_image_file(filename):
                # Extract EXIF data for images
                exif_data = get_exif_data(file_path)
                if exif_data:
                    gps_lat, gps_lon = get_gps_coordinates_from_image(exif_data)
                    if gps_lat and gps_lon:
                        google_maps_url = f"https://www.google.com/maps?q={gps_lat},{gps_lon}"
                        return render_template("index.html", exif_data=exif_data, gps_lat=gps_lat, gps_lon=gps_lon, google_maps_url=google_maps_url, file_url=file_url)
                    else:
                        return render_template("index.html", exif_data=exif_data, error="No GPS data found.", file_url=file_url)
                else:
                    return render_template("index.html", error="No EXIF data found.", file_url=file_url)
            
            elif allowed_video_file(filename):
                # Extract video metadata
                video_metadata = get_video_metadata(file_path)
                if video_metadata:
                    return render_template("index.html", video_metadata=video_metadata, file_url=file_url)
                else:
                    return render_template("index.html", error="No video metadata found.", file_url=file_url)
            
            else:
                return render_template("index.html", error="Invalid file format.", file_url=file_url)
    
    return render_template("index.html")

# Route to serve uploaded files (image or video)
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# Run the Flask app
if __name__ == '__main__':
    # Ensure the 'uploads' folder exists, create if not
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    
    # Run the Flask application on all available interfaces (0.0.0.0)
    # app.run(debug=True, host='0.0.0.0')
    app.run(debug=True, host='0.0.0.0', port=5001)
