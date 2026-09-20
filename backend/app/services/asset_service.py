from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.client import Asset, Client
from app.models.user import User
from app.schemas.client import AssetCreate
from app.services.activity_service import log_activity


def create_asset(db: Session, client: Client, payload: AssetCreate, actor: User) -> Asset:
    asset = Asset(client_id=client.id, **payload.model_dump())
    db.add(asset)
    db.flush()
    log_activity(db, actor.id, "asset.created", "Asset", asset.id)
    db.commit()
    db.refresh(asset)
    return asset


def list_assets(db: Session, client_id: str):
    return db.query(Asset).filter(Asset.client_id == client_id).order_by(Asset.created_at.desc()).all()


def get_asset_or_404(db: Session, asset_id: str) -> Asset:
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    return asset


def delete_asset(db: Session, asset: Asset, actor: User) -> None:
    log_activity(db, actor.id, "asset.deleted", "Asset", asset.id)
    db.delete(asset)
    db.commit()
