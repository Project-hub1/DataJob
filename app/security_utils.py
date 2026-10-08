from zipfile import BadZipFile, ZipFile


def validate_upload(data: bytes, extension: str, *, max_size: int) -> tuple[bool, str]:
    if not data:
        return False, 'The selected file is empty.'
    if len(data) > max_size:
        return False, 'The selected file is too large.'
    ext = extension.lower().lstrip('.')
    signatures = {
        'pdf': data.startswith(b'%PDF-'),
        'jpg': data.startswith(b'\xff\xd8\xff'),
        'jpeg': data.startswith(b'\xff\xd8\xff'),
        'png': data.startswith(b'\x89PNG\r\n\x1a\n'),
        'webp': data.startswith(b'RIFF') and len(data) >= 12 and data[8:12] == b'WEBP',
        'doc': data.startswith(bytes.fromhex('D0CF11E0A1B11AE1')),
    }
    if ext in {'docx'}:
        try:
            with ZipFile(__import__('io').BytesIO(data)) as archive:
                names = set(archive.namelist())
                valid = '[Content_Types].xml' in names and 'word/document.xml' in names
        except (BadZipFile, OSError):
            valid = False
        signatures['docx'] = valid
    if not signatures.get(ext, False):
        return False, 'The file content does not match the selected file type.'
    return True, ''
