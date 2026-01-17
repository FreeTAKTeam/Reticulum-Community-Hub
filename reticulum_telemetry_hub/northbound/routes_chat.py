"""Chat routes for the northbound API."""
# pylint: disable=import-error

from __future__ import annotations

import hashlib
from typing import Optional

from fastapi import Depends
from fastapi import FastAPI
from fastapi import File
from fastapi import Form
from fastapi import HTTPException
from fastapi import Query
from fastapi import UploadFile
from fastapi import status

from .models import ChatSendPayload
from .services import NorthboundServices


MAX_ATTACHMENT_BYTES = 8 * 1024 * 1024


def register_chat_routes(
    app: FastAPI,
    *,
    services: NorthboundServices,
    require_protected,
) -> None:
    """Register chat routes on the FastAPI app."""

    @app.get("/Chat/Messages", dependencies=[Depends(require_protected)])
    def list_chat_messages(
        limit: int = Query(default=200),
        direction: Optional[str] = Query(default=None),
        topic_id: Optional[str] = Query(default=None, alias="topic_id"),
        destination: Optional[str] = Query(default=None),
        source: Optional[str] = Query(default=None),
    ) -> list[dict]:
        """Return persisted chat messages."""

        messages = services.list_chat_messages(
            limit=limit,
            direction=direction,
            topic_id=topic_id,
            destination=destination,
            source=source,
        )
        return [message.to_dict() for message in messages]

    @app.post("/Chat/Message", dependencies=[Depends(require_protected)])
    def send_chat_message(payload: ChatSendPayload) -> dict:
        """Send a chat message with optional attachments."""

        try:
            attachments = services.resolve_attachments(
                file_ids=payload.file_ids, image_ids=payload.image_ids
            )
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        try:
            message = services.send_chat_message(
                content=payload.content or "",
                scope=payload.scope,
                topic_id=payload.topic_id,
                destination=payload.destination,
                attachments=attachments,
            )
        except RuntimeError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
            ) from exc
        return message.to_dict()

    @app.post("/Chat/Attachment", dependencies=[Depends(require_protected)])
    async def upload_chat_attachment(
        category: str = Form(...),
        file: UploadFile = File(...),
        sha256: Optional[str] = Form(default=None),
        topic_id: Optional[str] = Form(default=None),
    ) -> dict:
        """Upload a chat attachment to the hub."""

        normalized = category.lower().strip()
        if normalized not in {"file", "image"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Attachment category must be file or image",
            )
        content = await file.read()
        if not content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Attachment content is empty",
            )
        if len(content) > MAX_ATTACHMENT_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Attachment exceeds size limit",
            )
        if normalized == "image":
            media_type = file.content_type or ""
            if not media_type.startswith("image/"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Image attachments must use an image content type",
                )
        if sha256:
            digest = hashlib.sha256(content).hexdigest()
            if digest.lower() != sha256.lower():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Attachment hash mismatch",
                )
        attachment = services.store_uploaded_attachment(
            content=content,
            filename=file.filename or "upload.bin",
            media_type=file.content_type,
            category=normalized,
            topic_id=topic_id,
        )
        return attachment.to_dict()
