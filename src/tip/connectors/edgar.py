"""
SEC EDGAR Connector - Polls data.sec.gov for filings on a CIK watchlist.

SEC Rate Limits (IMPORTANT):
- Max 10 requests/second (we default to 2 rps)
- User-Agent header required with contact info
- Respect Retry-After headers on 429/403

This connector uses conservative rate limiting and caching to stay
well within SEC limits and be a "polite" automated client.
"""
from __future__ import annotations

import asyncio
import hashlib
import random
import time
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Dict, Any, List, Optional, Tuple
import logging

import requests

from tip.connectors.base import BaseConnector, ConnectorConfig
from tip.models import EventType

logger = logging.getLogger(__name__)

# SEC hard limit is 10 rps - we NEVER exceed 8 rps in code
SEC_ABSOLUTE_MAX_RPS = 8
DEFAULT_RPS = 2.0

# Default forms to track
DEFAULT_FORMS_ALLOWLIST = [
    "8-K", "10-Q", "10-K", "S-1",
    "424B1", "424B2", "424B3", "424B4", "424B5",
    "13D", "13G", "SC 13D", "SC 13G",
    "4", "3", "5"
]


@dataclass
class RateLimiter:
    """Token bucket rate limiter for SEC requests."""
    max_rps: float = DEFAULT_RPS
    tokens: float = field(init=False)
    last_refill: float = field(init=False)
    
    def __post_init__(self):
        # Hard cap - NEVER exceed SEC safety limit
        if self.max_rps > SEC_ABSOLUTE_MAX_RPS:
            logger.warning(f"RPS capped from {self.max_rps} to {SEC_ABSOLUTE_MAX_RPS}")
            self.max_rps = SEC_ABSOLUTE_MAX_RPS
        self.tokens = self.max_rps
        self.last_refill = time.time()
    
    def acquire(self) -> None:
        """Acquire a token, blocking if necessary."""
        while True:
            now = time.time()
            elapsed = now - self.last_refill
            self.tokens = min(self.max_rps, self.tokens + elapsed * self.max_rps)
            self.last_refill = now
            
            if self.tokens >= 1:
                self.tokens -= 1
                return
            
            wait_time = (1 - self.tokens) / self.max_rps
            time.sleep(wait_time)


@dataclass
class EDGARConfig:
    """EDGAR-specific configuration."""
    ciks: List[str]  # List of 10-digit zero-padded CIKs
    user_agent_name: str = "TradingIntelPlatform"
    user_agent_email: str = "contact@example.com"
    max_rps: float = DEFAULT_RPS
    forms_allowlist: List[str] = field(default_factory=lambda: DEFAULT_FORMS_ALLOWLIST.copy())
    state_db_path: str = "./edgar_state.db"
    
    @property
    def user_agent(self) -> str:
        return f"{self.user_agent_name} {self.user_agent_email} (tip-edgar-connector)"


