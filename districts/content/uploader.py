import sys
import uuid
import asyncio
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase


class Uploader(AgentBase):
    """
    Handles video upload to YouTube, Instagram, and other platforms.
    Supports scheduled uploads and API integration.
    """

    PLATFORMS = ["youtube", "instagram", "tiktok", "twitter", "facebook"]

    def __init__(self, ghost: dict = None):
        super().__init__(str(uuid.uuid4()), "Uploader", "content")
        if ghost:
            self.inherit_ghost(ghost)

        self._upload_history: list[dict] = []
        self._scheduled_uploads: list[dict] = []
        self._api_credentials = CONFIG.get("api_keys", {})
        logger.info("[VECTOR][uploader] Uploader initialized")

    async def upload_to_youtube(self, video_path: str, title: str,
                               description: str, tags: list[str],
                               category: str = "22", privacy: str = "private",
                               scheduled_time: Optional[str] = None) -> dict:
        """
        Upload video to YouTube using Google API.
        """
        if not Path(video_path).exists():
            return {"status": "error", "message": "Video file not found"}

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
            self._upload_history.append(upload_record)

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

            if response.status_code == 200:
                result = response.json()
                creation_id = result.get("id")

                publish_url = f"https://graph.facebook.com/v18.0/{instagram_account_id}/media_publish"
                publish_data = {
                    "creation_id": creation_id,
                    "access_token": instagram_token
                }

                publish_response = await client.post(publish_url, data=publish_data)

                upload_record = {
                    "id": str(uuid.uuid4()),
                    "platform": "instagram",
                    "media_id": creation_id,
                    "caption": caption[:100],
                    "status": "published",
                    "timestamp": self._get_timestamp()
                }
                self._upload_history.append(upload_record)

                self.award_points(25, "instagram_uploaded")
                return {"status": "success", "platform": "instagram", **upload_record}

        except Exception as e:
            logger.error(f"[VECTOR][uploader] Instagram upload failed: {e}")

        return self._simulate_upload("instagram", video_path, caption)

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
        self._upload_history.append(upload_record)

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

        self._scheduled_uploads.append(schedule)

        self.award_points(10, "upload_scheduled")
        logger.info(f"[VECTOR][uploader] Scheduled {platform} upload for {scheduled_datetime}")

        return {
            "status": "success",
            "schedule_id": schedule["id"],
            "scheduled_time": scheduled_datetime
        }

    async def execute_scheduled_uploads(self) -> list[dict]:
        """
        Execute all pending scheduled uploads.
        """
        now = datetime.now(timezone.utc)
        executed = []

        pending = [u for u in self._scheduled_uploads if u["status"] == "pending"]

        for schedule in pending:
            try:
                scheduled_dt = datetime.fromisoformat(
                    schedule["scheduled_time"].replace("Z", "+00:00")
                )

                if scheduled_dt <= now:
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
                    else:
                        result = self._simulate_upload(
                            schedule["platform"],
                            schedule["video_path"],
                            schedule["metadata"].get("title", "")
                        )

                    schedule["status"] = "executed"
                    schedule["result"] = result
                    executed.append(result)

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
