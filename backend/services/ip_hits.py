import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx
from ipaddress import ip_address

from services.database import ip_hits_collection

logger = logging.getLogger("voicera.ip_hits")


def _is_public_ip(ip: str) -> bool:
    try:
        addr = ip_address(ip)
        return not (addr.is_private or addr.is_loopback or addr.is_reserved or addr.is_link_local)
    except Exception:
        return False


def _normalize_ip(ip: str) -> Optional[str]:
    try:
        return str(ip_address(ip))  # canonical/compressed form
    except Exception:
        return None


async def ensure_indexes() -> None:
    try:
        await ip_hits_collection.create_index("ip", unique=True, name="uniq_ip")
        await ip_hits_collection.create_index("country_code", name="idx_country_code")
    except Exception as e:
        # If index exists or server returns a benign error, just log and continue
        logger.info("ip_hits index ensure: %s", getattr(e, "details", str(e)))


async def _fetch_json(client: httpx.AsyncClient, url: str, headers: Optional[Dict[str, str]] = None) -> Optional[Dict[str, Any]]:
    try:
        r = await client.get(url, headers=headers, timeout=2.0)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


async def geolocate_ip(ip: str, cf_country: Optional[str] = None) -> Dict[str, Optional[str]]:
    """Return best-effort geolocation for the IP.

    Fields: country, country_code, region, region_code, source
    """
    result: Dict[str, Optional[str]] = {
        "country": None,
        "country_code": None,
        "region": None,
        "region_code": None,
        "source": None,
    }

    # If Cloudflare country header is present, prefer it for country_code
    if cf_country and isinstance(cf_country, str) and 1 <= len(cf_country) <= 3:
        result["country_code"] = cf_country.upper()
        result["source"] = (result["source"] or "") + ("cf ")

    token_ipinfo = os.getenv("IPINFO_TOKEN")

    async with httpx.AsyncClient(headers={"Accept": "application/json"}) as client:
        # Try ipinfo (if token available)
        if token_ipinfo:
            data = await _fetch_json(client, f"https://ipinfo.io/{ip}?token={token_ipinfo}")
            if data:
                # ipinfo provides 2-letter country code
                result["country_code"] = data.get("country") or result["country_code"]
                # Some plans include region
                region = data.get("region") or None
                result["region"] = region or result["region"]
                result["source"] = (result["source"] or "") + ("ipinfo ")
                if result["country_code"] and result["region"]:
                    return result

        # Try ipapi.co (free, often reliable)
        data = await _fetch_json(client, f"https://ipapi.co/{ip}/json/")
        if data and not data.get("error"):
            result["country"] = data.get("country_name") or result["country"]
            result["country_code"] = data.get("country") or result["country_code"]
            result["region"] = data.get("region") or result["region"]
            result["region_code"] = data.get("region_code") or result["region_code"]
            result["source"] = (result["source"] or "") + ("ipapi ")
            if result["country_code"] and result["region"]:
                return result

        # Try ipwhois.app
        data = await _fetch_json(client, f"https://ipwhois.app/json/{ip}?objects=country,country_code,region,region_code")
        if data and data.get("success", True):
            result["country"] = data.get("country") or result["country"]
            result["country_code"] = data.get("country_code") or result["country_code"]
            result["region"] = data.get("region") or result["region"]
            result["region_code"] = data.get("region_code") or result["region_code"]
            result["source"] = (result["source"] or "") + ("ipwhois ")

    return result


async def record_ip_hit(ip: Optional[str], cf_country: Optional[str] = None, user_agent: Optional[str] = None) -> None:
    """Insert a new unique IP hit with geo if it's not already present.

    - Skips private/loopback/reserved IPs
    - Avoids external calls if IP already exists
    - Uses upsert with $setOnInsert to be race-safe
    """
    if not ip:
        return
    if not _is_public_ip(ip):
        return

    norm = _normalize_ip(ip)
    if not norm:
        return

    try:
        existing = await ip_hits_collection.find_one({"ip": norm}, projection={"_id": 1})
        if existing:
            return

        geo = await geolocate_ip(norm, cf_country=cf_country)

        doc = {
            "ip": norm,
            "country": geo.get("country"),
            "country_code": geo.get("country_code"),
            "region": geo.get("region"),
            "region_code": geo.get("region_code"),
            "first_seen": datetime.now(timezone.utc),
        }
        # Optionally store a tiny UA sample for debugging only (no PII beyond UA string)
        if user_agent:
            doc["ua_sample"] = str(user_agent)[:200]

        await ip_hits_collection.update_one(
            {"ip": norm},
            {"$setOnInsert": doc},
            upsert=True,
        )
    except Exception as e:
        # Fault tolerant: swallow errors to never impact request path
        logger.warning("record_ip_hit failed: %s", getattr(e, "details", str(e)))


def schedule_record_ip_hit(ip: Optional[str], cf_country: Optional[str] = None, user_agent: Optional[str] = None) -> None:
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(record_ip_hit(ip, cf_country=cf_country, user_agent=user_agent))
    except RuntimeError:
        # No running loop (unlikely in FastAPI), run fire-and-forget via asyncio
        asyncio.run(record_ip_hit(ip, cf_country=cf_country, user_agent=user_agent))
