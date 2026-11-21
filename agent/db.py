"""Base SQLite (fichier /data/social.db) — uniquement les tables de l'agent social."""
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional

import sqlalchemy as sa
from sqlalchemy import JSON, Column, LargeBinary, Text, UniqueConstraint, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import Field, SQLModel

DATA_DIR = os.getenv("DATA_DIR", "/data")
DB_PATH = os.path.join(DATA_DIR, "social.db")
DB_URL = f"sqlite+aiosqlite:///{DB_PATH}"


def gen_id() -> str:
    return str(uuid.uuid4())


engine = create_async_engine(DB_URL, echo=False, connect_args={"timeout": 30})


@event.listens_for(engine.sync_engine, "connect")
def _pragmas(dbapi_conn, _rec):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=30000")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.close()


_Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@asynccontextmanager
async def get_celery_session():          # nom conservé : tes services l'importent tels quels
    async with _Session() as session:
        yield session


async def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


# ═════════════════════ MODÈLES ═════════════════════
class SocialBrand(SQLModel, table=True):
    __tablename__ = "social_brand"
    id: str = Field(default_factory=gen_id, primary_key=True)
    slug: str = Field(index=True, unique=True)
    nom: str = Field(default="")
    site_url: str = Field(default="")
    urls_supplementaires: List[str] = Field(default=[], sa_column=Column(JSON))
    identite: dict = Field(default={}, sa_column=Column(JSON))
    ton: dict = Field(default={}, sa_column=Column(JSON))
    style_guide: str = Field(default="", sa_column=Column(Text))
    piliers: List[dict] = Field(default=[], sa_column=Column(JSON))
    apprentissages: List[dict] = Field(default=[], sa_column=Column(JSON))
    config: dict = Field(default={}, sa_column=Column(JSON))
    statut_analyse: str = Field(default="non_analyse")
    erreur_analyse: Optional[str] = Field(default=None, sa_column=Column(Text))
    derniere_analyse: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class SocialStyleSample(SQLModel, table=True):
    __tablename__ = "social_style_sample"
    id: str = Field(default_factory=gen_id, primary_key=True)
    brand_id: str = Field(foreign_key="social_brand.id", index=True)
    plateforme: Optional[str] = Field(default=None, index=True)
    texte: str = Field(sa_column=Column(Text))
    source: str = Field(default="manuel")
    poids: float = Field(default=1.0)
    texte_hash: str = Field(default="", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SocialAccount(SQLModel, table=True):
    __tablename__ = "social_account"
    __table_args__ = (UniqueConstraint("brand_id", "plateforme", name="uq_social_account"),)
    id: str = Field(default_factory=gen_id, primary_key=True)
    brand_id: str = Field(foreign_key="social_brand.id", index=True)
    plateforme: str = Field(index=True)
    nom_affichage: str = Field(default="")
    identifiant_externe: Optional[str] = None
    credentials_chiffrees: bytes = Field(sa_column=Column(LargeBinary))
    statut: str = Field(default="actif")
    expire_le: Optional[datetime] = None
    derniere_verification: Optional[datetime] = None
    derniere_erreur: Optional[str] = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class SocialIdea(SQLModel, table=True):
    __tablename__ = "social_idea"
    id: str = Field(default_factory=gen_id, primary_key=True)
    brand_id: str = Field(foreign_key="social_brand.id", index=True)
    titre: str
    angle: str = Field(default="", sa_column=Column(Text))
    accroche: str = Field(default="", sa_column=Column(Text))
    pilier: str = Field(default="", index=True)
    objectif: str = Field(default="engagement")
    format_conseille: str = Field(default="texte")
    plateformes: List[str] = Field(default=[], sa_column=Column(JSON))
    justification: str = Field(default="", sa_column=Column(Text))
    source_tendance_url: Optional[str] = None
    urgence: str = Field(default="evergreen")
    score_potentiel: float = Field(default=50.0)
    statut: str = Field(default="propose", index=True)
    motif_rejet: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SocialPost(SQLModel, table=True):
    __tablename__ = "social_post"
    __table_args__ = (sa.Index("ix_social_post_statut_sched", "statut", "scheduled_at"),)
    id: str = Field(default_factory=gen_id, primary_key=True)
    brand_id: str = Field(foreign_key="social_brand.id", index=True)
    idea_id: Optional[str] = Field(default=None, index=True)
    groupe_id: Optional[str] = Field(default=None, index=True)
    variante: Optional[str] = None
    plateforme: str = Field(index=True)
    format: str = Field(default="texte")
    contenu: str = Field(default="", sa_column=Column(Text))
    contenu_original_ia: Optional[str] = Field(default=None, sa_column=Column(Text))
    hashtags: List[str] = Field(default=[], sa_column=Column(JSON))
    media_urls: List[str] = Field(default=[], sa_column=Column(JSON))
    lien: Optional[str] = None
    pilier: str = Field(default="")
    visuel_spec: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    script_video: Optional[str] = Field(default=None, sa_column=Column(Text))
    statut: str = Field(default="brouillon", index=True)
    scheduled_at: Optional[datetime] = Field(default=None, index=True)
    published_at: Optional[datetime] = Field(default=None, index=True)
    external_id: Optional[str] = None
    external_url: Optional[str] = None
    prediction: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    horaire_justification: Optional[str] = Field(default=None, sa_column=Column(Text))
    erreur: Optional[str] = Field(default=None, sa_column=Column(Text))
    nb_tentatives: int = Field(default=0)
    genere_par_ia: bool = Field(default=True)
    validated_by: Optional[str] = None
    validated_at: Optional[datetime] = None
    rejet_motif: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class SocialMetric(SQLModel, table=True):
    __tablename__ = "social_metric"
    id: str = Field(default_factory=gen_id, primary_key=True)
    post_id: str = Field(foreign_key="social_post.id", index=True)
    brand_id: str = Field(index=True)
    plateforme: str = Field(index=True)
    collecte_le: datetime = Field(default_factory=datetime.utcnow, index=True)
    age_heures: float = Field(default=0.0)
    impressions: int = Field(default=0)
    reach: int = Field(default=0)
    video_views: int = Field(default=0)
    likes: int = Field(default=0)
    comments: int = Field(default=0)
    shares: int = Field(default=0)
    saves: int = Field(default=0)
    clicks: int = Field(default=0)
    engagement_score: float = Field(default=0.0)
    engagement_rate: Optional[float] = None
    brut: Optional[dict] = Field(default=None, sa_column=Column(JSON))


class SocialAccountSnapshot(SQLModel, table=True):
    __tablename__ = "social_account_snapshot"
    __table_args__ = (UniqueConstraint("brand_id", "plateforme", "jour", name="uq_social_snapshot"),)
    id: str = Field(default_factory=gen_id, primary_key=True)
    brand_id: str = Field(index=True)
    plateforme: str = Field(index=True)
    jour: str = Field(index=True)
    followers: int = Field(default=0)
    media_count: Optional[int] = None
    collecte_le: datetime = Field(default_factory=datetime.utcnow)


class SocialReport(SQLModel, table=True):
    __tablename__ = "social_report"
    id: str = Field(default_factory=gen_id, primary_key=True)
    brand_id: str = Field(index=True)
    periode_debut: str
    periode_fin: str
    faits: dict = Field(default={}, sa_column=Column(JSON))
    analyse: dict = Field(default={}, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SocialJob(SQLModel, table=True):
    __tablename__ = "social_job"
    id: str = Field(default_factory=gen_id, primary_key=True)
    kind: str = Field(index=True)
    statut: str = Field(default="en_attente", index=True)
    params: dict = Field(default={}, sa_column=Column(JSON))
    resultat: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    erreur: Optional[str] = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None