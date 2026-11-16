import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import app as app_module


class ImageUploadTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_config = {
            key: app_module.app.config[key]
            for key in (
                "DATABASE",
                "UPLOAD_FOLDER",
                "SECRET_KEY",
                "TESTING",
                "MAX_CONTENT_LENGTH",
            )
        }
        app_module.app.config.update(
            DATABASE=str(Path(self.temp_dir.name) / "metadata.sqlite"),
            UPLOAD_FOLDER=str(Path(self.temp_dir.name) / "uploads"),
            SECRET_KEY="test-secret",
            TESTING=True,
        )
        app_module._initialize_database()
        with app_module._database_connection() as connection:
            connection.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                ("test_user", "unused"),
            )

        self.client = app_module.app.test_client()
        with self.client.session_transaction() as session:
            session["user_id"] = 1
            session["csrf_token"] = "test-token"

    def tearDown(self):
        app_module.app.config.update(self.original_config)
        self.temp_dir.cleanup()

    @staticmethod
    def make_image(image_format):
        image_data = io.BytesIO()
        Image.new("RGB", (2, 2), "white").save(image_data, format=image_format)
        image_data.seek(0)
        return image_data

    def upload(self, image_data, filename):
        return self.client.post(
            "/",
            data={
                "csrf_token": "test-token",
                "files": (image_data, filename),
            },
            follow_redirects=True,
        )

    def upload_count(self):
        with app_module._database_connection() as connection:
            return connection.execute("SELECT COUNT(*) FROM uploads").fetchone()[0]

    def test_rejects_image_content_that_does_not_match_extension(self):
        response = self.upload(self.make_image("BMP"), "photo.jpg")

        self.assertIn("This file is not a safe, valid image.", response.get_data(as_text=True))
        self.assertEqual(self.upload_count(), 0)
        self.assertEqual(list(Path(app_module.app.config["UPLOAD_FOLDER"]).iterdir()), [])

    def test_accepts_jpeg_with_matching_extension(self):
        self.upload(self.make_image("JPEG"), "photo.jpg")

        self.assertEqual(self.upload_count(), 1)

    def test_oversized_request_returns_payload_too_large(self):
        app_module.app.config["MAX_CONTENT_LENGTH"] = 256
        response = self.client.post(
            "/",
            data={"csrf_token": "test-token", "files": (io.BytesIO(b"x" * 512), "photo.jpg")},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 413)

    def test_form_limit_is_file_total_not_multipart_request_limit(self):
        response = self.client.get("/")

        self.assertGreater(app_module.MAX_CONTENT_LENGTH, app_module.MAX_TOTAL_FILE_SIZE)
        self.assertIn(
            f'data-max-total-size="{app_module.MAX_TOTAL_FILE_SIZE}"',
            response.get_data(as_text=True),
        )

    def test_video_probe_uses_a_timeout_and_reads_metadata(self):
        probe_result = {
            "streams": [{"codec_type": "video", "width": 1920, "height": 1080}],
            "format": {"duration": "12.5"},
        }
        with patch(
            "subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=["ffprobe"], returncode=0, stdout=json.dumps(probe_result), stderr=""
            ),
        ) as run:
            metadata = app_module.get_video_metadata("clip.mp4")

        self.assertEqual(
            metadata,
            {"width": 1920, "height": 1080, "duration": 12.5},
        )
        self.assertEqual(
            run.call_args.kwargs["timeout"],
            app_module.VIDEO_PROBE_TIMEOUT_SECONDS,
        )

    def test_video_probe_timeout_returns_no_metadata(self):
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired("ffprobe", 15),
        ) as run:
            metadata = app_module.get_video_metadata("clip.mp4")

        self.assertIsNone(metadata)
        run.assert_called_once()

    def test_gps_coordinates_require_valid_ranges_and_references(self):
        invalid_gps_values = (
            {
                "GPSLatitude": (91, 0, 0),
                "GPSLatitudeRef": "N",
                "GPSLongitude": (0, 0, 0),
                "GPSLongitudeRef": "E",
            },
            {
                "GPSLatitude": (0, 0, 0),
                "GPSLatitudeRef": "N",
                "GPSLongitude": (181, 0, 0),
                "GPSLongitudeRef": "E",
            },
            {
                "GPSLatitude": (0, 60, 0),
                "GPSLatitudeRef": "N",
                "GPSLongitude": (0, 0, 0),
                "GPSLongitudeRef": "E",
            },
            {
                "GPSLatitude": (0, 0, 0),
                "GPSLongitude": (0, 0, 0),
                "GPSLongitudeRef": "E",
            },
        )

        for gps_info in invalid_gps_values:
            with self.subTest(gps_info=gps_info):
                coordinates = app_module.get_gps_coordinates_from_image(
                    {"GPSInfo": gps_info}
                )
                self.assertEqual(coordinates, (None, None))

    def test_gps_coordinates_preserve_southern_and_western_signs(self):
        coordinates = app_module.get_gps_coordinates_from_image(
            {
                "GPSInfo": {
                    "GPSLatitude": (37, 30, 0),
                    "GPSLatitudeRef": "S",
                    "GPSLongitude": (122, 15, 0),
                    "GPSLongitudeRef": "W",
                }
            }
        )

        self.assertEqual(coordinates, (-37.5, -122.25))


if __name__ == "__main__":
    unittest.main()
