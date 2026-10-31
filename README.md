# EXIF Studio

A local Flask app for reviewing image EXIF/GPS data and basic video metadata.

## Run locally

```powershell
python -m pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`. Create an account to start a private library.
Usernames are case-insensitive and use 3–32 letters, numbers, or underscores;
passwords must be 12–128 characters. Passwords are stored as scrypt hashes.
Sign-in attempts are rate-limited per username and client address. The app
binds to localhost by default; before network deployment, configure HTTPS,
`FLASK_SECRET_KEY`, and `SESSION_COOKIE_SECURE=true`, and use a production WSGI
server. Video metadata extraction also requires the FFmpeg `ffprobe` executable
to be installed and available on `PATH`.

## Uploads and privacy

- Images: JPG, JPEG, PNG
- Videos: MP4, AVI, MOV, MKV
- Up to 10 files per batch, 16 MB per file, and 64 MB per request

Uploads and extracted metadata are stored locally and associated with the
account that uploaded them. Only that account can list, preview, or delete its
files. They stay there until you use **Delete** for each file. Deleting a file
removes its stored media and metadata. The original media is not modified.
Metadata may contain personal information, including device details and
location; review it before sharing.

On the first request after upgrading, records without an owner and their media
files are deleted rather than assigned to the first account.

The app generates a temporary session secret when `FLASK_SECRET_KEY` is not
configured. Set that environment variable to a securely generated, stable value
so users can remain signed in after app restarts. Localhost is the only supported
deployment by default; account isolation does not replace HTTPS or other
production controls.

## Run tests

```powershell
python -m unittest discover -s tests -v
```
