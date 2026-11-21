"""Remplace Celery : mêmes noms (`.delay`), exécution en tâche asyncio dans le processus."""
import asyncio
import json
import logging

from agent.services.social import social_agent_service as svc

logger = logging.getLogger("social_tasks")
_tasks: set = set()
_sem = None


def _spawn(coro):
    t = asyncio.get_running_loop().create_task(coro)
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)


async def _run_job(job_id: str, kind: str, params: dict | None = None):
    global _sem
    if _sem is None:
        _sem = asyncio.Semaphore(2)          # max 2 jobs lourds (vidéo…) en parallèle
    async with _sem:
        await svc.job_update(job_id, statut="en_cours")
        try:
            res = await asyncio.wait_for(svc.JOB_HANDLERS[kind](**(params or {})), 1500)
            res = res if isinstance(res, dict) else {"result": res}
            res = json.loads(json.dumps(res, default=str))
            await svc.job_update(job_id, statut="termine", resultat=res)
        except BaseException as e:
            logger.exception("[social_job] %s a échoué", kind)
            await svc.job_update(job_id, statut="echec", erreur=(str(e) or e.__class__.__name__)[:1000])


class _Task:
    def __init__(self, fn):
        self.fn = fn

    def delay(self, *a, **k):
        _spawn(self.fn(*a, **k))


social_job_task = _Task(_run_job)
social_publish_post_task = _Task(lambda post_id, force=False: svc.publish_post(post_id, force=force))