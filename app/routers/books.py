#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Brandista Books Router — AI Bookkeeper

Real AI-powered bookkeeping endpoints:
  1. Receipt analysis → structured journal entries
  2. Account suggestion → Finnish chart of accounts mapping
  3. Transaction history (in-memory for MVP)

Uses OpenAI GPT to parse receipts and suggest accounting entries
following Finnish accounting standards (kirjanpitolaki).
"""

import os
import json
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, date
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from app.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/books", tags=["Books"])

# ============================================================================
# MODELS
# ============================================================================

class ReceiptRequest(BaseModel):
    text: str = Field(..., description="Receipt text content (OCR or pasted)")

class JournalLine(BaseModel):
    account_code: str = Field(..., description="Finnish chart of accounts code")
    account_name: str = Field(..., description="Account name in Finnish")
    debit: Optional[float] = Field(None, description="Debit amount")
    credit: Optional[float] = Field(None, description="Credit amount")

class VatBreakdown(BaseModel):
    rate: float = Field(..., description="VAT rate percentage")
    net_amount: float = Field(..., description="Net amount (excl. VAT)")
    vat_amount: float = Field(..., description="VAT amount")
    total: float = Field(..., description="Total (incl. VAT)")

class ReceiptAnalysis(BaseModel):
    vendor: str = Field(..., description="Vendor/store name")
    date: Optional[str] = Field(None, description="Receipt date")
    total: float = Field(..., description="Total amount")
    currency: str = Field(default="EUR", description="Currency")
    category: str = Field(..., description="Expense category")
    description: str = Field(..., description="Transaction description in Finnish")
    journal_entries: List[JournalLine] = Field(..., description="Suggested journal entries")
    vat_breakdown: List[VatBreakdown] = Field(default_factory=list, description="VAT breakdown")
    confidence: float = Field(..., description="AI confidence 0-1")
    notes: Optional[str] = Field(None, description="Additional notes or warnings")

class AccountSuggestionRequest(BaseModel):
    description: str = Field(..., description="Transaction description")
    amount: float = Field(default=0, description="Transaction amount")

class AccountSuggestion(BaseModel):
    account_code: str = Field(..., description="Account code")
    account_name: str = Field(..., description="Account name")
    confidence: float = Field(..., description="Match confidence 0-1")
    reason: str = Field(..., description="Why this account was suggested")

class AccountSuggestionResponse(BaseModel):
    description: str
    amount: float
    suggestions: List[AccountSuggestion]
    vat_code: Optional[str] = None
    vat_rate: Optional[float] = None
    journal_entries: List[JournalLine] = Field(default_factory=list)

class TransactionRecord(BaseModel):
    id: str
    date: str
    vendor: str
    description: str
    amount: float
    category: str
    account_code: str
    account_name: str
    vat_rate: Optional[float] = None
    created_at: str

# In-memory transaction store for MVP
_transactions: Dict[str, List[TransactionRecord]] = {}

# ============================================================================
# OPENAI HELPER
# ============================================================================

async def _call_gpt(system_prompt: str, user_message: str) -> str:
    """Call OpenAI GPT and return the response text."""
    try:
        from openai import AsyncOpenAI
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(503, "OpenAI API key not configured")

        client = AsyncOpenAI(api_key=api_key)
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.2,
            max_tokens=2000,
        )
        return response.choices[0].message.content.strip()
    except ImportError:
        raise HTTPException(503, "OpenAI library not available")

# ============================================================================
# RECEIPT ANALYSIS
# ============================================================================

RECEIPT_SYSTEM_PROMPT = """Olet AI Bookkeeper — suomalaisen kirjanpidon asiantuntija.

Analysoi annettu kuitti ja palauta JSON-muodossa:

{
  "vendor": "Kaupan/yrityksen nimi",
  "date": "YYYY-MM-DD tai null",
  "total": 123.45,
  "currency": "EUR",
  "category": "yksi: ruoka, toimistotarvikkeet, matkakulut, edustus, polttoaine, it-palvelut, markkinointi, puhelin, vakuutus, vuokra, koulutus, muu",
  "description": "Lyhyt kuvaus kirjaukselle suomeksi",
  "journal_entries": [
    {"account_code": "4000", "account_name": "Ostot", "debit": 100.00, "credit": null},
    {"account_code": "2939", "account_name": "ALV-saamiset", "debit": 25.50, "credit": null},
    {"account_code": "1910", "account_name": "Pankkitili", "debit": null, "credit": 125.50}
  ],
  "vat_breakdown": [
    {"rate": 25.5, "net_amount": 100.00, "vat_amount": 25.50, "total": 125.50}
  ],
  "confidence": 0.85,
  "notes": "Mahdolliset varoitukset tai lisätiedot"
}

