import pytest

from mission_control.core.uploads import UploadError, safe_join, validate_upload


def test_safe_join_allows_normal_path(tmp_path):
    out = safe_join(tmp_path, "Weapons/Pulse.ogg")
    assert out == (tmp_path / "Weapons/Pulse.ogg").resolve()


@pytest.mark.parametrize("evil", ["../etc/passwd", "../../secret", "Weapons/../../escape"])
def test_safe_join_rejects_traversal(tmp_path, evil):
    with pytest.raises(UploadError):
        safe_join(tmp_path, evil)


def test_validate_upload_accepts_good_file():
    validate_upload(
        filename="ambient.ogg",
        size=1024,
        content_type="audio/ogg",
        allowed_extensions={".ogg"},
        allowed_content_types={"audio/ogg"},
        max_bytes=10_000,
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(filename="ambient.exe", size=10, content_type="audio/ogg"),       # bad ext
        dict(filename="ambient.ogg", size=0, content_type="audio/ogg"),        # empty
        dict(filename="ambient.ogg", size=10_001, content_type="audio/ogg"),   # too big
        dict(filename="ambient.ogg", size=10, content_type="text/plain"),      # bad ctype
        dict(filename="", size=10, content_type="audio/ogg"),                  # no name
    ],
)
def test_validate_upload_rejects_bad_files(kwargs):
    with pytest.raises(UploadError):
        validate_upload(
            allowed_extensions={".ogg"},
            allowed_content_types={"audio/ogg"},
            max_bytes=10_000,
            **kwargs,
        )
