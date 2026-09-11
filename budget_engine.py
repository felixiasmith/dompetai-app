from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi import APIRouter, HTTPException, Depends
import os

router = APIRouter(prefix="/api/v1/budget", tags=["Budgeting Engine"])

# Koneksi Database Helper
async def get_db_client():
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    return AsyncIOMotorClient(mongo_uri)

@router.get("/health-score/{user_id}")
async def get_budget_health_score(user_id: str, db_client: AsyncIOMotorClient = Depends(get_db_client)):
    db = db_client["dompet_ai_db"]
    
    # 1. Tentukan batas waktu awal dan akhir bulan berjalan (GMT+7 Konteks)
    now = datetime.now(timezone.utc)
    start_of_month = datetime(now.year, now.month, 1, 0, 0, 0, tzinfo=timezone.utc)
    
    # 2. Agregasi total pendapatan (INFLOW) di bulan ini
    inflow_pipeline = [
        {"$match": {
            "user_id": user_id,
            "transaction_type": "INFLOW",
            "timestamp_utc": {"$gte": start_of_month}
        }},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
    ]
    inflow_res = await db.transactions.aggregate(inflow_pipeline).to_list(1)
    total_income = inflow_res[0]["total"] if inflow_res else 0.0

    # Jika belum ada pemasukan dicatat bulan ini, set default profil demo untuk kalkulasi awal
    if total_income == 0:
        total_income = 15000000.0 # Batas asumsi profil demo Tech Professional

    # 3. Agregasi pengeluaran bulanan berdasarkan Kategori 50/30/20
    expense_pipeline = [
        {"$match": {
            "user_id": user_id,
            "transaction_type": "OUTFLOW",
            "timestamp_utc": {"$gte": start_of_month},
            "category": {"$in": ["Needs", "Wants", "Savings"]}
        }},
        {"$group": {"_id": "$category", "total": {"$sum": "$amount"}}}
    ]
    expense_res = await db.transactions.aggregate(expense_pipeline).to_list(3)
    
    # Petakan hasil ke struktur dictionary
    actual = {"Needs": 0.0, "Wants": 0.0, "Savings": 0.0}
    for item in expense_res:
        actual[item["_id"]] = item["total"]

    # 4. Hitung Target Alokasi Ideal Berdasarkan Aturan Klasik 50/30/20
    target = {
        "Needs": total_income * 0.50,
        "Wants": total_income * 0.30,
        "Savings": total_income * 0.20
    }

    # 5. Algoritma Perhitungan Penalti & Skor Kesehatan Finansial
    # Nilai dasar awal dimulai sempurna dari angka 100
    health_score = 100.0 
    deductions = []

    # Penalti A: Jika Kebutuhan Pokok (Needs) melebih batas 50%
    if actual["Needs"] > target["Needs"]:
        excess_needs_pct = ((actual["Needs"] - target["Needs"]) / target["Needs"]) * 100
        penalty = min(excess_needs_pct * 0.5, 30) # Maksimal penalti 30 poin
        health_score -= penalty
        deductions.append(f"Kebutuhan pokok (Needs) melebihi anggaran target sebesar Rp{(actual['Needs'] - target['Needs']):,.0f}.")

    # Penalti B: Jika Gaya Hidup (Wants) melebih batas 30% (Sifatnya sangat krusial)
    if actual["Wants"] > target["Wants"]:
        excess_wants_pct = ((actual["Wants"] - target["Wants"]) / target["Wants"]) * 100
        penalty = min(excess_wants_pct * 0.8, 40) # Maksimal penalti 40 poin karena bocor gaya hidup berbahaya
        health_score -= penalty
        deductions.append(f"Gaya hidup & keinginan (Wants) bocor sebesar Rp{(actual['Wants'] - target['Wants']):,.0f} dari batas aman bulanan.")

    # Penalti C: Jika Tabungan (Savings) kurang dari aturan minimal 20%
    if actual["Savings"] < target["Savings"]:
        deficit_savings_pct = ((target["Savings"] - actual["Savings"]) / target["Savings"]) * 100
        penalty = min(deficit_savings_pct * 0.4, 30) # Maksimal penalti 30 poin
        health_score -= penalty
        deductions.append("Alokasi investasi dan tabungan (Savings) belum memenuhi kuota minimum 20% bulan ini.")

    # Pastikan batas bawah skor tidak minus
    health_score = max(round(health_score), 0)

    # 6. Diagnosis AI Terstruktur Berdasarkan Rentang Skor Akhir
    if health_score >= 85:
        status_label = "EXCELLENT"
        diagnosis = "Kondisi finansial sangat prima. Alokasi dana terdistribusi dengan sangat sehat sesuai kaidah budgeting makro."
    elif health_score >= 70:
        status_label = "GOOD"
        diagnosis = "Keuangan Anda dalam jalur yang benar. Ada sedikit kebocoran minor di pos gaya hidup namun tidak merusak struktur tabungan inti."
    elif health_score >= 50:
        status_label = "WARNING"
        diagnosis = "Waspada. Pengeluaran wajib atau konsumsi jangka pendek mulai menekan porsi tabungan masa depan Anda."
    else:
        status_label = "CRITICAL"
        diagnosis = "Bahaya. Terjadi ketimpangan alokasi yang parah. Anda rentan mengalami defisit bulanan akibat pengeluaran tidak terkendali."

    return {
        "calculated_at": now.isoformat(),
        "total_monthly_income": total_income,
        "breakdown": {
            "needs": {"actual": actual["Needs"], "target": target["Needs"], "percentage_of_income": (actual["Needs"]/total_income)*100},
            "wants": {"actual": actual["Wants"], "target": target["Wants"], "percentage_of_income": (actual["Wants"]/total_income)*100},
            "savings": {"actual": actual["Savings"], "target": target["Savings"], "percentage_of_income": (actual["Savings"]/total_income)*100}
        },
        "budget_health_score": health_score,
        "status": status_label,
        "diagnostics_summary": diagnosis,
        "flags_detected": deductions
    }