Suomalainen tilikartta (yleisimmät):
- 1910 Pankkitili
- 2939 ALV-saamiset (ostojen ALV)
- 2871 ALV-velka (myyntien ALV)
- 4000 Ostot (tavarat)
- 4100 Ulkopuoliset palvelut
- 6300 Vuokrat
- 6400 Matkakulut
- 6500 Edustuskulut
- 6800 Toimistotarvikkeet
- 6900 IT-kulut ja ohjelmistot
- 7000 Markkinointikulut
- 7100 Puhelinkulut
- 7200 Vakuutukset
- 7500 Koulutuskulut

ALV-kannat Suomessa (2024-):
- 25.5% yleinen
- 14% ruoka, ravintolat
- 10% kirjat, lääkkeet, liikunta, kulttuuri
- 0% terveydenhuolto, koulutus, rahoitus

TÄRKEÄÄ:
- Kirjausten debit = credit (tasapaino)
- ALV lasketaan automaattisesti oikein
- Käytä oikeita suomalaisia tilikoodeja
- Palauta VAIN validi JSON, ei muuta tekstiä"""


@router.post("/analyze-receipt", response_model=ReceiptAnalysis)
async def analyze_receipt(
    req: ReceiptRequest,
    user: dict = Depends(get_current_user),
):
    """
    Analyze a receipt and suggest journal entries.
    Uses GPT to parse receipt text and map to Finnish chart of accounts.
    """
    if not req.text.strip():
        raise HTTPException(400, "Receipt text cannot be empty")

    if len(req.text) > 5000:
        raise HTTPException(400, "Receipt text too long (max 5000 chars)")

    logger.info(f"[Books] Analyzing receipt for {user.get('username', '?')} ({len(req.text)} chars)")

    try:
        raw = await _call_gpt(RECEIPT_SYSTEM_PROMPT, req.text)

        # Strip markdown code block if GPT wraps it
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

        data = json.loads(raw)
        result = ReceiptAnalysis(**data)

        # Save transaction record for the user
        user_id = user.get("username", "anonymous")
        record = TransactionRecord(
            id=str(uuid4()),
            date=result.date or datetime.now().strftime("%Y-%m-%d"),
            vendor=result.vendor,
            description=result.description,
            amount=result.total,
            category=result.category,
            account_code=result.journal_entries[0].account_code if result.journal_entries else "4000",
            account_name=result.journal_entries[0].account_name if result.journal_entries else "Ostot",
            vat_rate=result.vat_breakdown[0].rate if result.vat_breakdown else None,
            created_at=datetime.now().isoformat(),
        )
        _transactions.setdefault(user_id, []).append(record)

        logger.info(f"[Books] ✅ Receipt analyzed: {result.vendor} {result.total}€ → {len(result.journal_entries)} entries")
        return result

    except json.JSONDecodeError as e:
        logger.error(f"[Books] GPT returned invalid JSON: {e}")
        raise HTTPException(500, "AI-kirjanpitäjä palautti virheellisen vastauksen. Yritä uudelleen.")
    except Exception as e:
        logger.error(f"[Books] Receipt analysis failed: {e}", exc_info=True)
        raise HTTPException(500, f"Kuitin analysointi epäonnistui: {str(e)[:200]}")


# ============================================================================
# ACCOUNT SUGGESTION
# ============================================================================

ACCOUNT_SYSTEM_PROMPT = """Olet AI Bookkeeper — suomalaisen kirjanpidon asiantuntija.

Käyttäjä kuvaa pankkitapahtuman. Ehdota sopivat tilit suomalaisesta tilikartasta.

Palauta JSON:

