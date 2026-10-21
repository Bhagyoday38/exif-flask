import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import app


class MetadataExtractorTests(unittest.TestCase):
    def setUp(self):
        self.upload_dir = tempfile.TemporaryDirectory()
        app.app.config.update(
            TESTING=True,
            UPLOAD_FOLDER=self.upload_dir.name,
            MAX_CONTENT_LENGTH=app.MAX_CONTENT_LENGTH,
        )
        self.client = app.app.test_client()

    def tearDown(self):
        self.upload_dir.cleanup()

    @staticmethod
    def image_file(format_name="JPEG", exif=None):
        image = Image.new("RGB", (2, 2), color="white")
        content = io.BytesIO()
        image.save(content, format=format_name, exif=exif or b"")
        content.seek(0)
        return content

    def test_png_exif_is_extracted(self):
        exif = Image.Exif()
        exif[271] = "Test camera"
        response = self.client.post(
            "/",
            data={"file": (self.image_file("PNG", exif.tobytes()), "photo.png")},
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Test camera", response.data)
        self.assertIn(b"EXIF metadata", response.data)

    def test_zero_gps_coordinates_are_valid(self):
        coordinates = app.get_gps_coordinates_from_image(
            {
                "GPSInfo": {
                    "GPSLatitude": (0, 0, 0),
                    "GPSLongitude": (0, 0, 0),
                }
            }
        )

        self.assertEqual(coordinates, (0, 0))

    def test_south_and_west_coordinates_are_negative(self):
        coordinates = app.get_gps_coordinates_from_image(
            {
                "GPSInfo": {
                    "GPSLatitude": (12, 30, 0),
                    "GPSLatitudeRef": "S",
                    "GPSLongitude": (45, 15, 0),
                    "GPSLongitudeRef": "W",
                }
            }
        )

        self.assertEqual(coordinates, (-12.5, -45.25))

    @patch("app.ffmpeg.probe", side_effect=FileNotFoundError)
    def test_missing_ffprobe_is_reported_as_unavailable_metadata(self, _probe):
        self.assertIsNone(app.get_video_metadata("missing-video.mp4"))

    def test_invalid_image_is_rejected_and_removed(self):
        response = self.client.post(
            "/",
            data={"file": (io.BytesIO(b"not an image"), "photo.jpg")},
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"not a valid image", response.data)
        self.assertEqual(list(Path(self.upload_dir.name).iterdir()), [])

    def test_unsupported_extension_is_not_saved(self):
        response = self.client.post(
            "/",
            data={"file": (io.BytesIO(b"payload"), "document.txt")},
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Unsupported file type", response.data)
        self.assertEqual(list(Path(self.upload_dir.name).iterdir()), [])

    def test_identical_filenames_do_not_overwrite_each_other(self):
        for color in ("red", "blue"):
            image = Image.new("RGB", (2, 2), color=color)
            content = io.BytesIO()
            image.save(content, format="JPEG")
            content.seek(0)
            response = self.client.post(
                "/",
                data={"file": (content, "same-name.jpg")},
                content_type="multipart/form-data",
            )
            self.assertEqual(response.status_code, 200)

        self.assertEqual(len(list(Path(self.upload_dir.name).iterdir())), 2)

    def test_cleanup_removes_only_files_created_by_the_app(self):
        existing = Path(self.upload_dir.name) / "keep.txt"
        existing.write_text("keep", encoding="utf-8")
        self.client.post(
            "/",
            data={"file": (self.image_file(), "photo.jpg")},
            content_type="multipart/form-data",
        )

        app.cleanup_uploads()

        self.assertEqual(existing.read_text(encoding="utf-8"), "keep")
        self.assertEqual(list(Path(self.upload_dir.name).iterdir()), [existing])


if __name__ == "__main__":
    unittest.main()
