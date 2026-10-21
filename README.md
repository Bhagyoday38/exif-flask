# Image & Video Metadata Extractor

A small Flask app for viewing image EXIF/GPS metadata and basic video stream
metadata.

## Run locally

```powershell
python -m pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`. Video metadata extraction also requires the
FFmpeg `ffprobe` executable to be installed and available on `PATH`.

## Supported files

- Images: JPG, JPEG, PNG
- Videos: MP4, AVI, MOV, MKV
- Maximum upload size: 16 MB

Files are stored in `uploads/` so the browser can show a preview. Files uploaded
by the running app are removed on normal shutdown; files already present in that
folder are left untouched. Image and video metadata may include personal
information, including device details and location.

## Run tests

```powershell
python -m unittest discover -s tests -v
```
