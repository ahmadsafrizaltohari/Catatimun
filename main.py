import os
import json
import requests
from datetime import datetime, date
from fastapi import FastAPI, Request
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from supabase import create_client, Client

app = FastAPI()

@app.get("/")
def home():
    return {"message": "Bot Keuangan WA Berhasil Aktif!"}

# 🔑 CONFIG
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SUPABASE_URL = "https://yaamohkupbysxjvpyhby.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlhYW1vaGt1cGJ5c3hqdnB5aGJ5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODUyMzY3MDUsImV4cCI6MjEwMDgxMjcwNX0.UeNlyr6QQDpbmQ2wwGnb3FhjuFb1bNgq0S48SUozsX8"
FONNTE_TOKEN = os.getenv("FONNTE_TOKEN")

# 🛡️ DAFTAR NOMOR WA YANG DIIZINKAN (Gunakan format 62...)
ALLOWED_NUMBERS = [
    "62882000805545",
]

gemini_client = genai.Client(api_key=GEMINI_API_KEY)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

NAMA_BULAN = [
    "", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember"
]

# ==================== PYDANTIC MODELS ====================

class TransaksiItem(BaseModel):
    amount: float = Field(description="Nominal uang dalam angka saja")
    type: str = Field(description="expense atau income")
    category: str = Field(description="Kategori transaksi")
    description: str = Field(description="Penjelasan singkat")

class TransaksiList(BaseModel):
    transaksi: list[TransaksiItem]

def kirim_balasan_wa(target: str, teks: str):
    url = "https://api.fonnte.com/send"
    headers = {"Authorization": FONNTE_TOKEN}
    payload = {"target": target, "message": teks}
    try:
        requests.post(url, headers=headers, data=payload)
    except Exception as e:
        print("❌ Gagal kirim WA:", e)

# ==================== FUNGSIONALITAS COMMAND ====================

def handle_laporan_hari_ini(user_number: str) -> str:
    """Rekap transaksi hari ini khusus untuk user tertentu"""
    today_str = date.today().isoformat()
    
    res = supabase.table("transactions") \
        .select("*") \
        .eq("user", user_number) \
        .gte("created_at", f"{today_str}T00:00:00") \
        .lte("created_at", f"{today_str}T23:59:59") \
        .execute()
    
    data = res.data
    if not data:
        return f"📊 *LAPORAN HARI INI ({today_str})*\n\nBelum ada transaksi yang dicatat hari ini."
    
    total_expense = 0
    total_income = 0
    rincian = ""

    for item in data:
        nominal = int(item["amount"])
        fmt_nominal = f"{nominal:,}".replace(",", ".")
        
        if item["type"] == "expense":
            total_expense += nominal
            rincian += f"🔴 {item['description']}: Rp{fmt_nominal} ({item['category']})\n"
        else:
            total_income += nominal
            rincian += f"🟢 {item['description']}: Rp{fmt_nominal} ({item['category']})\n"

    tot_exp_fmt = f"{total_expense:,}".replace(",", ".")
    tot_inc_fmt = f"{total_income:,}".replace(",", ".")

    return (
        f"📊 *LAPORAN TRANSAKSI HARI INI*\n"
        f"📅 Tanggal: {today_str}\n\n"
        f"{rincian}\n"
        f"----------------------------------------\n"
        f"💸 Total Pengeluaran: *Rp{tot_exp_fmt}*\n"
        f"💰 Total Pemasukan: *Rp{tot_inc_fmt}*"
    )

def handle_laporan_bulanan(user_number: str) -> str:
    """Rekap transaksi bulan ini dikelompokkan per kategori khusus user tertentu"""
    today = date.today()
    first_day = date(today.year, today.month, 1).strftime("%Y-%m-%dT00:00:00")
    
    if today.month == 12:
        next_month_first_day = date(today.year + 1, 1, 1).strftime("%Y-%m-%dT00:00:00")
    else:
        next_month_first_day = date(today.year, today.month + 1, 1).strftime("%Y-%m-%dT00:00:00")

    res = supabase.table("transactions") \
        .select("*") \
        .eq("user", user_number) \
        .gte("created_at", first_day) \
        .lt("created_at", next_month_first_day) \
        .execute()

    data = res.data
    nama_bulan = NAMA_BULAN[today.month]

    if not data:
        return f"📅 *LAPORAN BULANAN ({nama_bulan} {today.year})*\n\nBelum ada transaksi di bulan ini."

    categories_expense = {}
    categories_income = {}
    total_expense = 0
    total_income = 0

    for item in data:
        nominal = int(item["amount"])
        cat = item.get("category", "Lain-lain")
        
        if item["type"] == "expense":
            total_expense += nominal
            categories_expense[cat] = categories_expense.get(cat, 0) + nominal
        else:
            total_income += nominal
            categories_income[cat] = categories_income.get(cat, 0) + nominal

    # Format text
    text_expense = ""
    for cat, amt in categories_expense.items():
        text_expense += f"• {cat}: Rp{amt:,}\n".replace(",", ".")

    text_income = ""
    for cat, amt in categories_income.items():
        text_income += f"• {cat}: Rp{amt:,}\n".replace(",", ".")

    tot_exp_fmt = f"{total_expense:,}".replace(",", ".")
    tot_inc_fmt = f"{total_income:,}".replace(",", ".")
    saldo_fmt = f"{(total_income - total_expense):,}".replace(",", ".")

    msg = f"📅 *REKAP BULANAN ({nama_bulan.upper()} {today.year})*\n\n"
    if text_expense:
        msg += f"🔴 *Pengeluaran per Kategori:*\n{text_expense}\n"
    if text_income:
        msg += f"🟢 *Pemasukan per Kategori:*\n{text_income}\n"

    msg += (
        f"----------------------------------------\n"
        f"💸 Total Pengeluaran: *Rp{tot_exp_fmt}*\n"
        f"💰 Total Pemasukan: *Rp{tot_inc_fmt}*\n"
        f"⚖️ Saldo Bulan Ini: *Rp{saldo_fmt}*"
    )
    return msg

