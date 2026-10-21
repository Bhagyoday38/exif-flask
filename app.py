import atexit
from pathlib import Path
from uuid import uuid4

import ffmpeg
from flask import Flask, render_template, request, send_from_directory, url_for
from PIL import ExifTags, Image, UnidentifiedImageError
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename

app = Flask(__name__)

ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png"}
ALLOWED_VIDEO_EXTENSIONS = {"mp4", "avi", "mov", "mkv"}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024

app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
app.config["UPLOAD_FOLDER"] = str(Path(app.root_path) / "uploads")
Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

GPS_IFD_TAG = 34853
_created_uploads = set()


def cleanup_uploads():
    for file_path in _created_uploads.copy():
        file_path.unlink(missing_ok=True)
        _created_uploads.discard(file_path)


atexit.register(cleanup_uploads)


def allowed_image_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


def allowed_video_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_VIDEO_EXTENSIONS


def _display_value(value):
    if isinstance(value, bytes):
        return value.hex(" ")
    if isinstance(value, dict):
        return ", ".join(
            f"{key}: {_display_value(item)}" for key, item in value.items()
        )
    if isinstance(value, (tuple, list)):
        return ", ".join(_display_value(item) for item in value)
    return str(value)


def get_exif_data(image_path):
    try:
        with Image.open(image_path) as image:
            exif = image.getexif()
            if not exif:
                return None

            exif_data = {
                ExifTags.TAGS.get(tag, str(tag)): _display_value(value)
                for tag, value in exif.items()
            }
            gps_info = exif.get_ifd(GPS_IFD_TAG)
            if gps_info:
                exif_data["GPSInfo"] = {
                    ExifTags.GPSTAGS.get(tag, str(tag)): value
                    for tag, value in gps_info.items()
                }
            return exif_data
    except (OSError, ValueError, TypeError, Image.DecompressionBombError):
        return None


def dms_to_decimal(dms):
    try:
        degrees, minutes, seconds = dms
        return float(degrees) + float(minutes) / 60 + float(seconds) / 3600
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def get_gps_coordinates_from_image(exif_data):
    if not exif_data:
        return None, None

    gps_info = exif_data.get("GPSInfo")
    if not isinstance(gps_info, dict):
        return None, None

    latitude = dms_to_decimal(gps_info.get("GPSLatitude", ()))
    longitude = dms_to_decimal(gps_info.get("GPSLongitude", ()))
    if latitude is None or longitude is None:
        return None, None

    if gps_info.get("GPSLatitudeRef") == "S":
        latitude = -latitude
    if gps_info.get("GPSLongitudeRef") == "W":
        longitude = -longitude
    return latitude, longitude


def get_video_metadata(video_path):
    try:
        probe = ffmpeg.probe(video_path)
        video_stream = next(
            (stream for stream in probe["streams"] if stream.get("codec_type") == "video"),
            None,
        )
        if video_stream is None:
            return None

        duration = probe.get("format", {}).get("duration")
        return {
            "width": video_stream.get("width"),
            "height": video_stream.get("height"),
            "duration": float(duration) if duration is not None else None,
        }
    except (ffmpeg.Error, OSError, KeyError, TypeError, ValueError):
        return None


def _render_page(**context):
    return render_template("index.html", **context)


@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(_error):
    return _render_page(error="That file is too large. Choose a file smaller than 16 MB."), 413


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return _render_page()

    uploaded_file = request.files.get("file")
    if uploaded_file is None or not uploaded_file.filename:
        return _render_page(error="Choose an image or video before uploading.")

    original_name = secure_filename(uploaded_file.filename)
    if not original_name:
        return _render_page(error="The selected file has an invalid name.")

    if allowed_image_file(original_name):
        media_type = "image"
    elif allowed_video_file(original_name):
        media_type = "video"
    else:
        return _render_page(
            error="Unsupported file type. Choose a JPG, PNG, MP4, AVI, MOV, or MKV file."
        )

    extension = original_name.rsplit(".", 1)[1].lower()
    filename = f"{uuid4().hex}.{extension}"
    file_path = Path(app.config["UPLOAD_FOLDER"]) / filename
    uploaded_file.save(file_path)
    _created_uploads.add(file_path)
    file_url = url_for("uploaded_file", filename=filename)

    if media_type == "image":
        try:
            with Image.open(file_path) as image:
                image.verify()
        except (
            UnidentifiedImageError,
            OSError,
            ValueError,
            Image.DecompressionBombError,
        ):
            file_path.unlink(missing_ok=True)
            _created_uploads.discard(file_path)
            return _render_page(error="The selected file is not a valid image.")

        exif_data = get_exif_data(file_path)
        if exif_data:
            gps_lat, gps_lon = get_gps_coordinates_from_image(exif_data)
            google_maps_url = (
                f"https://www.google.com/maps?q={gps_lat},{gps_lon}"
                if gps_lat is not None and gps_lon is not None
                else None
            )
            return _render_page(
                exif_data=exif_data,
                gps_lat=gps_lat,
                gps_lon=gps_lon,
                google_maps_url=google_maps_url,
                file_url=file_url,
                media_type=media_type,
                filename=original_name,
            )
        return _render_page(
            error="This image is valid, but it does not contain readable EXIF metadata.",
            file_url=file_url,
            media_type=media_type,
            filename=original_name,
        )

    video_metadata = get_video_metadata(file_path)
    if video_metadata is None:
        file_path.unlink(missing_ok=True)
        _created_uploads.discard(file_path)
        return _render_page(
            error="The selected file is not a supported video or its metadata could not be read."
        )
    return _render_page(
        video_metadata=video_metadata,
        file_url=file_url,
        media_type=media_type,
        filename=original_name,
    )


@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0")