class EDGARConnector(BaseConnector):
    """
    SEC EDGAR filing connector.
    
    Polls data.sec.gov for new filings on a watchlist of CIKs.
    Respects SEC rate limits and uses conditional requests.
    """
    
    def __init__(
        self,
        cfg: ConnectorConfig,
        s3,
        bus=None,
        edgar_cfg: Optional[EDGARConfig] = None,
    ):
        super().__init__(cfg, s3, bus)
        self.edgar_cfg = edgar_cfg or EDGARConfig(ciks=[])
        self.rate_limiter = RateLimiter(max_rps=self.edgar_cfg.max_rps)
        self.forms_allowlist = set(f.upper() for f in self.edgar_cfg.forms_allowlist)
        
        # Initialize state database for deduplication
        self._init_state_db()
        
        # Session for HTTP requests
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.edgar_cfg.user_agent,
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate",
        })
        
        # Consecutive error tracking for cooldown
        self._consecutive_errors = 0
        self._in_cooldown = False
    
    def _init_state_db(self) -> None:
        """Initialize SQLite database for state tracking."""
        db_path = Path(self.edgar_cfg.state_db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        
        conn = sqlite3.connect(str(db_path))
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS seen_filings (
                cik TEXT NOT NULL,
                accession TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                PRIMARY KEY (cik, accession)
            );
            CREATE TABLE IF NOT EXISTS cik_state (
                cik TEXT PRIMARY KEY,
                last_etag TEXT,
                last_modified TEXT,
                last_poll_at TEXT
            );
        """)
        conn.commit()
        conn.close()
        logger.info(f"EDGAR state DB initialized: {db_path}")
    
    def _is_seen(self, cik: str, accession: str) -> bool:
        """Check if we've already processed this filing."""
        conn = sqlite3.connect(self.edgar_cfg.state_db_path)
        cursor = conn.execute(
            "SELECT 1 FROM seen_filings WHERE cik = ? AND accession = ?",
            (cik, accession)
        )
        result = cursor.fetchone() is not None
        conn.close()
        return result
    
    def _mark_seen(self, cik: str, accession: str) -> None:
        """Mark a filing as seen."""
        conn = sqlite3.connect(self.edgar_cfg.state_db_path)
        conn.execute(
            "INSERT OR IGNORE INTO seen_filings (cik, accession, first_seen_at) VALUES (?, ?, ?)",
            (cik, accession, datetime.now(timezone.utc).isoformat())
        )
        conn.commit()
        conn.close()
    
    def _get_cik_state(self, cik: str) -> Tuple[Optional[str], Optional[str]]:
        """Get cached ETag and Last-Modified for a CIK."""
        conn = sqlite3.connect(self.edgar_cfg.state_db_path)
        cursor = conn.execute(
            "SELECT last_etag, last_modified FROM cik_state WHERE cik = ?",
            (cik,)
        )
        row = cursor.fetchone()
        conn.close()
        return (row[0], row[1]) if row else (None, None)
    
    def _update_cik_state(self, cik: str, etag: Optional[str], last_modified: Optional[str]) -> None:
        """Update cached state for a CIK."""
        conn = sqlite3.connect(self.edgar_cfg.state_db_path)
        conn.execute(
            """
            INSERT INTO cik_state (cik, last_etag, last_modified, last_poll_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(cik) DO UPDATE SET
                last_etag = COALESCE(excluded.last_etag, last_etag),
                last_modified = COALESCE(excluded.last_modified, last_modified),
                last_poll_at = excluded.last_poll_at
            """,
            (cik, etag, last_modified, datetime.now(timezone.utc).isoformat())
        )
        conn.commit()
        conn.close()
    
    def _fetch_cik(self, cik: str) -> Tuple[Optional[Dict], bool]:
        """
        Fetch submissions for a CIK with rate limiting and conditional request.
        
        Returns:
            (data, was_modified) - data is None if 304 Not Modified
        """
        # Rate limit
        self.rate_limiter.acquire()
        
        # Get cached headers
        etag, last_modified = self._get_cik_state(cik)
        
        # Build request
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        headers = {}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified
        
        try:
            response = self.session.get(url, headers=headers, timeout=30)
            
            # Not modified
            if response.status_code == 304:
                logger.debug(f"CIK {cik} not modified (304)")
                self._update_cik_state(cik, etag, last_modified)
                self._consecutive_errors = 0
                return None, False
            
            # Rate limited or forbidden
            if response.status_code in (429, 403):
                self._handle_rate_limit(response)
                return None, False
            
            # Server error
            if response.status_code >= 500:
                logger.warning(f"SEC server error {response.status_code} for CIK {cik}")
                return None, False
            
            response.raise_for_status()
            
            # Success - update cache
            new_etag = response.headers.get("ETag")
            new_last_modified = response.headers.get("Last-Modified")
            self._update_cik_state(cik, new_etag, new_last_modified)
            self._consecutive_errors = 0
            
            return response.json(), True
            
        except requests.RequestException as e:
            logger.error(f"Request error for CIK {cik}: {e}")
            return None, False
    
    def _handle_rate_limit(self, response: requests.Response) -> None:
        """Handle SEC rate limiting."""
        self._consecutive_errors += 1
        
        retry_after = response.headers.get("Retry-After")
        wait_time = int(retry_after) if retry_after else 60
        
        logger.warning(
            f"Rate limited by SEC (status={response.status_code}), "
            f"waiting {wait_time}s, consecutive_errors={self._consecutive_errors}"
        )
        
        # Enter cooldown after repeated errors
        if self._consecutive_errors >= 3:
            cooldown = 10 * 60 * random.uniform(0.8, 1.2)  # 8-12 minutes
            logger.critical(f"ENTERING COOLDOWN MODE for {cooldown/60:.1f} minutes")
            time.sleep(cooldown)
            self._consecutive_errors = 0
        else:
            time.sleep(wait_time)
    
    def fetch(self) -> Iterable[Dict[str, Any]]:
        """Fetch new filings from all CIKs in the watchlist."""
        if not self.edgar_cfg.ciks:
            logger.warning("No CIKs configured for EDGAR connector")
            return
        
        logger.info(f"Polling {len(self.edgar_cfg.ciks)} CIKs for new filings")
        
        for cik in self.edgar_cfg.ciks:
            # Add jitter between CIKs
            time.sleep(random.uniform(0.1, 0.5))
            
            data, was_modified = self._fetch_cik(cik)
            
            if not was_modified or data is None:
                continue
            
            # Parse filings
            recent = data.get("filings", {}).get("recent", {})
            if not recent:
                continue
            
            accessions = recent.get("accessionNumber", [])
            forms = recent.get("form", [])
            filing_dates = recent.get("filingDate", [])
            primary_docs = recent.get("primaryDocument", [])
            
            cik_no_padding = str(int(cik))
            
            for i in range(min(100, len(accessions))):
                form = forms[i] if i < len(forms) else ""
                
                # Filter by forms allowlist
                if form.upper() not in self.forms_allowlist:
                    continue
                
                accession = accessions[i]
                
                # Skip already seen
                if self._is_seen(cik, accession):
                    continue
                
                filing_date = filing_dates[i] if i < len(filing_dates) else ""
                primary_doc = primary_docs[i] if i < len(primary_docs) else ""
                
                # Build filing index URL
                accession_no_dashes = accession.replace("-", "")
                filing_url = (
                    f"https://www.sec.gov/Archives/edgar/data/{cik_no_padding}/"
                    f"{accession_no_dashes}/{accession}-index.html"
                )
                
                # Mark as seen before yielding
                self._mark_seen(cik, accession)
                
                yield {
                    "cik": cik,
                    "form": form,
                    "accession": accession,
                    "filingDate": filing_date,
                    "filingIndexUrl": filing_url,
                    "primaryDocument": primary_doc,
                    "companyName": data.get("name", ""),
                    "tickers": data.get("tickers", []),
                }
    
    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a filing into a TIP event."""
        # Try to get primary ticker
        tickers = raw.get("tickers", [])
        symbol = tickers[0] if tickers else None
        
        # Parse filing date
        filing_date_str = raw.get("filingDate", "")
        try:
            ts_event = datetime.strptime(filing_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            ts_event = datetime.now(timezone.utc)
        
        # Severity based on form type
        form = raw.get("form", "").upper()
        if form in ("8-K",):
            severity = 70  # Material events
        elif form in ("10-K", "10-Q"):
            severity = 60  # Periodic reports
        elif form in ("4", "3", "5"):
            severity = 50  # Insider transactions
        elif form in ("13D", "13G", "SC 13D", "SC 13G"):
            severity = 65  # Significant ownership
        elif form.startswith("S-") or form.startswith("424"):
            severity = 55  # Offerings
        else:
            severity = 50
        
        return {
            "eventType": EventType.DISCLOSURE_FILING,
            "symbol": symbol,
            "entityId": raw.get("cik"),
            "tsEvent": ts_event,
            "severity": severity,
            "confidence": 1.0,  # SEC filings are authoritative
            "payload": {
                "cik": raw.get("cik"),
                "form": raw.get("form"),
                "accession": raw.get("accession"),
                "filingDate": raw.get("filingDate"),
                "filingUrl": raw.get("filingIndexUrl"),
                "primaryDocument": raw.get("primaryDocument"),
                "companyName": raw.get("companyName"),
                "tickers": raw.get("tickers", []),
            },
            "dedupeKey": f"edgar:{raw.get('cik')}:{raw.get('accession')}",
        }


def normalize_cik(cik: str) -> str:
    """Normalize CIK to 10-digit zero-padded format."""
    return f"{int(cik):010d}"

