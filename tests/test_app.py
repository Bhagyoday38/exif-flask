import io
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import app


class MetadataAppTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        root = Path(self.temporary_directory.name)
        app.app.config.update(
            TESTING=True,
            SECRET_KEY="test-secret",
            UPLOAD_FOLDER=str(root / "uploads"),
            DATABASE=str(root / "metadata.sqlite"),
        )
        self.client = app.app.test_client()
        self._register(self.client, "alice", "correct horse battery")

    def _csrf_token(self, client=None):
        selected_client = client or self.client
        response = selected_client.get("/")
        if response.status_code == 302:
            response = selected_client.get(response.location)
        match = re.search(
            rb'name="csrf_token" value="([^"]+)"',
            response.data,
        )
        self.assertIsNotNone(match, "The page should include a CSRF token.")
        return match.group(1).decode()

    def _register(self, client, username, password):
        response = client.post(
            "/register",
            data={
                "csrf_token": self._csrf_token(client),
                "username": username,
                "password": password,
            },
        )
        self.assertEqual(response.status_code, 302)
        return response

    def _login(self, client, username, password):
        return client.post(
            "/login",
            data={
                "csrf_token": self._csrf_token(client),
                "username": username,
                "password": password,
            },
        )

    @staticmethod
    def _image(name, color):
        image_bytes = io.BytesIO()
        Image.new("RGB", (4, 4), color).save(image_bytes, format="JPEG")
        image_bytes.seek(0)
        return image_bytes, name

    @staticmethod
    def _image_with_exif(name):
        image_bytes = io.BytesIO()
        exif = Image.Exif()
        exif[270] = "Camera test description"
        Image.new("RGB", (4, 4), "orange").save(
            image_bytes,
            format="JPEG",
            exif=exif,
        )
        image_bytes.seek(0)
        return image_bytes, name

    def test_upload_page_supports_multiple_files_and_explains_persistence(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'name="files"', response.data)
        self.assertIn(b"multiple", response.data)
        self.assertIn(b"until you delete", response.data.lower())
        for asset_path in ("/static/app.js", "/static/style.css"):
            asset_response = self.client.get(asset_path)
            self.assertEqual(asset_response.status_code, 200)
            asset_response.close()

    def test_anonymous_users_are_redirected_to_login(self):
        anonymous_client = app.app.test_client()

        response = anonymous_client.get("/")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith("/login"))

    def test_anonymous_users_cannot_access_media_and_unknown_routes_stay_not_found(self):
        anonymous_client = app.app.test_client()

        media_response = anonymous_client.get(f"/uploads/{'a' * 32}")
        missing_route_response = anonymous_client.get("/missing")

        self.assertEqual(media_response.status_code, 302)
        self.assertEqual(missing_route_response.status_code, 404)

    def test_registration_rejects_duplicate_usernames_case_insensitively(self):
        anonymous_client = app.app.test_client()
        response = anonymous_client.post(
            "/register",
            data={
                "csrf_token": self._csrf_token(anonymous_client),
                "username": "Alice",
                "password": "another secure password",
            },
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn(b"username is unavailable", response.data.lower())

    def test_registration_requires_a_long_password_and_valid_username(self):
        anonymous_client = app.app.test_client()
        response = anonymous_client.post(
            "/register",
            data={
                "csrf_token": self._csrf_token(anonymous_client),
                "username": "invalid name",
                "password": "short",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"username", response.data.lower())
        self.assertIn("12–128 characters".encode(), response.data)

    def test_passwords_are_stored_as_hashes(self):
        with app._database_connection() as connection:
            row = connection.execute(
                "SELECT password_hash FROM users WHERE username = ?",
                ("alice",),
            ).fetchone()

        self.assertNotEqual(row["password_hash"], "correct horse battery")
        self.assertTrue(row["password_hash"].startswith("scrypt:"))

    def test_login_is_rate_limited_after_repeated_failures(self):
        anonymous_client = app.app.test_client()
        csrf_token = self._csrf_token(anonymous_client)
        for _ in range(app.MAX_LOGIN_ATTEMPTS):
            response = anonymous_client.post(
                "/login",
                data={
                    "csrf_token": csrf_token,
                    "username": "alice",
                    "password": "incorrect password",
                },
            )
            self.assertEqual(response.status_code, 401)

        response = anonymous_client.post(
            "/login",
            data={
                "csrf_token": csrf_token,
                "username": "alice",
                "password": "correct horse battery",
            },
        )

        self.assertEqual(response.status_code, 429)

    def test_users_cannot_view_or_delete_each_others_uploads(self):
        upload_response = self.client.post(
            "/",
            data={
                "csrf_token": self._csrf_token(),
                "files": [self._image("alice-private.jpg", "red")],
            },
            content_type="multipart/form-data",
        )
        results = self.client.get(upload_response.location)
        image_match = re.search(rb'<img src="(/uploads/([a-f0-9]{32}))"', results.data)
        self.assertIsNotNone(image_match)
        image_url = image_match.group(1).decode()
        upload_id = image_match.group(2).decode()

        bob = app.app.test_client()
        self._register(bob, "bob", "another secure password")

        self.assertNotIn(b"alice-private.jpg", bob.get("/").data)
        self.assertEqual(bob.get(image_url).status_code, 404)
        delete_response = bob.post(
            f"/uploads/{upload_id}/delete",
            data={"csrf_token": self._csrf_token(bob)},
        )
        self.assertEqual(delete_response.status_code, 404)
        self.assertIn(b"alice-private.jpg", self.client.get("/").data)

    def test_login_logout_and_protected_library(self):
        self.client.post("/logout", data={"csrf_token": self._csrf_token()})
        self.assertEqual(self.client.get("/").status_code, 302)

        login_response = self._login(
            self.client,
            "ALICE",
            "correct horse battery",
        )
        self.assertEqual(login_response.status_code, 302)
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_legacy_unowned_uploads_are_deleted_during_migration(self):
        upload_id = "a" * 32
        stored_filename = f"{upload_id}.jpg"
        upload_directory = Path(app.app.config["UPLOAD_FOLDER"])
        upload_directory.mkdir(parents=True, exist_ok=True)
        stored_file = upload_directory / stored_filename
        stored_file.write_bytes(b"legacy private image")
        with app._database_connection() as connection:
            connection.execute("DROP TABLE uploads")
            connection.execute(
                """
                CREATE TABLE uploads (
                    id TEXT PRIMARY KEY,
                    stored_filename TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                INSERT INTO uploads
                    (id, stored_filename, display_name, media_type, metadata_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (upload_id, stored_filename, "legacy.jpg", "image", "{}"),
            )

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(stored_file.exists())
        with app._database_connection() as connection:
            rows = connection.execute("SELECT id FROM uploads").fetchall()
        self.assertEqual(rows, [])

    def test_uploading_multiple_images_shows_each_result_after_redirect(self):
        response = self.client.post(
            "/",
            data={
                "csrf_token": self._csrf_token(),
                "files": [
                    self._image("first.jpg", "red"),
                    self._image("second.jpg", "blue"),
                ],
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 302)
        results = self.client.get(response.location)
        self.assertEqual(results.status_code, 200)
        self.assertIn(b"first.jpg", results.data)
        self.assertIn(b"second.jpg", results.data)
        self.assertEqual(results.data.count(b'class="result-item"'), 2)

    def test_exif_values_are_stored_and_shown_per_image(self):
        response = self.client.post(
            "/",
            data={
                "csrf_token": self._csrf_token(),
                "files": [self._image_with_exif("with-metadata.jpg")],
            },
            content_type="multipart/form-data",
        )

        results = self.client.get(response.location)
        self.assertIn(b"ImageDescription", results.data)
        self.assertIn(b"Camera test description", results.data)

    def test_video_metadata_remains_available(self):
        with patch(
            "app.get_video_metadata",
            return_value={"width": 1920, "height": 1080, "duration": 12.5},
        ):
            response = self.client.post(
                "/",
                data={
                    "csrf_token": self._csrf_token(),
                    "files": [(io.BytesIO(b"video"), "clip.mp4")],
                },
                content_type="multipart/form-data",
            )

        results = self.client.get(response.location)
        self.assertIn(b"clip.mp4", results.data)
        self.assertIn(b"1920", results.data)
        self.assertIn(b"12.50 seconds", results.data)

    def test_gps_coordinates_parse_displayed_exif_values(self):
        coordinates = app.get_gps_coordinates_from_image(
            {
                "GPSInfo": {
                    "GPSLatitude": "37.0, 48.0, 15.0",
                    "GPSLatitudeRef": "S",
                    "GPSLongitude": "122.0, 24.0, 30.0",
                    "GPSLongitudeRef": "W",
                }
            }
        )

        self.assertAlmostEqual(coordinates[0], -37.8041667)
        self.assertAlmostEqual(coordinates[1], -122.4083333)

    def test_upload_requires_a_csrf_token(self):
        response = self.client.post(
            "/",
            data={"files": [self._image("image.jpg", "red")]},
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 400)

    def test_uploaded_file_is_retained_and_can_be_deleted(self):
        response = self.client.post(
            "/",
            data={
                "csrf_token": self._csrf_token(),
                "files": [self._image("image.jpg", "red")],
            },
            content_type="multipart/form-data",
        )
        results = self.client.get(response.location)
        image_match = re.search(rb'<img src="(/uploads/([a-f0-9]{32}))"', results.data)
        self.assertIsNotNone(image_match)
        image_url = image_match.group(1).decode()
        upload_id = image_match.group(2).decode()

        image_response = self.client.get(image_url)
        self.assertEqual(image_response.status_code, 200)
        image_response.close()
        refreshed_client = app.app.test_client()
        self._register(refreshed_client, "carol", "first account password")
        retained_results = refreshed_client.get("/")
        self.assertNotIn(b"image.jpg", retained_results.data)
        login_client = app.app.test_client()
        self._login(login_client, "alice", "correct horse battery")
        retained_results = login_client.get("/")
        self.assertIn(b"image.jpg", retained_results.data)

        rejected_delete = refreshed_client.post(
            f"/uploads/{upload_id}/delete",
            data={"csrf_token": "invalid"},
        )
        self.assertEqual(rejected_delete.status_code, 400)
        retained_image_response = login_client.get(image_url)
        self.assertEqual(retained_image_response.status_code, 200)
        retained_image_response.close()

        delete_response = refreshed_client.post(
            f"/uploads/{upload_id}/delete",
            data={"csrf_token": self._csrf_token(refreshed_client)},
        )
        self.assertEqual(delete_response.status_code, 404)
        owner_delete = login_client.post(
            f"/uploads/{upload_id}/delete",
            data={"csrf_token": self._csrf_token(login_client)},
        )
        self.assertEqual(owner_delete.status_code, 302)
        self.assertEqual(login_client.get(image_url).status_code, 404)
        login_client.get("/")
        self.assertNotIn(b"image.jpg", login_client.get("/").data)

    def test_invalid_images_are_rejected_without_storing_them(self):
        response = self.client.post(
            "/",
            data={
                "csrf_token": self._csrf_token(),
                "files": [
                    (io.BytesIO(b"not an image"), "spoofed.jpg"),
                    self._image("valid.jpg", "green"),
                ],
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )

        self.assertIn(b"not a safe, valid image", response.data)
        self.assertEqual(response.data.count(b'class="result-item"'), 1)
        self.assertEqual(len(list((Path(app.app.config["UPLOAD_FOLDER"])).iterdir())), 1)

    def test_upload_rejects_files_over_the_per_file_limit(self):
        with patch.object(app, "MAX_FILE_SIZE", 4):
            response = self.client.post(
                "/",
                data={
                    "csrf_token": self._csrf_token(),
                    "files": [self._image("large.jpg", "yellow")],
                },
                content_type="multipart/form-data",
                follow_redirects=True,
            )

        self.assertIn(b"Each file must be smaller than 16 MB", response.data)
        self.assertNotIn(b'class="result-item"', response.data)
        self.assertEqual(len(list(Path(app.app.config["UPLOAD_FOLDER"]).iterdir())), 0)

    def test_request_size_limit_returns_a_clear_error(self):
        with patch.dict(app.app.config, {"MAX_CONTENT_LENGTH": 128}):
            response = self.client.post(
                "/",
                data={
                    "csrf_token": self._csrf_token(),
                    "files": [self._image("too-large.jpg", "purple")],
                },
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 413)
        self.assertIn(b"upload is too large", response.data)

    def test_upload_rejects_batches_over_the_file_count_limit(self):
        with patch.object(app, "MAX_BATCH_FILES", 1):
            response = self.client.post(
                "/",
                data={
                    "csrf_token": self._csrf_token(),
                    "files": [
                        self._image("first.jpg", "red"),
                        self._image("second.jpg", "blue"),
                    ],
                },
                content_type="multipart/form-data",
                follow_redirects=True,
            )

        self.assertIn(b"Choose no more than 1 file", response.data)
        self.assertNotIn(b'class="result-item"', response.data)
        upload_directory = Path(app.app.config["UPLOAD_FOLDER"])
        self.assertFalse(upload_directory.exists() and any(upload_directory.iterdir()))

    def test_unrecognized_upload_ids_are_not_served(self):
        response = self.client.get("/uploads/not-a-valid-id")

        self.assertEqual(response.status_code, 404)

    def test_responses_include_security_headers(self):
        response = self.client.get("/")

        self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(response.headers.get("X-Frame-Options"), "DENY")
        self.assertIn("default-src 'self'", response.headers.get("Content-Security-Policy", ""))


if __name__ == "__main__":
    unittest.main()
