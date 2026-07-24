import asyncio
import logging
import httpx
import json
import os
from typing import Optional, Dict, Any
import aiosqlite

from app.core.config import settings

logger = logging.getLogger("nexa.firebase")

DEFAULT_FIREBASE_URL = os.getenv("FIREBASE_DATABASE_URL", "https://nexa-prime-enterprise-default-rtdb.firebaseio.com")

class FirebaseManager:
    def __init__(self):
        self.firebase_url: str = DEFAULT_FIREBASE_URL
        self.api_key: Optional[str] = os.getenv("FIREBASE_API_KEY", None)
        self.is_configured: bool = True

    def configure(self, firebase_url: str, api_key: Optional[str] = None):
        """Configure Firebase Realtime / Firestore REST endpoint."""
        url = firebase_url.strip().rstrip("/")
        if not url.startswith("http"):
            url = f"https://{url}"
        self.firebase_url = url
        if api_key:
            self.api_key = api_key.strip()
        self.is_configured = True
        logger.info(f"🔥 Firebase Manager Configured with URL: {self.firebase_url}")

    async def test_connection(self) -> Dict[str, Any]:
        """Test read/write connection to Firebase."""
        if not self.firebase_url:
            return {"success": False, "error": "Firebase URL belirtilmedi."}
        
        endpoint = f"{self.firebase_url}/system_ping.json"
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                ping_data = {"status": "ok", "app": "NEXA PRIME Enterprise", "timestamp": str(asyncio.get_event_loop().time())}
                resp = await client.put(endpoint, json=ping_data)
                if resp.status_code == 200:
                    return {"success": True, "url": self.firebase_url, "data": resp.json()}
                else:
                    return {"success": False, "error": f"HTTP Status {resp.status_code}: {resp.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def sync_projects(self, db: aiosqlite.Connection) -> int:
        """Sync all 20 real estate projects to Firebase (/projects.json)."""
        async with db.execute("SELECT * FROM projects ORDER BY id ASC") as cursor:
            rows = await cursor.fetchall()
        
        projects_dict = {str(r["id"]): dict(r) for r in rows}
        endpoint = f"{self.firebase_url}/projects.json"

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.put(endpoint, json=projects_dict)
            if resp.status_code == 200:
                logger.info(f"✅ {len(projects_dict)} projects successfully synced to Firebase.")
                return len(projects_dict)
            else:
                raise RuntimeError(f"Firebase Sync Failed: {resp.status_code} — {resp.text}")

    async def sync_crm_customers(self, db: aiosqlite.Connection) -> int:
        """Sync all CRM customer leads to Firebase (/customers.json)."""
        async with db.execute("""
            SELECT c.*, p.name as project_name 
            FROM customers c 
            LEFT JOIN projects p ON c.project_id = p.id 
            ORDER BY c.id DESC
        """) as cursor:
            rows = await cursor.fetchall()
        
        customers_dict = {str(r["id"]): dict(r) for r in rows}
        endpoint = f"{self.firebase_url}/customers.json"

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.put(endpoint, json=customers_dict)
            if resp.status_code == 200:
                await db.execute("UPDATE customers SET firebase_synced = 1")
                await db.commit()
                logger.info(f"✅ {len(customers_dict)} CRM customers synced to Firebase.")
                return len(customers_dict)
            else:
                raise RuntimeError(f"Firebase CRM Sync Failed: {resp.status_code} — {resp.text}")

    async def sync_all(self, db: aiosqlite.Connection) -> Dict[str, Any]:
        """Perform 1-click full system sync (Projects + Customers + System Status) to Firebase."""
        p_count = await self.sync_projects(db)
        c_count = await self.sync_crm_customers(db)
        
        # Also sync system metadata
        async with httpx.AsyncClient(timeout=8.0) as client:
            meta = {
                "system": "NEXA PRIME Enterprise v3.5",
                "total_projects": p_count,
                "total_crm_leads": c_count,
                "status": "Online",
                "last_sync": "CURRENT_TIMESTAMP"
            }
            await client.put(f"{self.firebase_url}/system_metadata.json", json=meta)

        return {
            "success": True,
            "synced_projects": p_count,
            "synced_customers": c_count,
            "firebase_url": self.firebase_url
        }

firebase_manager = FirebaseManager()
