import os
import time
import random
import re
import sqlite3
from urllib.parse import unquote
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import requests

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

# PROXY BİLGİLERİNİZ
PROXY_IP = "82.41.113.137"
PROXY_PORT = "2534"
PROXY_USER = "LJdsximctNx3"
PROXY_PASS = "3Eyb9BqYR4Kc"

DEALS_URLS = [
    "https://www.amazon.com.tr/deals?ref_=nav_cs_gb",
    "https://www.amazon.com.tr/gp/goldbox",
    "https://www.amazon.com.tr/s?i=electronics&rh=p_n_deal_type%3A26901101031"
]

# TEST İÇİN %5 YAPILDI (Daha sonra %25 veya %30 yapabilirsiniz)
MIN_DISCOUNT_PERCENT = 5.0  
DB_FILE = "firsat_hafizasi.db"

def db_kur():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS urunler (
            asin TEXT PRIMARY KEY,
            fiyat REAL,
            tarih TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def daha_once_bildirildi_mi(asin):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT asin FROM urunler WHERE asin = ?", (asin,))
    row = cursor.fetchone()
    conn.close()
    return row is not None

def db_ekle(asin, fiyat):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO urunler (asin, fiyat) VALUES (?, ?)", (asin, fiyat))
    conn.commit()
    conn.close()

def telegram_mesaj_gonder(mesaj):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("[UYARI] TELEGRAM_TOKEN veya CHAT_ID eksik!")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": mesaj, "parse_mode": "HTML"}
    try:
        requests.post(url, data=payload, proxies={"http": None, "https": None}, timeout=10)
    except Exception as e:
        print(f"Telegram Gönderim Hatası: {e}")

def metinden_fiyat_cikar(fiyat_str):
    if not fiyat_str:
        return None
    temiz = re.sub(r'[^\d.,]', '', fiyat_str)
    if not temiz:
        return None
    if "," in temiz:
        temiz = temiz.replace(".", "").replace(",", ".")
    else:
        if temiz.count(".") == 1 and len(temiz.split(".")[1]) != 2:
            temiz = temiz.replace(".", "")
    try:
        return float(temiz)
    except ValueError:
        return None

def anlik_firsat_taramasi():
    db_kur()
    
    proxy_config = {"server": f"http://{PROXY_IP}:{PROXY_PORT}"}
    if PROXY_USER and PROXY_PASS:
        proxy_config["username"] = PROXY_USER
        proxy_config["password"] = PROXY_PASS

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            proxy=proxy_config,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            locale="tr-TR",
            viewport={"width": 1440, "height": 900}
        )
        
        page = context.new_page()
        page.route("**/*.{png,jpg,jpeg,svg,webp,gif,woff,woff2,ttf}", lambda route: route.abort())

        print("🚀 Anlık Fırsat Tarayıcısı Başlatıldı...")

        for target_url in DEALS_URLS:
            print(f"\n[SAYFA TARANIYOR] -> {target_url}")
            try:
                page.goto(target_url, wait_until="commit", timeout=25000)
                page.wait_for_timeout(3000)

                soup = BeautifulSoup(page.content(), "html.parser")
                kartlar = soup.select("div[data-component-type='s-search-result'], div[data-testid='grid-deals-container'] div[data-deal-id]")
                
                if not kartlar:
                    kartlar = soup.find_all("div", {"class": re.compile(r'DealCard|GridItem')})

                print(f"Tespit Edilen Potansiyel Fırsat Kartı Sayısı: {len(kartlar)}")

                for kart in kartlar:
                    asin = kart.get("data-asin")
                    if not asin:
                        link_elem = kart.find("a", href=True)
                        if link_elem:
                            match = re.search(r'/(?:dp|gp/product)/([A-Z0-9]{10})', link_elem['href'])
                            if match:
                                asin = match.group(1)

                    if not asin:
                        continue

                    if daha_once_bildirildi_mi(asin):
                        continue

                    baslik_elem = kart.find("h2") or kart.select_one("span.a-truncate-full, .a-size-base-plus")
                    urun_adi = baslik_elem.get_text().strip() if baslik_elem else "Amazon Fırsat Ürünü"

                    guncel_fiyat = None
                    eski_fiyat = None

                    guncel_elem = kart.select_one("span.a-price:not([data-a-strike='true']) span.a-offscreen, .a-price-whole")
                    if guncel_elem:
                        guncel_fiyat = metinden_fiyat_cikar(guncel_elem.get_text())

                    eski_elem = kart.select_one("span.a-price[data-a-strike='true'] span.a-offscreen, span.a-text-price span.a-offscreen")
                    if eski_elem:
                        eski_fiyat = metinden_fiyat_cikar(eski_elem.get_text())

                    rozet_elem = kart.select_one("span.a-badge-text, div[class*='badge']")
                    rozet_orani = None
                    if rozet_elem:
                        rozet_match = re.search(r'%(\d+)', rozet_elem.get_text())
                        if rozet_match:
                            rozet_orani = float(rozet_match.group(1))

                    indirim_orani = 0.0
                    if eski_fiyat and guncel_fiyat and eski_fiyat > guncel_fiyat:
                        indirim_orani = ((eski_fiyat - guncel_fiyat) / eski_fiyat) * 100
                    elif rozet_orani:
                        indirim_orani = rozet_orani

                    # --- DETAYLI YAZDIRMA (KARTLARI GÖRMEK İÇİN) ---
                    print(f"-> ASIN: {asin} | Güncel: {guncel_fiyat} TL | Eski: {eski_fiyat} TL | İndirim: %{indirim_orani:.1f}")

                    if indirim_orani >= MIN_DISCOUNT_PERCENT and guncel_fiyat:
                        urun_linki = f"https://www.amazon.com.tr/dp/{asin}"
                        eski_fiyat_str = f"{eski_fiyat:.2f} TL" if eski_fiyat else "Belirtilmemiş"
                        
                        mesaj = (
                            f"⚡ <b>ANLIK AMAZON FIRSATI!</b> ⚡\n\n"
                            f"📦 <b>Ürün:</b> {urun_adi[:90]}...\n"
                            f"📉 <b>İndirim:</b> %{int(indirim_orani)}\n"
                            f"💰 <b>Fiyat:</b> {eski_fiyat_str} ➔ <b>{guncel_fiyat:.2f} TL</b>\n\n"
                            f"🔗 <a href='{urun_linki}'>Ürünü İncele / Satın Al</a>"
                        )
                        
                        telegram_mesaj_gonder(mesaj)
                        db_ekle(asin, guncel_fiyat)
                        print(f"🔥 [FIRSAT BİLDİRİLDİ] %{int(indirim_orani)} - {urun_adi[:30]}")

            except Exception as e:
                print(f"Hata oluştu ({target_url}): {e}")

        browser.close()

if __name__ == "__main__":
    anlik_firsat_taramasi()
