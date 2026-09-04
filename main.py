import os
import time
import random
import re
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
PROXY_PASS = "LJdsximctNx3"

KATEGORI_LINKLERI = [
    # 1. Bilgisayar & Bileşenleri (Prime Gönderimli)
    "https://www.amazon.com.tr/s?rh=n%3A13709879031%2Cp_n_fulfilled_by_amazon%3A21345978031",
    # 2. Elektronik Genel
    "https://www.amazon.com.tr/s?i=electronics&rh=p_n_fulfilled_by_amazon%3A21345978031",
    # 3. Cep Telefonu ve Aksesuarları
    "https://www.amazon.com.tr/s?i=telephones&rh=p_n_fulfilled_by_amazon%3A21345978031"
]

MAX_PAGES_PER_CATEGORY = 400
MIN_DISCOUNT_PERCENT = 30.0
HAFIZA_DOSYASI = "bildirilenler.txt"

def daha_once_bildirildi_mi(asin):
    if not os.path.exists(HAFIZA_DOSYASI):
        return False
    with open(HAFIZA_DOSYASI, "r", encoding="utf-8") as f:
        kayitlar = f.read().splitlines()
    return asin in kayitlar

def hafizaya_ekle(asin):
    with open(HAFIZA_DOSYASI, "a", encoding="utf-8") as f:
        f.write(f"{asin}\n")

def telegram_mesaj_gonder(mesaj):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("[UYARI] TELEGRAM_TOKEN veya CHAT_ID tanımlı değil!")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": mesaj, "parse_mode": "HTML"}
    try:
        requests.post(url, data=payload, proxies={"http": None, "https": None}, timeout=10)
    except Exception as e:
        print(f"Telegram hatası: {e}")

def metinden_fiyat_ cikar(fiyat_str):
    """
    Amazon'un "1.299,00 TL" veya "1.299 TL" gibi fiyat metinlerini güvenli şekilde float'a çevirir.
    """
    if not fiyat_str:
        return None
    # Sadece rakam, nokta ve virgülü tut
    temiz = re.sub(r'[^\d.,]', '', fiyat_str)
    if not temiz:
        return None
    
    # "1.299,50" -> binlik noktayı kaldır, virgülü noktaya çevir -> "1299.50"
    if "," in temiz:
        temiz = temiz.replace(".", "").replace(",", ".")
    else:
        # Eğer sadece nokta varsa ve son 3 haneden önceyse binlik ayırıcıdır (örn: 1.299)
        if temiz.count(".") == 1 and len(temiz.split(".")[1]) != 2:
            temiz = temiz.replace(".", "")
            
    try:
        return float(temiz)
    except ValueError:
        return None

def asin_ile_temiz_link_ve_id_al(kart):
    h2_link = kart.select_one("h2 a")
    raw_href = h2_link.get("href") if h2_link else None

    if not raw_href:
        for a_tag in kart.find_all("a", href=True):
            href = a_tag["href"]
            if "/dp/" in href or "/gp/product/" in href or "sspa/click" in href:
                raw_href = href
                break

    if not raw_href:
        return None, None

    if "sspa/click" in raw_href or "url=" in raw_href:
        url_match = re.search(r'url=([^&]+)', raw_href)
        if url_match:
            raw_href = unquote(url_match.group(1))

    asin_match = re.search(r'/(?:dp|gp/product)/([A-Z0-9]{10})', raw_href)
    if asin_match:
        asin = asin_match.group(1)
        return f"https://www.amazon.com.tr/dp/{asin}", asin

    return None, None

