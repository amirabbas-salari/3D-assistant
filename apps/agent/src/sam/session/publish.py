"""Room publish helpers."""
import json, logging
logger = logging.getLogger("sam.session.publish")

async def publish_room_message(ctx, message: dict, *, topic: str = "transcript") -> None:
    if not ctx.room.isconnected():
        return
    try:
        await ctx.room.local_participant.publish_data(
            json.dumps(message, ensure_ascii=False),
            reliable=True,
            topic=topic,
        )
    except Exception:
        logger.warning("Could not publish room data message on topic %s", topic, exc_info=True)

async def publish_latency(ctx, latency):
    await publish_room_message(ctx, {"type": "latency", **latency.as_dict()}, topic="diagnostics")

async def publish_assistant_reply(ctx, text: str):
    await publish_room_message(ctx, {"type": "assistant_reply", "text": text})
