from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from .config import settings
from .database import SessionLocal, get_db, init_db
from .models import Analysis, PaperSignal
from .schemas import AnalysisRequest, RefreshRequest
from .services.analyzer import TokenAnalyzer
from .services.notify import send_telegram
from .services.providers import DexScreenerClient, ProviderError

scheduler = AsyncIOScheduler(timezone="UTC")


async def run_and_store(
    *, mint: str, mode: str, note: str | None, db: Session, send_alerts: bool = True
) -> dict[str, Any]:
    analyzer = TokenAnalyzer(settings)
    result = await analyzer.run(mint=mint, mode=mode, note=note)
    record = Analysis(mint=mint, mode=mode, status="complete", result_json=json.dumps(result))
    db.add(record)
    db.flush()  # receive record.id before persisting paper candidates

    created_signals: list[PaperSignal] = []
    for candidate in result["signals"]:
        if not candidate["paper_track_eligible"]:
            continue
        token = candidate["token"]
        # One open paper position per token prevents a scheduled scan from endlessly
        # opening duplicate hypothetical entries.
        existing = db.scalar(
            select(PaperSignal).where(
                PaperSignal.token_address == token["address"], PaperSignal.status == "open"
            )
        )
        if existing:
            continue
        paper = PaperSignal(
            source_analysis_id=record.id,
            token_address=token["address"],
            symbol=candidate["symbol"],
            consensus_wallets=candidate["independent_wallet_count"],
            score=candidate["score"],
            entry_price_usd=token.get("price_usd"),
            current_price_usd=token.get("price_usd"),
            return_pct=0.0 if token.get("price_usd") else None,
            detail_json=json.dumps(candidate),
        )
        db.add(paper)
        created_signals.append(paper)
    db.commit()

    # Never send synthetic alerts. Live alerts are sent only for newly opened paper signals.
    if send_alerts and mode == "live" and settings.telegram_ready:
        for paper in created_signals:
            if paper.score < settings.alert_score_threshold:
                continue
            message = (
                "Wallet Radar — kandidat perlu review manual\n"
                f"{paper.symbol} | skor {paper.score}/100 | {paper.consensus_wallets} wallet/cluster\n"
                f"Alamat: {paper.token_address}\n"
                "Ini bukan rekomendasi beli. Periksa hard gate, holder, authority, dan slippage."
            )
            paper.alert_sent = await send_telegram(settings, message)
        db.commit()

    return {
        "analysis_id": record.id,
        "result": result,
        "new_paper_signals": [serialize_signal(item) for item in created_signals],
    }