def tum_sayfalari_tara():
    proxy_config = {"server": f"http://{PROXY_IP}:{PROXY_PORT}"}
    if PROXY_USER and PROXY_PASS:
        proxy_config["username"] = PROXY_USER
        proxy_config["password"] = PROXY_PASS

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            proxy=proxy_config,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-setuid-sandbox"]
        )
        
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            locale="tr-TR",
            viewport={"width": 1366, "height": 768}
        )
        
        page = context.new_page()
        page.route("**/*.{png,jpg,jpeg,svg,webp,gif,woff,woff2,ttf}", lambda route: route.abort())
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        toplam_yeni_bildirim = 0

        for kat_idx, base_url in enumerate(KATEGORI_LINKLERI, start=1):
            print(f"\n==========================================")
            print(f"Kategori {kat_idx}/{len(KATEGORI_LINKLERI)} Taranıyor...")
            print(f"==========================================")
            
            current_url = base_url
            page_number = 1

            try:
                while current_url and page_number <= MAX_PAGES_PER_CATEGORY:
                    print(f"[Kat {kat_idx}] Sayfa {page_number}/{MAX_PAGES_PER_CATEGORY} Taranıyor...")
                    
                    try:
                        page.goto(current_url, wait_until="commit", timeout=30000)
                        page.wait_for_selector("div[data-component-type='s-search-result']", timeout=15000)
                    except Exception as goto_err:
                        print(f"Sayfa yüklenme uyarısı: {goto_err}")

                    time.sleep(random.uniform(1.0, 2.0))
                    
                    html_content = page.content()
                    soup = BeautifulSoup(html_content, "html.parser")
                    
                    urun_kartlari = soup.find_all("div", {"data-component-type": "s-search-result"})
                    
                    if not urun_kartlari:
                        print(f"Sayfa {page_number} üzerinde ürün bulunamadı veya son sayfaya ulaşıldı.")
                        break

                    for kart in urun_kartlari:
                        urun_linki, asin = asin_ile_temiz_link_ve_id_al(kart)
                        
                        if not urun_linki or not asin:
                            continue

                        if daha_once_bildirildi_mi(asin):
                            continue

                        baslik_elem = kart.find("h2")
                        urun_adi = baslik_elem.get_text().strip() if baslik_elem else "Amazon Ürünü"

                        # 1. Güncel Fiyat Tespiti (Önce a-price içindeki tam offscreen metni dene)
                        guncel_fiyat = None
                        fiyat_container = kart.select_one("span.a-price:not([data-a-strike='true'])")
                        if fiyat_container:
                            offscreen = fiyat_container.select_one("span.a-offscreen")
                            if offscreen:
                                guncel_fiyat = metinden_fiyat_ cikar(offscreen.get_text())

                        if not guncel_fiyat:
                            whole_elem = kart.find("span", {"class": "a-price-whole"})
                            fraction_elem = kart.find("span", {"class": "a-price-fraction"})
                            if whole_elem:
                                w_text = whole_elem.get_text()
                                f_text = fraction_elem.get_text() if fraction_elem else "00"
                                guncel_fiyat = metinden_fiyat_ cikar(f"{w_text},{f_text}")

                        if not guncel_fiyat:
                            continue

                        # 2. Eski Fiyat (Üstü Çizili Fiyat) Tespiti - Farklı CSS Alternatifleri
                        eski_fiyat = None
                        
                        # Alternatif 1: span.a-text-price span.a-offscreen
                        eski_elem = kart.select_one("span.a-text-price span.a-offscreen")
                        if eski_elem:
                            eski_fiyat = metinden_fiyat_ cikar(eski_elem.get_text())

                        # Alternatif 2: data-a-strike='true' olan fiyatlar
                        if not eski_fiyat:
                            eski_strike = kart.select_one("span.a-price[data-a-strike='true'] span.a-offscreen")
                            if eski_strike:
                                eski_fiyat = metinden_fiyat_ cikar(eski_strike.get_text())

                        # Alternatif 3: a-basis-price / üstü çizili ikincil metinler
                        if not eski_fiyat:
                            eski_basis = kart.select_one("span.a-price.a-text-price")
                            if eski_basis:
                                eski_fiyat = metinden_fiyat_ cikar(eski_basis.get_text())

                        # 3. İndirim Hesaplama
                        if eski_fiyat and eski_fiyat > guncel_fiyat:
                            indirim_orani = ((eski_fiyat - guncel_fiyat) / eski_fiyat) * 100
                            
                            if indirim_orani >= MIN_DISCOUNT_PERCENT:
                                toplam_yeni_bildirim += 1
                                mesaj = (
                                    f"🔥 <b>%{int(indirim_orani)} AMAZON İNDİRİMİ!</b> 🔥\n\n"
                                    f"📦 <b>Ürün:</b> {urun_adi[:100]}...\n"
                                    f"📉 <b>İndirim Oranı:</b> %{indirim_orani:.1f}\n"
                                    f"💰 <b>Fiyat:</b> {eski_fiyat:.2f} TL ➔ {guncel_fiyat:.2f} TL\n\n"
                                    f"🔗 <a href='{urun_linki}'>Ürüne Git</a>"
                                )
                                telegram_mesaj_gonder(mesaj)
                                hafizaya_ekle(asin)
                                print(f"[BİLDİRİLDİ] %{indirim_orani:.1f} İndirim: {urun_adi[:30]}")

                    next_button = soup.find("a", {"class": "s-pagination-next"})
                    if next_button and "href" in next_button.attrs:
                        current_url = "https://www.amazon.com.tr" + next_button["href"]
                        page_number += 1
                    else:
                        print("Bu kategorideki tüm sayfalar tamamlandı.")
                        break

            except Exception as e:
                print(f"Kategori {kat_idx} taranırken hata:", e)

        print(f"\nBütün Kategorilerin Taraması Bitti! Toplam {toplam_yeni_bildirim} yeni indirim bildirildi.")
        browser.close()

if __name__ == "__main__":
    tum_sayfalari_tara()
