import json
import os
from contextlib import contextmanager
from pathlib import Path
import re
import secrets
import sqlite3
import warnings
from uuid import uuid4

import ffmpeg
from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from PIL import ExifTags, Image, UnidentifiedImageError
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename

app = Flask(__name__)

ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png"}
ALLOWED_VIDEO_EXTENSIONS = {"mp4", "avi", "mov", "mkv"}
MAX_FILE_SIZE = 16 * 1024 * 1024
MAX_BATCH_FILES = 10
MAX_CONTENT_LENGTH = 64 * 1024 * 1024
UPLOAD_ID_PATTERN = re.compile(r"[a-f0-9]{32}\Z")

app.config.update(
    MAX_CONTENT_LENGTH=MAX_CONTENT_LENGTH,
    UPLOAD_FOLDER=str(Path(app.root_path) / "uploads"),
    DATABASE=str(Path(app.instance_path) / "metadata.sqlite"),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "").lower() == "true",
    SESSION_COOKIE_SAMESITE="Lax",
)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)
Path(app.instance_path).mkdir(parents=True, exist_ok=True)
Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

GPS_IFD_TAG = 34853


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
                    ExifTags.GPSTAGS.get(tag, str(tag)): _display_value(value)
                    for tag, value in gps_info.items()
                }
            return exif_data
    except (
        OSError,
        ValueError,
        TypeError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        return None


def dms_to_decimal(dms):
    try:
        if isinstance(dms, str):
            dms = [part.strip() for part in dms.split(",")]
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
    return render_template(
        "index.html",
        uploads=_list_uploads(),
        csrf_token=_get_csrf_token(),
        max_file_size=MAX_FILE_SIZE,
        max_batch_files=MAX_BATCH_FILES,
        max_total_size=MAX_CONTENT_LENGTH,
        **context,
    )


def _connect_database():
    connection = sqlite3.connect(app.config["DATABASE"])
    connection.row_factory = sqlite3.Row
    return connection


@contextmanager
def _database_connection():
    connection = _connect_database()
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def _initialize_database():
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
    with _database_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS uploads (
                id TEXT PRIMARY KEY,
                stored_filename TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                media_type TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


@app.before_request
def initialize_database():
    if request.endpoint != "static":
        _initialize_database()


def _get_csrf_token():
    token = session.get("csrf_token")
    if not isinstance(token, str):
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def _validate_csrf_token():
    submitted_token = request.form.get("csrf_token", "")
    expected_token = session.get("csrf_token", "")
    if not expected_token or not secrets.compare_digest(
        submitted_token, expected_token
    ):
        abort(400)


def _list_uploads():
    with _database_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, stored_filename, display_name, media_type,
                   metadata_json, created_at
            FROM uploads
            ORDER BY rowid DESC
            """
        ).fetchall()
    uploads = []
    for row in rows:
        item = dict(row)
        item["metadata"] = json.loads(item.pop("metadata_json"))
        item["file_url"] = url_for("uploaded_file", upload_id=item["id"])
        uploads.append(item)
    return uploads


def _get_upload(upload_id):
    with _database_connection() as connection:
        row = connection.execute(
            """
            SELECT id, stored_filename, display_name, media_type,
                   metadata_json, created_at
            FROM uploads
            WHERE id = ?
            """,
            (upload_id,),
        ).fetchone()
    if row is None:
        return None
    item = dict(row)
    item["metadata"] = json.loads(item.pop("metadata_json"))
    return item


def _image_metadata(file_path):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(file_path) as image:
                image.verify()
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as error:
        raise ValueError("This file is not a safe, valid image.") from error

    exif_data = get_exif_data(file_path)
    gps_lat, gps_lon = get_gps_coordinates_from_image(exif_data)
    google_maps_url = (
        f"https://www.google.com/maps?q={gps_lat},{gps_lon}"
        if gps_lat is not None and gps_lon is not None
        else None
    )
    return {
        "exif_data": exif_data,
        "gps_lat": gps_lat,
        "gps_lon": gps_lon,
        "google_maps_url": google_maps_url,
        "video_metadata": None,
        "message": (
            "This image does not contain readable EXIF metadata."
            if not exif_data
            else None
        ),
    }


def _video_metadata(file_path):
    metadata = get_video_metadata(file_path)
    if metadata is None:
        raise ValueError(
            "This file is not a supported video or its metadata could not be read."
        )
    return {
        "exif_data": None,
        "gps_lat": None,
        "gps_lon": None,
        "google_maps_url": None,
        "video_metadata": metadata,
        "message": None,
    }


def _process_upload(uploaded_file):
    display_name = secure_filename(uploaded_file.filename or "")
    if not display_name:
        raise ValueError("The selected file has an invalid name.")

    extension = display_name.rsplit(".", 1)[-1].lower()
    if "." not in display_name or (
        extension not in ALLOWED_IMAGE_EXTENSIONS
        and extension not in ALLOWED_VIDEO_EXTENSIONS
    ):
        raise ValueError(
            "Unsupported file type. Choose a JPG, PNG, MP4, AVI, MOV, or MKV file."
        )

    media_type = (
        "image" if extension in ALLOWED_IMAGE_EXTENSIONS else "video"
    )
    upload_id = uuid4().hex
    stored_filename = f"{upload_id}.{extension}"
    upload_root = Path(app.config["UPLOAD_FOLDER"])
    upload_root.mkdir(parents=True, exist_ok=True)
    file_path = upload_root / stored_filename

    stored = False
    try:
        uploaded_file.save(file_path)
        if file_path.stat().st_size > MAX_FILE_SIZE:
            raise ValueError("Each file must be smaller than 16 MB.")

        metadata = (
            _image_metadata(file_path)
            if media_type == "image"
            else _video_metadata(file_path)
        )
        with _database_connection() as connection:
            connection.execute(
                """
                INSERT INTO uploads
                    (id, stored_filename, display_name, media_type, metadata_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    upload_id,
                    stored_filename,
                    display_name,
                    media_type,
                    json.dumps(metadata),
                ),
            )
        stored = True
        return upload_id
    finally:
        if not stored:
            file_path.unlink(missing_ok=True)


@app.after_request
def add_security_headers(response):
    response.headers.setdefault("Content-Security-Policy", (
        "default-src 'self'; img-src 'self'; media-src 'self'; "
        "object-src 'none'; base-uri 'self'; form-action 'self'; "
        "frame-ancestors 'none'"
    ))
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault(
        "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
    )
    response.headers.setdefault("Cache-Control", "private, no-store")
    return response


@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(_error):
    return (
        _render_page(
            error="The upload is too large. Choose up to 10 files with a combined size under 64 MB."
        ),
        413,
    )


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return _render_page()

    _validate_csrf_token()
    uploaded_files = request.files.getlist("files")
    if not uploaded_files or not any(file.filename for file in uploaded_files):
        flash("Choose at least one image or video before uploading.", "error")
        return redirect(url_for("index"))
    if len(uploaded_files) > MAX_BATCH_FILES:
        file_label = "file" if MAX_BATCH_FILES == 1 else "files"
        flash(
            f"Choose no more than {MAX_BATCH_FILES} {file_label} at a time.",
            "error",
        )
        return redirect(url_for("index"))

    for uploaded_file in uploaded_files:
        if not uploaded_file.filename:
            continue
        try:
            _process_upload(uploaded_file)
        except ValueError as error:
            flash(f"{secure_filename(uploaded_file.filename)}: {error}", "error")
    return redirect(url_for("index"))


@app.route("/uploads/<upload_id>")
def uploaded_file(upload_id):
    if not UPLOAD_ID_PATTERN.fullmatch(upload_id):
        abort(404)
    upload = _get_upload(upload_id)
    if upload is None:
        abort(404)
    file_path = _stored_file_path(upload["stored_filename"])
    if not file_path.is_file():
        abort(404)
    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        upload["stored_filename"],
        conditional=True,
    )


@app.post("/uploads/<upload_id>/delete")
def delete_uploaded_file(upload_id):
    _validate_csrf_token()
    if not UPLOAD_ID_PATTERN.fullmatch(upload_id):
        abort(404)
    upload = _get_upload(upload_id)
    if upload is None:
        abort(404)

    file_path = _stored_file_path(upload["stored_filename"])
    try:
        file_path.unlink(missing_ok=True)
    except OSError:
        app.logger.exception("Failed to delete a stored upload.")
        abort(500)

    with _database_connection() as connection:
        connection.execute("DELETE FROM uploads WHERE id = ?", (upload_id,))
    flash(f"Deleted {upload['display_name']}.", "success")
    return redirect(url_for("index"))


def _stored_file_path(stored_filename):
    upload_root = Path(app.config["UPLOAD_FOLDER"]).resolve()
    if Path(stored_filename).name != stored_filename:
        app.logger.error("Refusing an upload path outside the upload directory.")
        abort(404)
    file_path = upload_root / stored_filename
    if file_path.parent.resolve() != upload_root or file_path.is_symlink():
        app.logger.error("Refusing an upload path outside the upload directory.")
        abort(404)
    return file_path


if __name__ == "__main__":
    app.run(debug=False, host="127.0.0.1")
