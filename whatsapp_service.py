import os
import httpx
from fastapi import BackgroundTasks
from logging import getlogger

logger = getlogger("whatsapp_service")

# 1. Fungsi Inti Mengirim Pesan WhatsApp (Meta Cloud API Resmi)
async def send_whatsapp_message(to_phone: str, text_body: str):
    whatsapp_token = os.getenv("WHATSAPP_SYSTEM_TOKEN")
    phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    
    if not whatsapp_token or not phone_number_id:
        logger.warning("Kredensial WhatsApp API belum lengkap. Notifikasi dilewati.")
        return False

    url = f"https://facebook.com{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {whatsapp_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "text",
        "text": {"body": text_body}
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, headers=headers, timeout=10.0)
            if response.status_code == 200:
                logger.info(f"Notifikasi WhatsApp berhasil dikirim ke {to_phone}")
                return True
            else:
                logger.error(f"Gagal kirim WA: {response.text}")
                return False
        except Exception as e:
            logger.error(f"Eror koneksi WhatsApp API: {str(e)}")
            return False

# 2. Trigger Otomatis: Peringatan Anggaran Bocor (Smart Budget Alert)
def trigger_budget_limit_alert(background_tasks: BackgroundTasks, to_phone: str, category: str, actual: float, limit: float):
    # Hitung persentase pemakaian
    usage_pct = (actual / limit) * 100
    
    if usage_pct >= 90.0:
        message = (
            f"⚠️ *PERINGATAN BUDGET DompetAI*\n\n"
            f"Halo Rian, pengeluaran untuk kategori *{category}* Anda telah mencapai *{usage_pct:.1f}%* "
            f"dari batas aman bulanan Anda.\n\n"
            f"• Realisasi: Rp {actual:,.0f}\n"
            f"• Batas Maksimal: Rp {limit:,.0f}\n\n"
            f"AI merekomendasikan untuk menunda pengeluaran non-primer di kategori ini hingga bulan depan."
        )
        # Jalankan di background task agar tidak menghambat response time API Ledger Utama
        background_tasks.add_task(send_whatsapp_message, to_phone, message)
