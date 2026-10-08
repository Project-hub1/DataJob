from app.security_utils import validate_upload


def test_upload_signature_validation():
    ok, _ = validate_upload(b'%PDF-1.7\n', 'pdf', max_size=1024)
    assert ok
    ok, _ = validate_upload(b'not-a-pdf', 'pdf', max_size=1024)
    assert not ok


def test_upload_size_limit():
    ok, _ = validate_upload(b'%PDF-' + b'x' * 20, 'pdf', max_size=10)
    assert not ok
