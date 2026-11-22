"""Schéma unique de la configuration, partagé par la page de premier démarrage et Paramètres › Configuration."""


def F(key, label, kind="text", hint="", restart=False, placeholder="", options=None, group=None, warn=""):
    """kind : text | url | secret | number | select. restart=True : lu une seule fois au démarrage de l'app."""
    return {"key": key, "label": label, "kind": kind, "hint": hint, "restart": restart,
            "placeholder": placeholder, "options": options or [], "group": group, "warn": warn}


SECTIONS = [
    {"id": "app", "title": "Application", "desc": "Adresse publique et réseau.", "fields": [
        F("PUBLIC_BASE_URL", "URL publique", "url", "Utilisée pour les liens des médias que les réseaux téléchargent. Doit être joignable depuis Internet, en https.", True, "https://mon-domaine.com"),
        F("SOCIAL_OAUTH_REDIRECT_BASE", "Base des retours OAuth", "url", "Vide = identique à l'URL publique.", True),
        F("PORT", "Port interne", "number", "Doit correspondre au mapping du docker-compose. Défaut 8080.", True, "8080"),
        F("SOCIAL_TZ", "Fuseau horaire", "text", "Identifiant IANA, par exemple Africa/Dakar.", True, "Africa/Dakar"),
    ]},
    {"id": "marque", "title": "Marque", "desc": "Identité de la marque gérée.", "fields": [
        F("SOCIAL_BRAND_SLUG", "Identifiant (slug)", "text", "Ex : ma-marque.", False, "rhmanager",
          warn="Attention : changer l'identifiant crée une nouvelle marque vide (l'ancienne reste en base)."),
        F("SOCIAL_BRAND_NAME", "Nom affiché", "text", "", True),
        F("SOCIAL_BRAND_SITE", "Site web de la marque", "url", "https://…", True),
        F("SOCIAL_FICHE_TECHNIQUE", "Chemin de la fiche technique (YAML)", "text", "Défaut : /data/fiche_technique.yaml", True, "/data/fiche_technique.yaml"),
    ]},
    {"id": "ia", "title": "Intelligence artificielle", "desc": "Rédaction, analyse et vision.", "fields": [
        F("GROQ_API_KEY", "Clé Groq (texte)", "secret", "Clé de secours. Les clés multiples avec bascule automatique se gèrent dans l'onglet « Clés API »."),
        F("GROQ_API_KEY_FACTURE", "Clé Groq (vision)", "secret", "Vide = clé ci-dessus."),
        F("LLM_BASE_URL", "URL de l'API LLM compatible OpenAI", "url", "Défaut : https://api.groq.com/openai/v1", False, "https://api.groq.com/openai/v1"),
        F("LLM_MODEL", "Modèle texte", "text", "Défaut : llama-3.3-70b-versatile. Le modèle choisi dans « Modèles & tarifs » est prioritaire.", False, "llama-3.3-70b-versatile"),
        F("GROQ_VISION_MODEL", "Modèle vision", "text", "Analyse des captures. Le modèle choisi dans « Modèles & tarifs » est prioritaire.", True),
        F("SERPER_API_KEY", "Clé Serper (actualités)", "secret", "Optionnel."),
        F("POLLINATIONS_API_KEY", "Clé Pollinations", "secret", "Optionnel."),
    ]},
    {"id": "medias", "title": "Médias et voix", "desc": "Photos libres, voix off et polices.", "fields": [
        F("UNSPLASH_ACCESS_KEY", "Unsplash : Access Key", "secret", "Optionnel.", group="Unsplash"),
        F("UNSPLASH_APP_NAME", "Unsplash : nom de l'app", "text", "", group="Unsplash"),
        F("PEXELS_API_KEY", "Pexels : clé", "secret", "Optionnel.", group="Pexels"),
        F("SOCIAL_VOICE", "Voix off (edge-tts)", "text", "Défaut : fr-FR-DeniseNeural", False, "fr-FR-DeniseNeural", group="Voix et polices"),
        F("SOCIAL_FONT_BOLD", "Police grasse (chemin)", "text", "Optionnel.", True, group="Voix et polices"),
        F("SOCIAL_FONT_REGULAR", "Police normale (chemin)", "text", "Optionnel.", True, group="Voix et polices"),
    ]},
    {"id": "qpost", "title": "Publication via QPost", "desc": "Méthode la plus simple pour TikTok et Instagram.", "fields": [
        F("QPOST_API_KEY", "Clé API QPost", "secret", "qpost.dev › API Keys."),
        F("QPOST_BASE_URL", "URL QPost", "url", "Défaut : https://qpost.dev", True, "https://qpost.dev"),
        F("QPOST_TIKTOK_PRIVACY", "Visibilité TikTok", "select", "Vide = PUBLIC_TO_EVERYONE.", False, "",
          ["PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "FOLLOWER_OF_CREATOR", "SELF_ONLY"]),
    ]},
    {"id": "oauth", "title": "Connexion OAuth (avancé)", "desc": "À remplir seulement pour utiliser les boutons « Connecter ». La connexion par jeton, dans l'onglet Comptes, reste la méthode recommandée.", "fields": [
        F("META_APP_ID", "App ID", "text", "", group="Meta (Facebook)"),
        F("META_APP_SECRET", "App Secret", "secret", "", group="Meta (Facebook)"),
        F("META_GRAPH_VERSION", "Version Graph", "text", "Ex : v24.0", True, "v24.0", group="Meta (Facebook)"),
        F("META_PAGE_ID", "ID de Page imposé", "text", "", group="Meta (Facebook)"),
        F("META_SCOPES", "Scopes", "text", "", False, "pages_show_list,pages_manage_posts,pages_read_engagement,business_management", group="Meta (Facebook)"),
        F("INSTAGRAM_APP_ID", "App ID", "text", "", group="Instagram"),
        F("INSTAGRAM_APP_SECRET", "App Secret", "secret", "", group="Instagram"),
        F("INSTAGRAM_SCOPES", "Scopes", "text", "", False, "instagram_business_basic,instagram_business_content_publish", group="Instagram"),
        F("LINKEDIN_CLIENT_ID", "Client ID", "text", "", group="LinkedIn"),
        F("LINKEDIN_CLIENT_SECRET", "Client Secret", "secret", "", group="LinkedIn"),
        F("LINKEDIN_VERSION", "Version API (AAAAMM)", "text", "", True, group="LinkedIn"),
        F("LINKEDIN_SCOPES", "Scopes", "text", "", False, "openid profile w_member_social", group="LinkedIn"),
        F("LINKEDIN_ORG_ID", "ID de Page", "text", "Optionnel : chiffres uniquement.", group="LinkedIn"),
        F("X_CLIENT_ID", "Client ID", "text", "", group="X"),
        F("X_CLIENT_SECRET", "Client Secret", "secret", "", group="X"),
        F("X_SCOPES", "Scopes", "text", "", False, "tweet.read tweet.write users.read media.write offline.access", group="X"),
        F("TIKTOK_CLIENT_KEY", "Client Key", "text", "", group="TikTok"),
        F("TIKTOK_CLIENT_SECRET", "Client Secret", "secret", "", group="TikTok"),
        F("TIKTOK_SCOPES", "Scopes", "text", "", False, "user.info.basic,video.publish,video.upload", group="TikTok"),
    ]},
]

FIELDS = {f["key"]: f for s in SECTIONS for f in s["fields"]}