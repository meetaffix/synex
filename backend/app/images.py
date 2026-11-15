"""One private image per draft. Upload to LinkedIn only after approval."""
import base64
from io import BytesIO
from urllib.parse import urlsplit
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from PIL import Image, ImageOps
from .database import get_db
from .deps import get_data_user, get_manager_user
from .publishing import get_post, post_out, log
from .publishing_models import Post, PostImage

router = APIRouter(prefix="/publishing/posts", tags=["draft images"])
MAX_BYTES = 5 * 1024 * 1024


class ImageIn(BaseModel):
    data: str = Field(max_length=4*((MAX_BYTES+2)//3))
    version: int = Field(ge=1)


def sanitize(value):
    try:
        raw = base64.b64decode(value, validate=True)
        if len(raw) > MAX_BYTES:
            raise ValueError()
        with Image.open(BytesIO(raw)) as original:
            fmt = original.format
            if fmt not in ("PNG", "JPEG") or original.width * original.height > 16_000_000 or getattr(original,"n_frames",1) != 1:
                raise ValueError()
            image = ImageOps.exif_transpose(original)
            # Re-encode pixels, removing EXIF/GPS and unrelated embedded payloads.
            clean = image.convert("RGBA" if fmt == "PNG" and "A" in image.getbands() else "RGB")
            clean.info.clear()
            buf = BytesIO(); clean.save(buf, format=fmt)
            if buf.tell() > MAX_BYTES:
                raise ValueError()
            return "image/png" if fmt == "PNG" else "image/jpeg", buf.getvalue()
    except (ValueError, OSError, Image.DecompressionBombError):
        raise HTTPException(422, "Use one valid JPEG or PNG up to 5 MB and 16 megapixels.")


def update_version(db, post, version, attached):
    changed = db.query(Post).filter(Post.id == post.id, Post.version == version, Post.status.in_(["draft","paused","failed","cancelled"])).update({"version":Post.version+1,"has_image":attached,"status":"draft"}, synchronize_session=False)
    if not changed:
        raise HTTPException(409, "The post changed or is already scheduled. Reload before changing its image.")


@router.get("/{post_id}/image")
def read(post_id: str, db: Session=Depends(get_db), user=Depends(get_data_user)):
    get_post(db,user,post_id)
    image=db.get(PostImage,post_id)
    if not image:
        raise HTTPException(404,"No image attached")
    return Response(image.data,media_type=image.content_type)


@router.put("/{post_id}/image")
def attach(post_id: str, payload: ImageIn, db: Session=Depends(get_db), user=Depends(get_manager_user)):
    post=get_post(db,user,post_id)
    mime,data=sanitize(payload.data)
    update_version(db,post,payload.version,True)
    image=db.get(PostImage,post_id) or PostImage(post_id=post_id)
    image.content_type,image.data=mime,data
    db.add(image);log(db,post,"draft","Draft image saved");db.commit();db.refresh(post)
    return post_out(post)


@router.delete("/{post_id}/image")
def remove(post_id: str, version:int, db: Session=Depends(get_db), user=Depends(get_manager_user)):
    post=get_post(db,user,post_id)
    update_version(db,post,version,False)
    db.query(PostImage).filter_by(post_id=post_id).delete()
    log(db,post,"draft","Draft image removed");db.commit();db.refresh(post)
    return post_out(post)


def prepare_media(db, sender, post, author, headers):
    """Only upload to LinkedIn's documented upload host; no redirects with bearer tokens."""
    image=db.get(PostImage,post.id)
    if not image:
        raise ValueError("Missing image")
    init=sender.post("https://api.linkedin.com/rest/images?action=initializeUpload",headers=headers,json={"initializeUploadRequest":{"owner":author}},timeout=25)
    init.raise_for_status()
    value=init.json()["value"]
    url=urlsplit(value["uploadUrl"])
    if url.scheme != "https" or url.netloc != "www.linkedin.com" or not url.path.startswith("/dms-uploads/") or not value["image"].startswith("urn:li:image:"):
        raise ValueError("Unrecognized upload destination")
    upload=sender.put(value["uploadUrl"],headers={"Authorization":headers["Authorization"],"Content-Type":image.content_type},content=image.data,timeout=30,follow_redirects=False)
    upload.raise_for_status()
    return {"media":{"id":value["image"]}}
