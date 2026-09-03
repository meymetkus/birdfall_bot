import os
import time
import random
import re
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import requests

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

# PROXY BİLGİLERİNİZ
PROXY_IP = "82.41.113.137"       # Proxy IP adresiniz
PROXY_PORT = "2534"            # Proxy portunuz
PROXY_USER = "LJdsximctNx3" # Kullanıcı adı
PROXY_PASS = "3Eyb9BqYR4Kc"          # Şifre

# Taranacak Başlangıç Kategorisi Linki
BASE_URL = "https://www.amazon.com.tr/s?rh=n%3A13709879031%2Cp_n_fulfilled_by_amazon%3A21345978031&dc&qid=1788469863&rnid=21345970031&ref=sr_nr_p_n_fulfilled_by_amazon_0"

MAX_PAGES = 400
MIN_DISCOUNT_PERCENT = 30.0

def telegram_mesaj_gonder(mesaj):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": mesaj, "parse_mode": "HTML"}
    try:
        requests.post(url, data=payload, proxies={"http": None, "https": None}, timeout=10)
    except Exception as e:
        print(f"Telegram hatası: {e}")

def urun_linki_temizle(href_str):
    if not href_str:
        return None
    # ASIN (Amazon ürün kodu B0... ile başlar) kodunu yakala
    asin_match = re.search(r'/(?:dp|gp/product)/([A-Z0-9]{10})', href_str)
    if asin_match:
        return f"https://www.amazon.com.tr/dp/{asin_match.group(1)}"
    
    # ASIN bulunamazsa tam URL yap
    if href_str.startswith("http"):
        return href_str.split("?")[0]
    elif href_str.startswith("/"):
        return "https://www.amazon.com.tr" + href_str.split("?")[0]
    
    return None

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

        current_url = BASE_URL
        page_number = 1
        toplam_tespit_edilen_urun = 0
        bulunan_indirim_sayisi = 0

        try:
            while current_url and page_number <= MAX_PAGES:
                print(f"--- Sayfa {page_number}/{MAX_PAGES} Taranıyor ---")
                
                response = page.goto(current_url, wait_until="domcontentloaded", timeout=60000)
                time.sleep(random.uniform(1.0, 2.0))
                
                html_content = page.content()
                soup = BeautifulSoup(html_content, "html.parser")
                
                urun_kartlari = soup.find_all("div", {"data-component-type": "s-search-result"})
                
                if not urun_kartlari:
                    print(f"Sayfa {page_number} üzerinde ürün bulunamadı veya son sayfaya ulaşıldı.")
                    break

                toplam_tespit_edilen_urun += len(urun_kartlari)

                for kart in urun_kartlari:
                    # Doğrudan başlık içindeki <a> etiketini veya ana ürün bağlantısını arıyoruz
                    link_elem = kart.find("a", {"class": "a-link-normal s-no-outline"}) or \
                                kart.find("a", {"class": "a-link-normal s-line-clamp-2"}) or \
                                kart.select_one("h2 a")
                    
                    if not link_elem or "href" not in link_elem.attrs:
                        continue
                        
                    raw_href = link_elem["href"]
                    urun_linki = urun_linki_temizle(raw_href)
                    
                    # Eğer geçerli ürün linki çıkarılamadıysa pas geç
                    if not urun_linki:
                        continue

                    baslik_elem = kart.find("h2")
                    urun_adi = baslik_elem.get_text().strip() if baslik_elem else "Amazon Ürünü"

                    fiyat_elem = kart.find("span", {"class": "a-price-whole"})
                    if not fiyat_elem:
                        continue
                    
                    fiyat_text = fiyat_elem.get_text().replace(".", "").replace(",", ".").strip()
                    
                    eski_fiyat_elem = kart.find("span", {"class": "a-text-price"})
                    if eski_fiyat_elem:
                        eski_fiyat_text = eski_fiyat_elem.find("span", {"class": "a-offscreen"})
                        if eski_fiyat_text:
                            eski_str = eski_fiyat_text.get_text().replace("TL", "").replace(".", "").replace(",", ".").strip()
                            try:
                                guncel_fiyat = float(fiyat_text)
                                eski_fiyat = float(eski_str)

                                if eski_fiyat > guncel_fiyat:
                                    indirim_orani = ((eski_fiyat - guncel_fiyat) / eski_fiyat) * 100
                                    
                                    if indirim_orani >= MIN_DISCOUNT_PERCENT:
                                        bulunan_indirim_sayisi += 1
                                        mesaj = (
                                            f"🔥 <b>%30+ AMAZON İNDİRİMİ!</b> 🔥\n\n"
                                            f"📦 <b>Ürün:</b> {urun_adi[:100]}...\n"
                                            f"📉 <b>İndirim Oranı:</b> %{indirim_orani:.1f}\n"
                                            f"💰 <b>Fiyat:</b> {eski_fiyat:.2f} TL ➔ {guncel_fiyat:.2f} TL\n\n"
                                            f"🔗 <a href='{urun_linki}'>Ürüne Git</a>"
                                        )
                                        telegram_mesaj_gonder(mesaj)
                                        print(f"[%{indirim_orani:.1f} İNDİRİM] {urun_adi[:30]} -> {urun_linki}")
                            except ValueError:
                                continue

                next_button = soup.find("a", {"class": "s-pagination-next"})
                if next_button and "href" in next_button.attrs:
                    current_url = "https://www.amazon.com.tr" + next_button["href"]
                    page_number += 1
                else:
                    print("Kategorideki tüm sayfalar taranarak son sayfaya ulaşıldı.")
                    break

            print(f"\nTarama Tamamlandı! Toplam {toplam_tespit_edilen_urun} ürün incelendi, %30 ve üzeri {bulunan_indirim_sayisi} indirim bulundu.")

        except Exception as e:
            print("Hata oluştu:", e)
        finally:
            browser.close()

if __name__ == "__main__":
    tum_sayfalari_tara()
