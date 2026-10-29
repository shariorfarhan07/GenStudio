import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

from app.config import get_settings

router = APIRouter(prefix="/api/uploads", tags=["uploads"])


@router.post("")
async def upload_file(file: UploadFile):
    cfg = get_settings()
    upload_dir = cfg.data_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(file.filename or "file.png").suffix.lower()
    uid = str(uuid.uuid4()) + ext
    dest = upload_dir / uid

    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")

    dest.write_bytes(data)
    return {"upload_id": uid, "filename": file.filename, "size": len(data)}
