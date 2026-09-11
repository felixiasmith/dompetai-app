from fastapi import HTTPException, status
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

# 1. Skema Data Pydantic untuk Validasi Input dari AI
class TransactionIn(BaseModel):
    user_id: str
    description: str
    amount: float = Field(gt=0, description="Nominal harus lebih besar dari 0")
    transaction_type: str = Field(description="INFLOW, OUTFLOW, TRANSFER, DEBT, RECEIVABLE")
    category: str = Field(description="Needs, Wants, Savings, Allocation")
    source_wallet_id: str
    destination_wallet_id: Optional[str] = None
    raw_nlp_text: Optional[str] = None

# 2. Fungsi Utama Pembaruan Saldo Otomatis (Ledger Engine)
async def process_transaction_ledger(client: AsyncIOMotorClient, tx_data: TransactionIn):
    db = client["dompet_ai_db"]
    
    # Menjalankan ACID Transaction di MongoDB untuk mencegah data korup
    async with await client.start_session() as session:
        async with session.start_transaction():
            
            # AMBIL DATA WALLET ASAL
            source_wallet = await db.wallets.find_one(
                {"_id": tx_data.source_wallet_id, "user_id": tx_data.user_id}, 
                session=session
            )
            if not source_wallet:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, 
                    detail=f"Dompet asal '{tx_data.source_wallet_id}' tidak ditemukan."
                )

            # LOGIKA MUTASI SALDO BERDASARKAN JENIS TRANSAKSI
            if tx_data.transaction_type == "OUTFLOW" or tx_data.transaction_type == "RECEIVABLE":
                # Uang Keluar / Menalangi teman: Kurangi Saldo Wallet Asal
                new_balance = source_wallet["balance"] - tx_data.amount
                await db.wallets.update_one(
                    {"_id": tx_data.source_wallet_id},
                    {"$set": {"balance": new_balance, "updated_at": datetime.utcnow()}},
                    session=session
                )

            elif tx_data.transaction_type == "INFLOW" or tx_data.transaction_type == "DEBT":
                # Uang Masuk / Meminjam uang: Tambah Saldo Wallet Asal
                new_balance = source_wallet["balance"] + tx_data.amount
                await db.wallets.update_one(
                    {"_id": tx_data.source_wallet_id},
                    {"$set": {"balance": new_balance, "updated_at": datetime.utcnow()}},
                    session=session
                )

            elif tx_data.transaction_type == "TRANSFER":
                # Transfer Antar Rekening: Pastikan wallet tujuan diisi
                if not tx_data.destination_wallet_id:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="destination_wallet_id wajib diisi untuk tipe transaksi TRANSFER."
                    )
                
                dest_wallet = await db.wallets.find_one(
                    {"_id": tx_data.destination_wallet_id, "user_id": tx_data.user_id}, 
                    session=session
                )
                if not dest_wallet:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Dompet tujuan '{tx_data.destination_wallet_id}' tidak ditemukan."
                    )

                # Eksekusi Mutasi Transfer Pindah Dana
                await db.wallets.update_one(
                    {"_id": tx_data.source_wallet_id},
                    {"$set": {"balance": source_wallet["balance"] - tx_data.amount, "updated_at": datetime.utcnow()}},
                    session=session
                )
                await db.wallets.update_one(
                    {"_id": tx_data.destination_wallet_id},
                    {"$set": {"balance": dest_wallet["balance"] + tx_data.amount, "updated_at": datetime.utcnow()}},
                    session=session
                )

            # SIMPAN LOG TRANSAKSI KE KOLEKSI TRANSACTIONS
            tx_document = {
                "user_id": tx_data.user_id,
                "timestamp_utc": datetime.utcnow(),
                "user_timezone": "Asia/Jakarta",
                "description": tx_data.description,
                "amount": tx_data.amount,
                "transaction_type": tx_data.transaction_type,
                "category": tx_data.category,
                "source_wallet_id": tx_data.source_wallet_id,
                "destination_wallet_id": tx_data.destination_wallet_id,
                "raw_nlp_text": tx_data.raw_nlp_text
            }
            
            insert_result = await db.transactions.insert_one(tx_document, session=session)
            
            # JIKA TRANSAKSI ADALAH UTANG/PIUTANG, BUAT CATATAN DI TABEL IOU
            if tx_data.transaction_type in ["DEBT", "RECEIVABLE"]:
                iou_document = {
                    "user_id": tx_data.user_id,
                    "type": tx_data.transaction_type,
                    "person_name": tx_data.description.split(" ke ")[-1] if " ke " in tx_data.description else "Pihak Ketiga",
                    "amount": tx_data.amount,
                    "remaining_amount": tx_data.amount,
                    "status": "UNPAID",
                    "description": tx_data.description,
                    "created_at": datetime.utcnow()
                }
                await db.debts_receivables.insert_one(iou_document, session=session)

            return {"status": "success", "transaction_id": str(insert_result.inserted_id)}
