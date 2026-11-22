"""Planificateur interne (remplace Celery beat)."""
import asyncio
import datetime as dt
import logging
import time

from agent.bootstrap import DATA_DIR
from agent.services.social import social_agent_service as svc
from agent.services.social import social_assets as assets
from agent.services.social.social_config import TZ
from agent.services.llm_client import llm_usage
log = logging.getLogger("scheduler")
_bg: set = set()


def _spawn(coro):
    t = asyncio.get_running_loop().create_task(coro)
    _bg.add(t)
    t.add_done_callback(_bg.discard)


async def _weekly():
    now = dt.datetime.now(TZ)
    if not (now.weekday() == 0 and now.hour == 7):
        return
    mark = DATA_DIR / ".autopilot_last"
    today = now.strftime("%Y-%m-%d")
    if mark.exists() and mark.read_text().strip() == today:
        return
    brand = await svc.get_or_create_brand()
    if not svc.cfg(brand).get("autopilot_actif"):
        return
    mark.write_text(today)
    _spawn(svc.autopilot_weekly(brand.id))


async def run_forever():
    last: dict = {}

    def due(key, every):
        n = time.monotonic()
        if n - last.get(key, -1e9) >= every:
            last[key] = n
            return True
        return False

    await asyncio.sleep(5)
    while True:
        try:
            if due("pub", 60):
                for pid in await svc.claim_due_posts(10):
                    _spawn(svc.publish_post(pid))
            if due("metrics", 3600):
                _spawn(svc.collect_metrics())
            if due("snap", 6 * 3600):
                _spawn(svc.snapshot_followers())
            if due("tokens", 12 * 3600):
                _spawn(svc.refresh_tokens())
            if due("scan", 6 * 3600):
                _spawn(asyncio.to_thread(assets.scan_once, 15))
            if due("purge_ai", 24 * 3600):
                _spawn(asyncio.to_thread(llm_usage.purge))
            await _weekly()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("scheduler")
        await asyncio.sleep(20)