def serialize_signal(item: PaperSignal) -> dict[str, Any]:
    return {
        "id": item.id,
        "token_address": item.token_address,
        "symbol": item.symbol,
        "consensus_wallets": item.consensus_wallets,
        "score": item.score,
        "status": item.status,
        "entry_price_usd": item.entry_price_usd,
        "current_price_usd": item.current_price_usd,
        "return_pct": item.return_pct,
        "alert_sent": item.alert_sent,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def serialize_analysis(item: Analysis, include_result: bool = False) -> dict[str, Any]:
    data = {
        "id": item.id,
        "mint": item.mint,
        "mode": item.mode,
        "status": item.status,
        "error": item.error,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }
    if include_result:
        data["result"] = json.loads(item.result_json)
    return data


async def scheduled_rescan() -> None:
    """Optional, deliberately disabled unless the user sets AUTO_SCAN_INTERVAL_MINUTES.

    It scans only distinct live seed mints previously run by the user; it never creates
    external trades and it honours the provider quota chosen by the user.
    """
    db = SessionLocal()
    try:
        records = db.scalars(
            select(Analysis).where(Analysis.mode == "live").order_by(desc(Analysis.created_at)).limit(50)
        ).all()
        seen: set[str] = set()
        for record in records:
            if record.mint in seen:
                continue
            seen.add(record.mint)
            try:
                await run_and_store(mint=record.mint, mode="live", note="scheduled re-scan", db=db)
            except Exception:
                # Individual provider failures are visible on a manual rerun; scheduler
                # intentionally continues so one token cannot block the whole watchlist.
                db.rollback()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    if settings.auto_scan_interval_minutes > 0:
        scheduler.add_job(
            scheduled_rescan,
            "interval",
            minutes=settings.auto_scan_interval_minutes,
            id="live-wallet-rescan",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        scheduler.start()
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "app": settings.app_name, "time": datetime.utcnow().isoformat() + "Z"}


@app.get("/api/config")
def public_config() -> dict[str, Any]:
    return {
        "demo_default": settings.demo_mode,
        "live_ready": settings.live_ready,
        "telegram_ready": settings.telegram_ready,
        "scheduled_scans_enabled": settings.auto_scan_interval_minutes > 0,
        "scan_interval_minutes": settings.auto_scan_interval_minutes,
        "min_consensus_wallets": settings.min_consensus_wallets,
        "min_liquidity_usd": settings.min_liquidity_usd,
    }


@app.post("/api/analyses")
async def create_analysis(payload: AnalysisRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    # Demo remains explicit even if live keys exist; live has to be selected in the UI.
    try:
        return await run_and_store(mint=payload.mint, mode=payload.mode, note=payload.note, db=db)
    except ProviderError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail=f"Analisis gagal: {exc}") from exc


@app.get("/api/analyses")
def list_analyses(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    items = db.scalars(select(Analysis).order_by(desc(Analysis.created_at)).limit(25)).all()
    return [serialize_analysis(item) for item in items]


@app.get("/api/analyses/{analysis_id}")
def get_analysis(analysis_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    item = db.get(Analysis, analysis_id)
    if not item:
        raise HTTPException(status_code=404, detail="Analisis tidak ditemukan.")
    return serialize_analysis(item, include_result=True)


@app.get("/api/paper-signals")
def list_paper_signals(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    items = db.scalars(select(PaperSignal).order_by(desc(PaperSignal.created_at)).limit(100)).all()
    return [serialize_signal(item) for item in items]


@app.post("/api/paper-signals/refresh")
async def refresh_paper_signals(payload: RefreshRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    statement = select(PaperSignal).where(PaperSignal.status == "open")
    if payload.signal_ids:
        statement = statement.where(PaperSignal.id.in_(payload.signal_ids))
    items = db.scalars(statement).all()
    dex = DexScreenerClient()
    updated = 0
    errors: list[str] = []
    for item in items:
        try:
            # Demo addresses generally have no public pair; their entry remains visible.
            market = await dex.market(item.token_address)
            if market.price_usd is None or market.security_status == "market_not_found":
                continue
            item.current_price_usd = market.price_usd
            if item.entry_price_usd and item.entry_price_usd > 0:
                item.return_pct = round((market.price_usd / item.entry_price_usd - 1) * 100, 2)
            updated += 1
        except ProviderError as exc:
            errors.append(str(exc))
    db.commit()
    return {"updated": updated, "errors": errors}


@app.post("/api/scans/run")
async def rescan_live_watchlist(db: Session = Depends(get_db)) -> dict[str, Any]:
    if not settings.live_ready:
        raise HTTPException(status_code=422, detail="Isi HELIUS_API_KEY dan BIRDEYE_API_KEY sebelum live re-scan.")
    latest = db.scalars(
        select(Analysis).where(Analysis.mode == "live").order_by(desc(Analysis.created_at)).limit(50)
    ).all()
    mints: list[str] = []
    for item in latest:
        if item.mint not in mints:
            mints.append(item.mint)
    if not mints:
        raise HTTPException(status_code=422, detail="Belum ada seed token live di watchlist.")
    completed: list[str] = []
    failures: list[dict[str, str]] = []
    for mint in mints:
        try:
            await run_and_store(mint=mint, mode="live", note="manual watchlist re-scan", db=db)
            completed.append(mint)
        except Exception as exc:
            db.rollback()
            failures.append({"mint": mint, "error": str(exc)})
    return {"completed": completed, "failures": failures}


STATIC_DIR = Path(__file__).parent / "static"
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