def handle_hapus_semua_transaksi(user_number: str) -> str:
    """Menghapus seluruh record transaksi khusus milik user ini saja"""
    try:
        supabase.table("transactions").delete().eq("user", user_number).execute()
        return "🗑️ *SEMUA TRANSAKSI KAMU BERHASIL DIHAPUS*\n\nDatabase transaksi kamu sekarang sudah bersih kembali."
    except Exception as e:
        print("❌ Error hapus data:", e)
        return f"❌ Gagal menghapus transaksi dari database: {str(e)}"

def handle_menu() -> str:
    """Menampilkan daftar perintah"""
    return (
        "🤖 *DAFTAR COMMAND BOT KEUNGAN*\n\n"
        "• `#laporanhariini` atau `#laporan` : Rekap transaksi hari ini\n"
        "• `#laporanbulanan` atau `#bulan` : Rekap per kategori bulan ini\n"
        "• `#hapustransaksi` : Hapus seluruh data transaksi kamu\n"
        "• `#menu` atau `#help` : Tampilkan menu ini\n\n"
        "💡 *Tips:* Kirim pesan biasa tanpa `#` untuk mencatat transaksi via AI."
    )

# ==================== MAIN WEBHOOK ====================

@app.post("/webhook")
async def webhook_receiver(request: Request):
    try:
        data = await request.json()
    except Exception:
        form_data = await request.form()
        data = dict(form_data)
        
    pesan_text = (data.get("message") or data.get("text") or "").strip()
    sender_number = data.get("sender") or data.get("from") or ""
    
    if not pesan_text or not sender_number:
        return {"status": "ignored"}

    # 🛑 1. CEK WHITELIST: Abaikan jika nomor pengirim tidak terdaftar
    if sender_number not in ALLOWED_NUMBERS:
        print(f"⚠️ Pesan dari {sender_number} diabaikan (Tidak terdaftar).")
        return {"status": "ignored", "reason": "Unauthorized number"}

    # 2. JIKA PESAN BERAWALAN COMMAND '#'
    if pesan_text.startswith("#"):
        command = pesan_text.split()[0].lower()
        
        if command in ["#laporanhariini", "#laporan", "#hariini"]:
            balasan = handle_laporan_hari_ini(sender_number)
        elif command in ["#laporanbulanan", "#bulan"]:
            balasan = handle_laporan_bulanan(sender_number)
        elif command in ["#hapustransaksi", "#hapussemua"]:
            balasan = handle_hapus_semua_transaksi(sender_number)
        elif command in ["#menu", "#help"]:
            balasan = handle_menu()
        else:
            balasan = f"⚠️ Command `{command}` tidak ditemukan. Ketik `#menu` untuk melihat daftar perintah."
            
        kirim_balasan_wa(sender_number, balasan)

    # 3. JIKA PESAN BIASA (PENCATATAN TRANSAKSI VIA GEMINI 1.5 FLASH)
    else:
        try:
            if not GEMINI_API_KEY:
                raise Exception("GEMINI_API_KEY belum terpasang di Environment Variables!")

            response = gemini_client.models.generate_content(
    model="gemini-2.0-flash",
    contents=pesan_text,
    config=types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=TransaksiList,
        system_instruction="Kamu adalah asisten keuangan. Ekstrak pesan menjadi data transaksi."
                )
            )
            
            raw_text = response.text.strip()
            
            # Pembersihan markdown jika ada
            if raw_text.startswith("```"):
                lines = raw_text.split("\n")
                raw_text = "\n".join(lines[1:-1]).strip()

            parsed_data = json.loads(raw_text)
            
            if isinstance(parsed_data, list):
                daftar_transaksi = parsed_data
            elif isinstance(parsed_data, dict):
                daftar_transaksi = parsed_data.get("transaksi", [])
            else:
                daftar_transaksi = []
            
            if not daftar_transaksi:
                kirim_balasan_wa(sender_number, "⚠️ Pesan tidak terdeteksi sebagai transaksi keuangan.")
                return {"status": "success"}

            teks_balasan = "✅ *Transaksi Berhasil Dicatat!*\n\n"
            
            for item in daftar_transaksi:
                amount = item.get("amount") if isinstance(item, dict) else item.amount
                typ = item.get("type") if isinstance(item, dict) else item.type
                category = item.get("category") if isinstance(item, dict) else item.category
                description = item.get("description") if isinstance(item, dict) else item.description

                supabase.table("transactions").insert({
                    "user": sender_number,
                    "amount": amount,
                    "type": typ,
                    "category": category,
                    "description": description
                }).execute()
                
                nominal_fmt = f"{int(amount):,}".replace(",", ".")
                teks_balasan += f"• *{description}*: Rp{nominal_fmt} ({category})\n"
            
            kirim_balasan_wa(sender_number, teks_balasan)
                
        except Exception as e:
            print("❌ Error Gemini/Supabase:", e)
            kirim_balasan_wa(sender_number, f"❌ Error detail: {str(e)}")
            
    return {"status": "success"}