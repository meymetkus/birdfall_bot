import os
from bs4 import BeautifulSoup
from curl_cffi import requests

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

SEARCH_URL = "https://www.amazon.com.tr/s?rh=n%3A13709879031%2Cp_n_fulfilled_by_amazon%3A21345978031&dc&qid=1788469863&rnid=21345970031&ref=sr_nr_p_n_fulfilled_by_amazon_0"

def telegram_mesaj_gonder(mesaj):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": mesaj, "parse_mode": "HTML"}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"Telegram hatası: {e}")

def liste_tarasını_yap():
    try:
        # Chrome 120 tarayıcısı taklidi yaparak Amazon engelini aşar
        res = requests.get(
            SEARCH_URL,
            impersonate="chrome120",
            headers={"Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7"}
        )

        if res.status_code != 200:
            print(f"Sayfaya erişilemedi, Durum Kodu: {res.status_code}")
            return

        soup = BeautifulSoup(res.content, "html.parser")
        urun_kartlari = soup.find_all("div", {"data-component-type": "s-search-result"})
        print(f"Toplam {len(urun_kartlari)} ürün bulundu.")

        for kart in urun_kartlari:
            baslik_elem = kart.find("h2")
            if not baslik_elem:
                continue
            
            urun_adi = baslik_elem.get_text().strip()
            link_elem = baslik_elem.find("a")
            urun_linki = "https://www.amazon.com.tr" + link_elem["href"] if link_elem and "href" in link_elem.attrs else SEARCH_URL

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
                            
                            if indirim_orani >= 10:
                                mesaj = (
                                    f"🚨 <b>AMAZON LİSTE İNDİRİMİ!</b>\n\n"
                                    f"📦 <b>Ürün:</b> {urun_adi[:100]}...\n"
                                    f"📉 <b>İndirim:</b> %{indirim_orani:.1f}\n"
                                    f"💰 <b>Fiyat:</b> {eski_fiyat:.2f} TL ➔ {guncel_fiyat:.2f} TL\n\n"
                                    f"🔗 <a href='{urun_linki}'>Ürüne Git</a>"
                                )
                                telegram_mesaj_gonder(mesaj)
                                print(f"İndirim bulundu: {urun_adi[:30]}")
                    except ValueError:
                        continue

    except Exception as e:
        print("Hata oluştu:", e)

if __name__ == "__main__":
    liste_tarasını_yap()