{
  "description": "Käyttäjän kuvaus",
  "amount": 123.45,
  "suggestions": [
    {
      "account_code": "6900",
      "account_name": "IT-kulut ja ohjelmistot",
      "confidence": 0.92,
      "reason": "Microsoft 365 on tyypillinen IT-ohjelmistokulu"
    },
    {
      "account_code": "4100",
      "account_name": "Ulkopuoliset palvelut",
      "confidence": 0.65,
      "reason": "Vaihtoehtoinen tili jos kyseessä ulkoistettu palvelu"
    }
  ],
  "vat_code": "25.5%",
  "vat_rate": 25.5,
  "journal_entries": [
    {"account_code": "6900", "account_name": "IT-kulut", "debit": 100.00, "credit": null},
    {"account_code": "2939", "account_name": "ALV-saamiset", "debit": 25.50, "credit": null},
    {"account_code": "1910", "account_name": "Pankkitili", "debit": null, "credit": 125.50}
  ]
}

Suomalainen tilikartta (yleisimmät):
- 1910 Pankkitili
- 2939 ALV-saamiset
- 3000 Myynti
- 4000 Ostot (tavarat)
- 4100 Ulkopuoliset palvelut
- 5000 Palkat
- 5200 Eläkevakuutus (TyEL)
- 5400 Sosiaaliturvamaksut
- 6300 Vuokrat
- 6400 Matkakulut
- 6500 Edustuskulut
- 6800 Toimistotarvikkeet
- 6900 IT-kulut ja ohjelmistot
- 7000 Markkinointikulut
- 7100 Puhelinkulut
- 7200 Vakuutukset
- 7300 Pankkikulut
- 7500 Koulutuskulut
- 8000 Poistot
- 9000 Tuloverot

Anna 2-3 ehdotusta luottamusjärjestyksessä.
Palauta VAIN validi JSON, ei muuta tekstiä."""


@router.post("/suggest-accounts", response_model=AccountSuggestionResponse)
async def suggest_accounts(
    req: AccountSuggestionRequest,
    user: dict = Depends(get_current_user),
):
    """
    Suggest accounting entries for a described transaction.
    """
    if not req.description.strip():
        raise HTTPException(400, "Description cannot be empty")

    logger.info(f"[Books] Account suggestion for: {req.description[:60]}...")

    user_msg = f"Tapahtuma: {req.description}\nSumma: {req.amount}€"

    try:
        raw = await _call_gpt(ACCOUNT_SYSTEM_PROMPT, user_msg)

        # Strip markdown code block
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

        data = json.loads(raw)
        # Ensure description/amount are set from request
        data["description"] = req.description
        data["amount"] = req.amount

        result = AccountSuggestionResponse(**data)
        logger.info(f"[Books] ✅ Suggested {len(result.suggestions)} accounts")
        return result

    except json.JSONDecodeError as e:
        logger.error(f"[Books] GPT returned invalid JSON: {e}")
        raise HTTPException(500, "AI-kirjanpitäjä palautti virheellisen vastauksen. Yritä uudelleen.")
    except Exception as e:
        logger.error(f"[Books] Account suggestion failed: {e}", exc_info=True)
        raise HTTPException(500, f"Tiliöintiehdotus epäonnistui: {str(e)[:200]}")


# ============================================================================
# TRANSACTION HISTORY (in-memory for MVP)
# ============================================================================

@router.get("/transactions", response_model=List[TransactionRecord])
async def get_transactions(
    user: dict = Depends(get_current_user),
):
    """Get analyzed transaction history for the current user."""
    user_id = user.get("username", "anonymous")
    txs = _transactions.get(user_id, [])
    # Return newest first
    return list(reversed(txs))


@router.get("/summary")
async def get_summary(
    user: dict = Depends(get_current_user),
):
    """Get expense summary by category."""
    user_id = user.get("username", "anonymous")
    txs = _transactions.get(user_id, [])

    by_category: Dict[str, float] = {}
    by_account: Dict[str, float] = {}
    total = 0.0

    for tx in txs:
        by_category[tx.category] = by_category.get(tx.category, 0) + tx.amount
        key = f"{tx.account_code} {tx.account_name}"
        by_account[key] = by_account.get(key, 0) + tx.amount
        total += tx.amount

    return {
        "total_amount": round(total, 2),
        "transaction_count": len(txs),
        "by_category": {k: round(v, 2) for k, v in sorted(by_category.items(), key=lambda x: -x[1])},
        "by_account": {k: round(v, 2) for k, v in sorted(by_account.items(), key=lambda x: -x[1])},
    }
