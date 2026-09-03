import os
import requests
from bs4 import BeautifulSoup

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

# Takip edilecek ürün linki ve hedef indirimler
URUN_URL = "https://www.amazon.com.tr/dp/B08N5WRWNW"  # Buraya takip etmek istediğiniz ürün linkini yapıştırabilirsiniz
ESKI_FIYAT = 1000.0  # Referans başlangıç fiyatı (TL)
HEDEF_INDIRIM_YUZDESI = 10  # Minimum yüzde kaç indirimde bildirim gelsin?

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "tr-TR,tr;q=0.9"
}

def telegram_mesaj_gonder(mesaj):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": mesaj, "parse_mode": "HTML"}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"Telegram hatası: {e}")

def kontrol_et():
    try:
        res = requests.get(URUN_URL, headers=HEADERS)
        if res.status_code != 200:
            print(f"Sayfaya erişilemedi, Durum Kodu: {res.status_code}")
            return

        soup = BeautifulSoup(res.content, "html.parser")
        
        baslik_elem = soup.find("span", {"id": "productTitle"})
        urun_adi = baslik_elem.get_text().strip() if baslik_elem else "Ürün"

        fiyat_elem = soup.find("span", {"class": "a-offscreen"})
        if not fiyat_elem:
            print("Fiyat bulunamadı.")
            return

        fiyat_text = fiyat_elem.get_text().replace("TL", "").replace(".", "").replace(",", ".").strip()
        guncel_fiyat = float(fiyat_text)

        if ESKI_FIYAT > guncel_fiyat:
            indirim = ((ESKI_FIYAT - guncel_fiyat) / ESKI_FIYAT) * 100
            if indirim >= HEDEF_INDIRIM_YUZDESI:
                mesaj = (
                    f"🚨 <b>AMAZON İNDİRİMİ!</b>\n\n"
                    f"📦 <b>Ürün:</b> {urun_adi}\n"
                    f"📉 <b>İndirim:</b> %{indirim:.1f}\n"
                    f"💰 <b>Fiyat:</b> {ESKI_FIYAT} TL ➔ {guncel_fiyat} TL\n\n"
                    f"🔗 <a href='{URUN_URL}'>Ürüne Git</a>"
                )
                telegram_mesaj_gonder(mesaj)
                print("İndirim bildirimi gönderildi!")
            else:
                print(f"İndirim yetersiz (%{indirim:.1f}). Güncel Fiyat: {guncel_fiyat} TL")
        else:
            print(f"İndirim yok. Güncel Fiyat: {guncel_fiyat} TL")

    except Exception as e:
        print("Hata oluştu:", e)

if __name__ == "__main__":
    kontrol_et()
