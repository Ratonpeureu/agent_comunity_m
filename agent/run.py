import os

from agent.bootstrap import load_config

load_config()        # le PORT saisi dans /setup est lu ici, avant le démarrage d'uvicorn

import uvicorn

if __name__ == "__main__":
    uvicorn.run("agent.main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8080")),
                proxy_headers=True, forwarded_allow_ips="*", log_level="info")