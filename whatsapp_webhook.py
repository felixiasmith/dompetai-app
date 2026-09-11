import os
import json
import httpx
from fastapi import APIRouter, Request, HTTPException, status, Depends
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
from pydantic import BaseModel
from typing import Optional

# Import mesin mutasi saldo yang kita buat sebelumnya
from ledger_service import process_transaction_ledger, TransactionIn

router = APIRouter(prefix="/api/v1/webhook", tags=["WhatsApp Webhook"])

# Koneksi Database Helper (Asumsi diinisialisasi di main.py)
async def get_db_client():
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    return AsyncIOMotorClient(mongo_uri)

# 1. Skema Payload Masuk dari Webhook WhatsApp (Struktur Sederhana)
class WhatsAppMessage(BaseModel):
    phone_number: str
    message_text: str
    timestamp: Optional[str] = None

# 2. Fungsi untuk Menghubungkan Teks ke Gemini 3.7 Flash via Emergent Key
async def call_gemini_37_flash_parser(raw_text: str) -> list:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY belum dikonfigurasi di environment.")

    # Endpoint resmi untuk pengisian model terstruktur Gemini
    url = f"https://googleapis.com{api_key}"
    
    # Masukkan System Prompt yang telah kita desain di Phase 1
    system_instruction = (
        "Bertindaklah sebagai mesin ekstraksi data keuangan (NLP Financial Parser) untuk DompetAI. "
        "Ubah pesan teks WhatsApp menjadi format JSON Array of Objects. "
        "Tanggal hari ini: 2026-09-11. Aturan Kategori: Needs, Wants, Savings, Allocation. "
        "Tipe transaksi wajib memilih: INFLOW, OUTFLOW, TRANSFER, DEBT, RECEIVABLE. "
        "Gunakan 'w_bca_01' untuk BCA, 'w_gopay_02' untuk GoPay, dan 'w_cash_03' untuk tunai/default."
    )

    payload = {
        "contents": [{"parts": [{"text": raw_text}]}],
        "systemInstruction": {"parts": [{"text": system_instruction}]},
        "generationConfig": {
            # Mengunci model agar WAJIB mengembalikan format JSON murni sesuai skema
            "responseMimeType": "application/json",
            # Mengaktifkan Gemini 3.7 Reasoning: set budget token berpikir
            "thinkingConfig": {
                "thinkingBudget": 1024 
            }
        }
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, timeout=30.0)
        if response.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Gemini API Error: {response.text}")
        
        result_json = response.json()
        try:
            # Ekstrak string JSON murni dari teks balasan Gemini
            raw_content = result_json["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(raw_content)
        except (KeyError, IndexError, json.JSONDecodeError):
            raise HTTPException(status_code=422, detail="Gagal mengurai response JSON terstruktur dari Gemini.")

# 3. Endpoint Utama Webhook WhatsApp (Human-In-The-Loop / Auto-Save)
@router.post("/whatsapp")
async def receive_whatsapp_chat(
    payload: WhatsAppMessage, 
    db_client: AsyncIOMotorClient = Depends(get_db_client)
):
    # Simulasi mapping nomor WhatsApp ke User ID terdaftar di sistem MongoDB Anda
    user_id = f"user_{payload.phone_number}" 
    
    # Langkah A: Kirim teks chat mentah ke Gemini 3.7 Flash untuk diekstrak
    parsed_transactions = await call_gemini_37_flash_parser(payload.message_text)
    
    saved_transactions = []
    
    # Langkah B: Iterasi hasil parsing (Mendukung multi-transaksi dalam satu chat)
    for tx in parsed_transactions:
        # Jika tingkat keyakinan AI rendah (low confidence), simpan sebagai DRAFT untuk verifikasi web
        if tx.get("confidence") == "low":
            db = db_client["dompet_ai_db"]
            tx["user_id"] = user_id
            tx["status"] = "DRAFT_PENDING_VERIFICATION"
            tx["created_at"] = datetime.utcnow()
            await db.draft_transactions.insert_one(tx)
            continue
            
        # Jika keyakinan tinggi (high confidence), langsung mutasikan ke saldo rekening real-time
        ledger_payload = TransactionIn(
            user_id=user_id,
            description=tx.get("description", "Transaksi WhatsApp"),
            amount=float(tx.get("amount", 0)),
            transaction_type=tx.get("transaction_type", "OUTFLOW"),
            category=tx.get("category", "Wants"),
            source_wallet_id=tx.get("source_wallet", "w_cash_03"),
            destination_wallet_id=tx.get("destination_wallet"),
            raw_nlp_text=payload.message_text
        )
        
        # Panggil service ledger otomatis dari Phase 2 bagian 1
        res = await process_transaction_ledger(db_client, ledger_payload)
        saved_transactions.append(res.get("transaction_id"))
        
    return {
        "status": "processed", 
        "message": f"Berhasil memproses {len(parsed_transactions)} catatan keuangan.",
        "committed_ledger_ids": saved_transactions
    }
