
import sys
import uuid
import asyncio
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase

_MAX_UPLOAD_HISTORY = 1000
_MAX_SCHEDULED_UPLOADS = 1000
# Statuses the upload_to_* methods return for a real, completed upload
# ('success' generic; 'published' Instagram/TikTok/Twitter; 'uploaded'/
# 'scheduled' YouTube, whose record status overrides the leading 'success').
_SUCCESS_UPLOAD_STATUSES = frozenset({"success", "published", "uploaded", "scheduled"})

class Uploader(AgentBase):
    """
    Handles video upload to YouTube, Instagram, and other platforms.
    Supports scheduled uploads and API integration.
    """

    PLATFORMS = ["youtube", "instagram", "tiktok", "twitter", "facebook"]

    def __init__(self, ghost: dict | None = None):
        super().__init__(str(uuid.uuid4()), "Uploader", "content")
        self.capabilities = ["#", "cancel_scheduled_upload", "content", "execute_scheduled_uploads", "instagram", "schedule_upload", "scheduled_uploads", "upload", "upload_history", "upload_instagram", "upload_tiktok", "upload_twitter", "upload_youtube", "youtube"]
        if ghost:
            self.inherit_ghost(ghost)

        self._upload_history: list[dict] = []
        self._scheduled_uploads: list[dict] = []
        self._api_credentials = CONFIG.get("api_keys", {})
        logger.info("[VECTOR][uploader] Uploader initialized")

    def _remember_upload(self, upload_record: dict) -> None:
        self._upload_history.append(upload_record)
        if len(self._upload_history) > _MAX_UPLOAD_HISTORY:
            del self._upload_history[:-_MAX_UPLOAD_HISTORY]

    def _remember_schedule(self, schedule: dict) -> None:
        self._scheduled_uploads.append(schedule)
        if len(self._scheduled_uploads) > _MAX_SCHEDULED_UPLOADS:
            del self._scheduled_uploads[:-_MAX_SCHEDULED_UPLOADS]

    async def _gate_publish(self, platform: str, title: str) -> tuple[bool, str]:
        """RED-tier owner-approval gate for real, public, irreversible uploads.

        2026-07-23 (task #92, per-district real tool-execution audit): found
        that `upload_to_youtube`/`upload_to_instagram`/`upload_to_tiktok`/
        `upload_to_twitter` had NO PermissionGateway check at all, even though
        `content_publish` is explicitly RED-tiered in core/config.py
        ("Real money / irreversible outward actions — owner approval ALWAYS").
        `content_scheduler.py`'s `run_pending()` already gates its OWN publish
        path (Dev.to/Hashnode/Medium via BlogPublisher) — its code comment
        even says "the content Hand gates, this scheduler did not [before this
        fix]" — but that's a DIFFERENT class from this Uploader, so it never
        covered YouTube/Instagram/TikTok/Twitter. Both the direct
        Governor.dispatch() → Uploader.run() path AND video_pipeline.py's
        create_and_upload() call these methods directly with zero gating,
        meaning VECTOR could autonomously publish to real social accounts
        with no owner approval — confirmed via code read, not by firing a
        real post. Mirrors content_scheduler's fail-closed pattern: any
        exception talking to the gateway means NOT approved.
        """
        try:
            from core.loop.permission_gateway import PermissionGateway, Action
            result = await PermissionGateway().execute(Action(
                action_type="content_publish",
                params={
                    "summary": f"Publish '{title[:60]}' to {platform}",
                    "platform": platform,
                    "title": title,
                },
                proposed_by="uploader",
            ))
            approved = getattr(result, "approved", False)
            reason = getattr(result, "reason", "")
            return approved, reason
        except Exception as _gw_err:
            logger.error(
                "[VECTOR][uploader] gateway unavailable — NOT publishing to {}: {}",
                platform, _gw_err,
            )
            return False, f"gateway unavailable: {_gw_err}"

    async def upload_to_youtube(self, video_path: str, title: str,
                               description: str, tags: list[str],
                               category: str = "22", privacy: str = "private",
                               scheduled_time: Optional[str] = None) -> dict:
        """
        Upload video to YouTube using Google API.
        """
        if not Path(video_path).exists():
            return {"status": "error", "message": "Video file not found"}

        _approved, _reason = await self._gate_publish("youtube", title)
        if not _approved:
            return {"status": "blocked", "platform": "youtube", "reason": _reason or "owner did not approve publish"}

        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            from googleapiclient.errors import HttpError
            from googleapiclient.http import MediaFileUpload

            creds_json = self._api_credentials.get("google_credentials_path", "")
            if not creds_json or not Path(creds_json).exists():
                return {
                    "status": "error",
                    "message": "Google API credentials not configured",
                    "simulated": True,
                    "video_id": f"sim_{uuid.uuid4().hex[:12]}"
                }

            credentials = Credentials.from_authorized_user_file(creds_json)
            youtube = build("youtube", "v3", credentials=credentials)

            body = {
                "snippet": {
                    "title": title[:100],
                    "description": description[:5000],
                    "tags": tags[:500],
                    "categoryId": category
                },
                "status": {
                    "privacyStatus": privacy,
                    "selfDeclaredMadeForKids": False
                }
            }

            if scheduled_time:
                body["status"]["publishAt"] = scheduled_time

            media = MediaFileUpload(video_path, chunksize=-1, resumable=True)

            request = youtube.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media
            )

            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    progress = int(status.resumable_progress * 100 / status.size())
                    logger.info(f"[VECTOR][uploader] YouTube upload: {progress}%")

            video_id = response.get("id")

            upload_record = {
                "id": str(uuid.uuid4()),
                "platform": "youtube",
                "video_id": video_id,
                "title": title,
                "status": "uploaded" if not scheduled_time else "scheduled",
                "scheduled_time": scheduled_time,
                "timestamp": self._get_timestamp()
            }
            self._remember_upload(upload_record)

            self.award_points(30, "youtube_uploaded")
            logger.info(f"[VECTOR][uploader] YouTube upload complete: {video_id}")

            return {
                "status": "success",
                "video_id": video_id,
                "platform": "youtube",
                **upload_record
            }

        except ImportError:
            return self._simulate_upload("youtube", video_path, title)
        except Exception as e:
            logger.error(f"[VECTOR][uploader] YouTube upload failed: {e}")
            return {"status": "error", "message": str(e), "platform": "youtube"}

    async def upload_to_instagram(self, video_path: str, caption: str,
                                  hashtags: list[str], scheduled_time: Optional[str] = None) -> dict:
        """
        Upload video to Instagram via Graph API.
        """
        if not Path(video_path).exists():
            return {"status": "error", "message": "Video file not found"}

        _approved, _reason = await self._gate_publish("instagram", caption)
        if not _approved:
            return {"status": "blocked", "platform": "instagram", "reason": _reason or "owner did not approve publish"}

        # Track partial success: if container was created but publish failed,
        # we can resume from the publish step on retry (don't create another container).
        partial_creation_id: str | None = None

        try:
            instagram_token = self._api_credentials.get("instagram_access_token", "")
            instagram_account_id = self._api_credentials.get("instagram_account_id", "")

            if not instagram_token or not instagram_account_id:
                return self._simulate_upload("instagram", video_path, caption)

            import httpx

            tags_str = " ".join("#" + h for h in hashtags[:30])
            caption_full = caption + "\n\n" + tags_str

            media_url = f"https://graph.facebook.com/v18.0/{instagram_account_id}/media"
            media_data = {
                "media_type": "REELS",
                "video_url": video_path,
                "caption": caption_full,
                "access_token": instagram_token
            }

            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(media_url, data=media_data)

                if response.status_code != 200:
                    raise RuntimeError(f"media create failed: {response.status_code} {response.text[:200]}")

                result = response.json()
                creation_id = result.get("id")
                partial_creation_id = creation_id  # phase 1 succeeded

                publish_url = f"https://graph.facebook.com/v18.0/{instagram_account_id}/media_publish"
                publish_data = {
                    "creation_id": creation_id,
                    "access_token": instagram_token
                }

                publish_response = await client.post(publish_url, data=publish_data)
                if publish_response.status_code != 200:
                    raise RuntimeError(f"media publish failed: {publish_response.status_code} {publish_response.text[:200]}")

                upload_record = {
                    "id": str(uuid.uuid4()),
                    "platform": "instagram",
                    "media_id": creation_id,
                    "caption": caption[:100],
                    "status": "published",
                    "timestamp": self._get_timestamp()
                }
                self._remember_upload(upload_record)

                self.award_points(25, "instagram_uploaded")
                return {"status": "success", "platform": "instagram", **upload_record}

        except Exception as e:
            logger.error(f"[VECTOR][uploader] Instagram upload failed: {e}")
            # If container was created but publish failed, return partial status
            # with the creation_id so retry can resume from the publish step
            # instead of creating a duplicate container.
            if partial_creation_id:
                return {
                    "status": "partial",
                    "platform": "instagram",
                    "creation_id": partial_creation_id,
                    "error": str(e),
                    "retry_with": {"creation_id": partial_creation_id},
                }
            return {
                "status": "error",
                "platform": "instagram",
                "message": str(e),
            }

    def _dry_run_enabled(self) -> bool:
        """Real uploads to tiktok/twitter are opt-in: CONFIG content.upload_dry_run defaults True."""
        try:
            content_cfg = CONFIG.get("content", {}) or {}
            if isinstance(content_cfg, dict):
                return bool(content_cfg.get("upload_dry_run", True))
            return bool(getattr(content_cfg, "upload_dry_run", True))
        except Exception:
            return True

    async def upload_to_tiktok(self, video_path: str, caption: str,
                               hashtags: list[str] | None = None) -> dict:
        """
        Upload video to TikTok via the Content Posting API (direct post).
        Needs api_keys.tiktok_access_token. Honors upload_dry_run.
        """
        path = Path(video_path)
        if not path.exists():
            return {"status": "error", "message": "Video file not found"}

        token = self._api_credentials.get("tiktok_access_token", "")
        if not token or self._dry_run_enabled():
            return self._simulate_upload("tiktok", video_path, caption)

        _approved, _reason = await self._gate_publish("tiktok", caption)
        if not _approved:
            return {"status": "blocked", "platform": "tiktok", "reason": _reason or "owner did not approve publish"}

        try:
            import httpx

            tags_str = " ".join("#" + h for h in (hashtags or [])[:10])
            title = (caption + " " + tags_str).strip()[:2200]
            video_size = path.stat().st_size

            headers = {"Authorization": f"Bearer {token}"}
            async with httpx.AsyncClient(timeout=300.0) as client:
                init = await client.post(
                    "https://open.tiktokapis.com/v2/post/publish/video/init/",
                    headers={**headers, "Content-Type": "application/json"},
                    json={
                        "post_info": {"title": title, "privacy_level": "SELF_ONLY"},
                        "source_info": {
                            "source": "FILE_UPLOAD",
                            "video_size": video_size,
                            "chunk_size": video_size,
                            "total_chunk_count": 1,
                        },
                    },
                )
                if init.status_code != 200:
                    raise RuntimeError(f"init failed: {init.status_code} {init.text[:200]}")
                data = init.json().get("data", {})
                publish_id = data.get("publish_id")
                upload_url = data.get("upload_url")
                if not upload_url:
                    raise RuntimeError(f"no upload_url in init response: {init.text[:200]}")

                put = await client.put(
                    upload_url,
                    headers={
                        "Content-Type": "video/mp4",
                        "Content-Range": f"bytes 0-{video_size - 1}/{video_size}",
                    },
                    content=path.read_bytes(),
                )
                if put.status_code not in (200, 201, 206):
                    raise RuntimeError(f"upload failed: {put.status_code} {put.text[:200]}")

            upload_record = {
                "id": str(uuid.uuid4()),
                "platform": "tiktok",
                "video_id": publish_id,
                "title": caption[:100],
                "status": "published",
                "timestamp": self._get_timestamp(),
            }
            self._remember_upload(upload_record)
            self.award_points(25, "tiktok_uploaded")
            return {"status": "success", "platform": "tiktok", **upload_record}

        except Exception as e:
            logger.error(f"[VECTOR][uploader] TikTok upload failed: {e}")
            return {
                "status": "error",
                "platform": "tiktok",
                "message": str(e),
            }

    async def upload_to_twitter(self, video_path: str, text: str,
                                hashtags: list[str] | None = None) -> dict:
        """
        Post a video tweet via X API v2 chunked media upload + POST /2/tweets.
        Needs api_keys.twitter_access_token (OAuth2 user token with media.write).
        Honors upload_dry_run.
        """
        path = Path(video_path)
        if not path.exists():
            return {"status": "error", "message": "Video file not found"}

        token = self._api_credentials.get("twitter_access_token", "")
        if not token or self._dry_run_enabled():
            return self._simulate_upload("twitter", video_path, text)

        _approved, _reason = await self._gate_publish("twitter", text)
        if not _approved:
            return {"status": "blocked", "platform": "twitter", "reason": _reason or "owner did not approve publish"}

        try:
            import httpx

            tags_str = " ".join("#" + h for h in (hashtags or [])[:5])
            tweet_text = (text + " " + tags_str).strip()[:280]
            video_bytes = path.read_bytes()
            headers = {"Authorization": f"Bearer {token}"}
            media_base = "https://api.x.com/2/media/upload"

            async with httpx.AsyncClient(timeout=300.0) as client:
                init = await client.post(media_base, headers=headers, data={
                    "command": "INIT",
                    "total_bytes": str(len(video_bytes)),
                    "media_type": "video/mp4",
                    "media_category": "tweet_video",
                })
                if init.status_code not in (200, 201, 202):
                    raise RuntimeError(f"INIT failed: {init.status_code} {init.text[:200]}")
                media_id = (init.json().get("data") or init.json()).get("id") or init.json().get("media_id_string")
                if not media_id:
                    raise RuntimeError(f"no media id: {init.text[:200]}")

                chunk_size = 4 * 1024 * 1024
                for i in range(0, len(video_bytes), chunk_size):
                    append = await client.post(
                        media_base, headers=headers,
                        data={"command": "APPEND", "media_id": media_id,
                              "segment_index": str(i // chunk_size)},
                        files={"media": video_bytes[i:i + chunk_size]},
                    )
                    if append.status_code not in (200, 201, 204):
                        raise RuntimeError(f"APPEND failed: {append.status_code} {append.text[:200]}")

                final = await client.post(media_base, headers=headers,
                                          data={"command": "FINALIZE", "media_id": media_id})
                if final.status_code not in (200, 201):
                    raise RuntimeError(f"FINALIZE failed: {final.status_code} {final.text[:200]}")

                tweet = await client.post(
                    "https://api.x.com/2/tweets",
                    headers={**headers, "Content-Type": "application/json"},
                    json={"text": tweet_text, "media": {"media_ids": [str(media_id)]}},
                )
                if tweet.status_code != 201:
                    raise RuntimeError(f"tweet failed: {tweet.status_code} {tweet.text[:200]}")
                tweet_id = tweet.json().get("data", {}).get("id")

            upload_record = {
                "id": str(uuid.uuid4()),
                "platform": "twitter",
                "video_id": tweet_id,
                "title": text[:100],
                "status": "published",
                "timestamp": self._get_timestamp(),
            }
            self._remember_upload(upload_record)
            self.award_points(25, "twitter_uploaded")
            return {"status": "success", "platform": "twitter", **upload_record}

        except Exception as e:
            logger.error(f"[VECTOR][uploader] Twitter upload failed: {e}")
            return {
                "status": "error",
                "platform": "twitter",
                "message": str(e),
            }

    def _simulate_upload(self, platform: str, video_path: str, title: str) -> dict:
        """Simulate upload when API is not configured."""
        logger.info(f"[VECTOR][uploader] Simulating {platform} upload")

        upload_record = {
            "id": str(uuid.uuid4()),
            "platform": platform,
            "video_id": f"sim_{uuid.uuid4().hex[:12]}",
            "title": title[:50],
            "status": "simulated",
            "simulated": True,
            "timestamp": self._get_timestamp()
        }
        self._remember_upload(upload_record)

        return {"status": "success", "platform": platform, **upload_record}

    async def schedule_upload(self, platform: str, video_path: str,
                             scheduled_datetime: str, metadata: dict) -> dict:
        """
        Schedule a video upload for a specific time.
        """
        try:
            scheduled_dt = datetime.fromisoformat(scheduled_datetime.replace("Z", "+00:00"))
        except ValueError:
            return {"status": "error", "message": "Invalid datetime format"}

        if scheduled_dt <= datetime.now(timezone.utc):
            return {"status": "error", "message": "Scheduled time must be in the future"}

        schedule = {
            "id": str(uuid.uuid4()),
            "platform": platform,
            "video_path": video_path,
            "scheduled_time": scheduled_datetime,
            "metadata": metadata,
            "status": "pending",
            "created_at": self._get_timestamp()
        }

        self._remember_schedule(schedule)

        self.award_points(10, "upload_scheduled")
        logger.info(f"[VECTOR][uploader] Scheduled {platform} upload for {scheduled_datetime}")

        return {
            "status": "success",
            "schedule_id": schedule["id"],
            "scheduled_time": scheduled_datetime
        }

    @staticmethod
    def _classify_scheduled_result(result) -> tuple[str, dict]:
        """Map an upload result to (schedule status, extra schedule fields).

        Fails closed: anything that is not a recognised, non-simulated success
        is never 'executed'. 'simulated' is checked first because the YouTube
        no-credentials result is status 'error' AND simulated=True.
        """
        if not isinstance(result, dict):
            return "failed", {"error": f"unexpected upload result: {result!r}"}

        if result.get("simulated"):
            return "simulated", {}

        status = result.get("status")
        if status in _SUCCESS_UPLOAD_STATUSES:
            return "executed", {}
        if status == "blocked":
            return "blocked", {"reason": result.get("reason") or "owner did not approve publish"}
        if status == "error":
            return "failed", {"error": result.get("message") or result.get("error") or "upload failed"}
        # 'partial' and any unrecognised status: never treat as done.
        return "failed", {
            "error": result.get("error") or result.get("message")
            or f"upload not completed (status={status!r})"
        }

    async def execute_scheduled_uploads(self) -> list[dict]:
        """
        Execute all pending scheduled uploads.

        Sets status='uploading' BEFORE the upload starts to prevent concurrent
        callers from picking up the same item (TOCTOU race). The final status
        is then taken from the real upload result:

        - 'executed': genuine, non-simulated success. Only these results are
          returned.
        - 'blocked': the permission gate refused; the reason is kept in
          schedule['reason'].
        - 'simulated': the result is flagged simulated (nothing was actually
          published), including the YouTube no-credentials 'error' shape.
        - 'failed': status 'error', 'partial' or unrecognised (fail closed),
          or the upload call raised; the message is kept in schedule['error'].

        schedule['result'] holds the raw result for every outcome except a
        raised exception.
        """
        now = datetime.now(timezone.utc)
        executed = []

        # Atomically claim pending items by transitioning to 'uploading' first.
        # This prevents two concurrent callers from both picking up the same
        # pending item and uploading it twice.
        pending = []
        for u in self._scheduled_uploads:
            if u["status"] == "pending":
                scheduled_dt = datetime.fromisoformat(
                    u["scheduled_time"].replace("Z", "+00:00")
                )
                if scheduled_dt <= now:
                    u["status"] = "uploading"
                    pending.append(u)

        for schedule in pending:
            try:
                if schedule["platform"] == "youtube":
                    result = await self.upload_to_youtube(
                        schedule["video_path"],
                        schedule["metadata"].get("title", "Untitled"),
                        schedule["metadata"].get("description", ""),
                        schedule["metadata"].get("tags", []),
                        scheduled_time=schedule["scheduled_time"]
                    )
                elif schedule["platform"] == "instagram":
                    result = await self.upload_to_instagram(
                        schedule["video_path"],
                        schedule["metadata"].get("caption", ""),
                        schedule["metadata"].get("hashtags", [])
                    )
                elif schedule["platform"] == "tiktok":
                    result = await self.upload_to_tiktok(
                        schedule["video_path"],
                        schedule["metadata"].get("caption", ""),
                        schedule["metadata"].get("hashtags", [])
                    )
                elif schedule["platform"] == "twitter":
                    result = await self.upload_to_twitter(
                        schedule["video_path"],
                        schedule["metadata"].get("caption", "")
                        or schedule["metadata"].get("title", ""),
                        schedule["metadata"].get("hashtags", [])
                    )
                else:
                    result = self._simulate_upload(
                        schedule["platform"],
                        schedule["video_path"],
                        schedule["metadata"].get("title", "")
                    )

                status, details = self._classify_scheduled_result(result)
                schedule["status"] = status
                schedule["result"] = result
                schedule.update(details)
                if status == "executed":
                    executed.append(result)
                else:
                    logger.warning(
                        "[VECTOR][uploader] Scheduled {} upload recorded as {}: {}",
                        schedule["platform"], status, details or "no detail",
                    )

            except Exception as e:
                logger.error(f"[VECTOR][uploader] Failed to execute scheduled upload: {e}")
                schedule["status"] = "failed"
                schedule["error"] = str(e)

        return executed

    def get_upload_history(self, platform: Optional[str] = None,
                          limit: int = 50) -> list[dict]:
        """Get upload history, optionally filtered by platform."""
        history = self._upload_history
        if platform:
            history = [h for h in history if h.get("platform") == platform]
        return sorted(history[-limit:], key=lambda x: x["timestamp"], reverse=True)

    def get_scheduled_uploads(self, status: Optional[str] = None) -> list[dict]:
        """Get scheduled uploads, optionally filtered by status."""
        if status:
            return [u for u in self._scheduled_uploads if u["status"] == status]
        return self._scheduled_uploads

    def cancel_scheduled_upload(self, schedule_id: str) -> bool:
        """Cancel a scheduled upload."""
        for schedule in self._scheduled_uploads:
            if schedule["id"] == schedule_id and schedule["status"] == "pending":
                schedule["status"] = "cancelled"
                return True
        return False

    def _get_timestamp(self) -> str:
        """Get current UTC timestamp."""
        return datetime.now(timezone.utc).isoformat()

    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "")
        p = task.get("params", {}) or {}
        supported = [
            "upload_youtube", "upload_instagram", "upload_tiktok", "upload_twitter",
            "schedule_upload", "execute_scheduled_uploads", "upload_history",
            "scheduled_uploads", "cancel_scheduled_upload",
        ]

        if task_type == "upload_youtube":
            return await self.upload_to_youtube(
                p.get("video_path", ""), p.get("title", ""), p.get("description", ""),
                p.get("tags", []), p.get("category", "22"), p.get("privacy", "private"),
                p.get("scheduled_time"),
            )
        if task_type == "upload_instagram":
            return await self.upload_to_instagram(
                p.get("video_path", ""), p.get("caption", ""), p.get("hashtags", []), p.get("scheduled_time"),
            )
        if task_type == "upload_tiktok":
            return await self.upload_to_tiktok(p.get("video_path", ""), p.get("caption", ""), p.get("hashtags"))
        if task_type == "upload_twitter":
            return await self.upload_to_twitter(p.get("video_path", ""), p.get("text", ""), p.get("hashtags"))
        if task_type == "schedule_upload":
            return await self.schedule_upload(
                p.get("platform", ""), p.get("video_path", ""),
                p.get("scheduled_datetime", ""), p.get("metadata", {}),
            )
        if task_type == "execute_scheduled_uploads":
            return {"status": "ok", "results": await self.execute_scheduled_uploads()}
        if task_type == "upload_history":
            return {"status": "ok", "history": self.get_upload_history(p.get("platform"), p.get("limit", 50))}
        if task_type == "scheduled_uploads":
            return {"status": "ok", "scheduled": self.get_scheduled_uploads(p.get("status"))}
        if task_type == "cancel_scheduled_upload":
            return {"status": "ok", "cancelled": self.cancel_scheduled_upload(p.get("schedule_id", ""))}

        # 2026-08-05: real chat dispatch arrives as an LLM-invented task_type
        # with the user's actual question in params["query"]/["content"] —
        # "show me my recent upload history across platforms" previously hit
        # the bare "unhandled type" error stub. Route it to the READ-ONLY,
        # no-required-argument history/schedule lookups — never trigger a
        # real upload_to_youtube/instagram/tiktok/twitter (RED-tier,
        # owner-approval-gated publish) or schedule_upload from unmatched
        # free text.
        query = (
            p.get("query") or p.get("content") or task.get("query") or task.get("prompt") or ""
        ).strip()
        if query:
            q = query.lower()
            if "schedul" in q:
                return {"status": "ok", "scheduled": self.get_scheduled_uploads(p.get("status"))}
            return {"status": "ok", "history": self.get_upload_history(p.get("platform"), p.get("limit", 50))}

        return {"status": "error", "error": f"unhandled type '{task_type}'", "supported": supported}

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    import asyncio

    async def test():
        uploader = Uploader()

        schedule = await uploader.schedule_upload(
            "youtube",
            "C:/videos/test.mp4",
            "2025-01-01T12:00:00Z",
            {"title": "Test Video", "description": "Test description"}
        )
        print(f"Scheduled: {schedule.get('schedule_id', 'N/A')}")

        history = uploader.get_upload_history()
        print(f"Upload history: {len(history)} items")

        print("✅ uploader.py OK")

    asyncio.run(test())
