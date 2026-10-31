# EXIF Studio

A local Flask app for reviewing image EXIF/GPS data and basic video metadata.

## Run locally

```powershell
python -m pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`. The app binds to localhost and is intended for a
single local user. It has no accounts or per-user access controls; do not expose
it on a network or deploy it publicly until authentication and upload ownership
are implemented. Video metadata extraction also requires the FFmpeg `ffprobe`
executable to be installed and available on `PATH`.

## Uploads and privacy

- Images: JPG, JPEG, PNG
- Videos: MP4, AVI, MOV, MKV
- Up to 10 files per batch, 16 MB per file, and 64 MB per request

Uploads and extracted metadata are stored locally so they remain available after
the app restarts. They stay there until you use **Delete** for each file.
Deleting a file removes its stored media and metadata. The original media is
not modified. Metadata may contain personal information, including device
details and location; review it before sharing.

The app generates a temporary session secret when `FLASK_SECRET_KEY` is not
configured. Set that environment variable to a securely generated, stable value
if you need browser sessions to survive app restarts. This does not make the
app safe for shared or public hosting.

## Run tests

```powershell
python -m unittest discover -s tests -v
```
