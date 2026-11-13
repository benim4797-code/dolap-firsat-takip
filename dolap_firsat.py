"""
Dolap + Gardrops Fırsat Takip
-----------------------------
Üst segment bebek/çocuk markalarını Dolap'ta (ve sırayla Gardrops'ta) tarar.
Telegram'a gönderilen bildirimler:
  🔥 Yeni ilan sıfırından en az %ESIK ucuz
  💰 Yeni ilan, ikinci el piyasasının (benzer ilanların medyanı) en az %PIYASA_ESIK altında
  📉 Daha önce görülen ilan indirime girip yukarıdaki eşiklerden birini geçti
  📊 Her akşam günlük özet, ⚠️ Dolap/Gardrops okunamazsa hata uyarısı

Telegram komutları (grupta yazılır, bir sonraki taramada ~10 dk içinde işlenir):
  /durum  /markalar  /ekle <marka>  /cikar <marka>  /esik <sayı>  /piyasa <sayı>  /test  /yardim

Ortam değişkenleri (GitHub Secrets / Variables):
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (zorunlu)
  ESIK_YUZDE (70), PIYASA_ESIK_YUZDE (40), OZET_SAATI (21, Türkiye saati)
  DOLAP_URL_EKI, GARDROPS_ARAMA_URL, TEST_MODU
"""

import json
import os
import re
import statistics
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
VARSAYILAN_ESIK = float(os.environ.get("ESIK_YUZDE") or 70)
VARSAYILAN_PIYASA_ESIK = float(os.environ.get("PIYASA_ESIK_YUZDE") or 40)
OZET_SAATI = int(os.environ.get("OZET_SAATI") or 21)
URL_EKI = os.environ.get("DOLAP_URL_EKI", "")
STATE_FILE = Path(__file__).with_name("ilanlar.json")
MAX_INCELEME = 15          # bir çalıştırmada en fazla kaç ilan detaylı incelensin
HATA_UYARI_ARALIK = 2 * 3600
TR = timezone(timedelta(hours=3))
UA = ("Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Mobile Safari/537.36")

VARSAYILAN_MARKALAR = [
    "beymen bebek",
    # bebek arabası, oto koltuğu, mama sandalyesi, beşik
    "stokke", "bugaboo", "cybex", "joolz", "uppababy", "nuna",
    "babyzen yoyo", "doona", "silver cross", "snoo",
    # taşıma, bakım, beslenme
    "babybjörn", "ergobaby", "elodie details", "liewood", "done by deer", "nattou",
    # giyim
    "bonpoint", "jacadi", "ralph lauren bebek", "konges sløjd",
    "burberry kids", "moncler çocuk", "bobo choses", "mini rodini",
    # oyuncak
    "jellycat", "maileg", "lego duplo", "grimm's", "plan toys",
]

SITELER = {
    "Dolap": {
        "arama": "https://dolap.com/ara?q={q}" + URL_EKI,
        "link_js": "/urun/",                     # ilan linklerinde geçen parça
        "her_turda": True,
    },
    "Gardrops": {
        "arama": os.environ.get("GARDROPS_ARAMA_URL") or "https://www.gardrops.com/arama?q={q}",
        "link_js": "",                           # boş: kart metninde fiyat olan site içi linkler
        "her_turda": False,                      # iki turda bir taranır (süre için)
    },
}

FIYAT_RE = re.compile(r"(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{1,2}))?\s*(?:TL|₺)", re.I)
INDIRIM_RE = re.compile(r"(\d{1,3}(?:\.\d{3})*|\d+)\s*(?:TL|₺)\s*İndirim", re.I)
GEREKSIZ = re.compile(
    r"\b(sıfır|sifir|az kullanılmış|temiz|orijinal|etiketli|tek ebat|beden|"
    r"\d+\s*-\s*\d+\s*ay|\d+\s*ay|\d+\s*yaş|kargo bedava|fırsat|acil)\b", re.I)


# ================================================================ yardımcılar
def tl_to_float(tam, kurus=None):
    return float(tam.replace(".", "") + "." + (kurus or "0"))


def metindeki_fiyatlar(metin):
    """Metindeki TL fiyatları (kupon indirim tutarları hariç)."""
    temiz = INDIRIM_RE.sub(" ", metin or "")
    return [tl_to_float(m.group(1), m.group(2)) for m in FIYAT_RE.finditer(temiz)]


def kart_fiyati(metin):
    f = [x for x in metindeki_fiyatlar(metin) if x >= 10]
    return min(f) if f else None


def tl(x):
    return f"{x:,.0f}".replace(",", ".")


def kacis(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def arama_terimi(baslik):
    t = GEREKSIZ.sub(" ", baslik or "")
    t = re.sub(r"[^\wçğıöşüÇĞİÖŞÜ\s&']", " ", t)
    return " ".join(t.split()[:7])


def bugun():
    return datetime.now(TR).strftime("%Y-%m-%d")


def gun_basi_ts():
    n = datetime.now(TR)
    return int(n.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())


# ================================================================ Telegram
def tg(metod, **params):
    if not TOKEN or not CHAT_ID:
        if metod in ("sendMessage", "sendPhoto"):
            print(f"[telegram yok] {params.get('text') or params.get('caption')}")
        return {}
    veri = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/{metod}", data=veri)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def mesaj(metin):
    try:
        tg("sendMessage", chat_id=CHAT_ID, text=metin[:4000], parse_mode="HTML",
           disable_web_page_preview="true")
    except Exception as e:
        print(f"[uyarı] Telegram mesajı gönderilemedi: {e}")


def foto_mesaj(foto_url, metin):
    """Fotoğraflı bildirim; foto yoksa veya hata olursa düz mesaj."""
    if foto_url and len(metin) <= 1024:
        try:
            tg("sendPhoto", chat_id=CHAT_ID, photo=foto_url, caption=metin, parse_mode="HTML")
            return
        except Exception as e:
            print(f"[uyarı] fotoğraf gönderilemedi, düz mesaj atılıyor: {e}")
    mesaj(metin)


# ================================================================ durum
def durum_yukle():
    veri = {}
    if STATE_FILE.exists():
        try:
            veri = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            veri = {}
    veri.setdefault("ilanlar", {})
    veri.setdefault("tohumlanan", [])
    veri.setdefault("ayarlar", {})
    veri["ayarlar"].setdefault("esik", VARSAYILAN_ESIK)
    veri["ayarlar"].setdefault("piyasa_esik", VARSAYILAN_PIYASA_ESIK)
    veri["ayarlar"].setdefault("markalar", list(VARSAYILAN_MARKALAR))
    veri.setdefault("tg_offset", 0)
    veri.setdefault("tur", 0)
    veri.setdefault("gunluk", {"tarih": bugun(), "tarama": 0, "yeni": 0, "bildirim": 0})
    veri.setdefault("son_ozet", "")
    veri.setdefault("hata", {"sayac": 0, "son_uyari": 0})
    return veri


def durum_kaydet(durum):
    ilanlar = durum["ilanlar"]
    if len(ilanlar) > 5000:
        for link in sorted(ilanlar, key=lambda k: ilanlar[k].get("zaman", 0))[:len(ilanlar) - 5000]:
            del ilanlar[link]
    STATE_FILE.write_text(json.dumps(durum, ensure_ascii=False, indent=1), encoding="utf-8")


# ================================================================ Telegram komutları
YARDIM = ("<b>Komutlar</b>\n"
          "/durum – ayarlar ve bugünkü sayılar\n"
          "/markalar – taranan markalar\n"
          "/ekle doona – marka/arama ekle\n"
          "/cikar doona – marka/arama çıkar\n"
          "/esik 60 – sıfıra göre ucuzluk eşiği (%)\n"
          "/piyasa 40 – ikinci el piyasasına göre eşik (%)\n"
          "/test – bir sonraki taramada test raporu gönder\n"
          "Komutlar bir sonraki taramada (~10 dk) işlenir.")


def komutlari_isle(durum):
    """Gruba yazılan komutları okur ve ayarları günceller. /test istendiyse True döner."""
    if not TOKEN or not CHAT_ID:
        return False
    try:
        cevap = tg("getUpdates", offset=durum["tg_offset"] + 1, timeout=0,
                   allowed_updates='["message"]')
    except Exception as e:
        print(f"[uyarı] komutlar okunamadı: {e}")
        return False
    ayar, test_istendi = durum["ayarlar"], False
    for g in cevap.get("result", []):
        durum["tg_offset"] = max(durum["tg_offset"], g["update_id"])
        m = g.get("message") or {}
        if str(m.get("chat", {}).get("id")) != str(CHAT_ID):
            continue  # sadece kendi grubumuzdan gelen komutlar
        metin = (m.get("text") or "").strip()
        if not metin.startswith("/"):
            continue
        komut, _, arg = metin.partition(" ")
        komut = komut.split("@")[0].lower()
        arg = arg.strip().lower()
        if komut in ("/yardim", "/start", "/help"):
            mesaj(YARDIM)
        elif komut == "/durum":
            g_ = durum["gunluk"]
            mesaj(f"<b>Durum</b>\nSıfıra göre eşik: %{ayar['esik']:.0f}\n"
                  f"Piyasaya göre eşik: %{ayar['piyasa_esik']:.0f}\n"
                  f"Marka sayısı: {len(ayar['markalar'])}\n"
                  f"Bugün: {g_['tarama']} tarama, {g_['yeni']} yeni ilan, {g_['bildirim']} bildirim\n"
                  f"Kayıtlı ilan: {len(durum['ilanlar'])}")
        elif komut == "/markalar":
            mesaj("<b>Taranan markalar</b>\n" + ", ".join(ayar["markalar"]))
        elif komut == "/ekle" and arg:
            if arg not in ayar["markalar"]:
                ayar["markalar"].append(arg)
            mesaj(f"✅ Eklendi: {kacis(arg)} (mevcut ilanları sessizce kaydedilecek)")
        elif komut == "/cikar" and arg:
            if arg in ayar["markalar"]:
                ayar["markalar"].remove(arg)
                mesaj(f"🗑 Çıkarıldı: {kacis(arg)}")
            else:
                mesaj(f"Listede yok: {kacis(arg)}")
        elif komut in ("/esik", "/piyasa"):
            try:
                deger = float(arg.replace("%", ""))
                assert 5 <= deger <= 95
                ayar["esik" if komut == "/esik" else "piyasa_esik"] = deger
                mesaj(f"✅ {'Sıfıra' if komut == '/esik' else 'Piyasaya'} göre eşik: %{deger:.0f}")
            except Exception:
                mesaj("Kullanım: /esik 60 veya /piyasa 40 (5-95 arası)")
        elif komut == "/test":
            test_istendi = True
            mesaj("🧪 Test raporu hazırlanıyor…")
        else:
            mesaj(YARDIM)
    return test_istendi


# ================================================================ sayfa okuma
KART_JS = """(linkParca) => {
    const sonuc = [], gorulen = new Set(), host = location.host;
    for (const a of document.querySelectorAll('a[href]')) {
        let url;
        try { url = new URL(a.href); } catch (e) { continue; }
        if (url.host !== host) continue;
        const href = url.origin + url.pathname;
        if (linkParca && !href.includes(linkParca)) continue;
        if (!linkParca && (url.pathname.split('/').filter(Boolean).length < 1
            || /arama|ara\\b|kategori|giris|uye|profil|kullanici|sepet|favori/.test(url.pathname))) continue;
        if (gorulen.has(href)) continue;
        let kart = a;
        for (let i = 0; i < 6 && kart.parentElement; i++) {
            if ((kart.innerText || '').match(/(TL|₺)/)) break;
            kart = kart.parentElement;
        }
        const metin = (kart.innerText || '').trim();
        if (!metin.match(/(TL|₺)/) || metin.length > 600) continue;
        gorulen.add(href);
        const img = kart.querySelector('img');
        sonuc.push({link: href, metin: metin, foto: img ? (img.currentSrc || img.src) : null});
    }
    return sonuc;
}"""


def site_ilanlari(page, site, terim):
    ayar = SITELER[site]
    page.goto(ayar["arama"].format(q=urllib.parse.quote(terim)),
              wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2500)
    page.mouse.wheel(0, 4000)
    page.wait_for_timeout(1200)
    return page.evaluate(KART_JS, ayar["link_js"])


def ilan_detay(page, link, kart_metni, kart_foto):
    """İlan sayfasından tam başlık, güncel fiyat ve fotoğraf."""
    baslik, fiyat, foto = None, None, None
    try:
        page.goto(link, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)
        for blok in page.locator('script[type="application/ld+json"]').all_inner_texts():
            try:
                veri = json.loads(blok)
            except Exception:
                continue
            for v in (veri if isinstance(veri, list) else [veri]):
                if isinstance(v, dict) and v.get("@type") in ("Product", "Offer"):
                    baslik = baslik or v.get("name")
                    img = v.get("image")
                    foto = foto or (img[0] if isinstance(img, list) and img else img if isinstance(img, str) else None)
                    teklif = v.get("offers") or {}
                    if isinstance(teklif, list):
                        teklif = teklif[0] if teklif else {}
                    if isinstance(teklif, dict) and teklif.get("price"):
                        fiyat = float(str(teklif["price"]).replace(",", "."))

        def meta(ad):
            m = page.locator(f'meta[property="{ad}"]')
            return m.first.get_attribute("content") if m.count() else None
        baslik = baslik or meta("og:title")
        foto = foto or meta("og:image")
        if not fiyat and meta("product:price:amount"):
            fiyat = float(meta("product:price:amount").replace(",", "."))
    except Exception as e:
        print(f"[uyarı] ilan sayfası okunamadı {link}: {e}")
    fiyat = fiyat or kart_fiyati(kart_metni)
    baslik = baslik or (kart_metni or "").split("\n")[0][:120]
    baslik = re.sub(r"\s*[|\-–]\s*(Dolap|Gardrops).*$", "", baslik or "").strip()
    return {"baslik": baslik, "fiyat": fiyat, "foto": foto or kart_foto}


def sifir_fiyat_bul(page, baslik):
    """Akakçe, olmazsa Cimri aramasındaki ilk sonuçların medyan fiyatı."""
    terim = arama_terimi(baslik)
    kaynaklar = [
        ("Akakçe", "https://www.akakce.com/arama/?q=" + urllib.parse.quote(terim)),
        ("Cimri", "https://www.cimri.com/arama?q=" + urllib.parse.quote(terim)),
    ]
    for ad, url in kaynaklar:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2500)
            fiyatlar = [f for f in metindeki_fiyatlar(page.inner_text("body")) if f >= 50][:8]
            if len(fiyatlar) >= 2:
                return statistics.median(fiyatlar[:5]), url
        except Exception as e:
            print(f"[uyarı] {ad} araması başarısız ({terim}): {e}")
    return None, kaynaklar[0][1]


def piyasa_fiyati_bul(page, site, baslik, haric_link):
    """Aynı sitede benzer ilanların medyan fiyatı (ikinci el piyasa değeri)."""
    terim = arama_terimi(baslik)
    try:
        kartlar = site_ilanlari(page, site, terim)
    except Exception as e:
        print(f"[uyarı] piyasa araması başarısız ({terim}): {e}")
        return None, 0
    fiyatlar = [kart_fiyati(k["metin"]) for k in kartlar if k["link"] != haric_link]
    fiyatlar = [f for f in fiyatlar if f][:15]
    if len(fiyatlar) < 4:          # karşılaştırma için yeterli benzer ilan yok
        return None, len(fiyatlar)
    return statistics.median(fiyatlar), len(fiyatlar)


# ================================================================ değerlendirme
def oranlar(fiyat, kayit):
    s = (1 - fiyat / kayit["sifir"]) * 100 if kayit.get("sifir") else None
    p = (1 - fiyat / kayit["piyasa"]) * 100 if kayit.get("piyasa") else None
    return s, p


def firsat_mi(s, p, ayar):
    return (s is not None and s >= ayar["esik"]) or (p is not None and p >= ayar["piyasa_esik"])


def bildirim_metni(tur, k, fiyat, s, p, ayar, onceki=None):
    sifir_firsat = s is not None and s >= ayar["esik"]
    if tur == "indirim":
        ust = "📉 <b>İndirime girdi — " + (f"sıfırından %{s:.0f} ucuz" if sifir_firsat
                                         else f"piyasanın %{p:.0f} altında") + "</b>"
    elif sifir_firsat:
        ust = f"🔥 <b>Yeni ilan — sıfırından %{s:.0f} ucuz</b>"
    else:
        ust = f"💰 <b>Yeni ilan — ikinci el piyasasının %{p:.0f} altında</b>"
    satirlar = [ust, f"{kacis(k['baslik'])} <i>({k['site']})</i>"]
    if onceki:
        satirlar.append(f"Fiyat: <s>{tl(onceki)} TL</s> → <b>{tl(fiyat)} TL</b>")
    else:
        satirlar.append(f"Fiyat: <b>{tl(fiyat)} TL</b>")
    if k.get("sifir"):
        satirlar.append(f"Sıfır (tahmini): {tl(k['sifir'])} TL → %{s:.0f} ucuz")
    if k.get("piyasa"):
        satirlar.append(f"İkinci el piyasa: {tl(k['piyasa'])} TL ({k.get('piyasa_n', 0)} ilan) → %{p:.0f} altında")
    satirlar.append(f'<a href="{k["link"]}">İlana git</a>' +
                    (f' · <a href="{kacis(k["kaynak"])}">Sıfır fiyat</a>' if k.get("sifir") and k.get("kaynak") else ""))
    return "\n".join(satirlar)


# ================================================================ özet ve hata
def gunluk_ozet(durum):
    g, ayar = durum["gunluk"], durum["ayarlar"]
    bas = gun_basi_ts()
    bugunku = [k for k in durum["ilanlar"].values()
               if k.get("zaman", 0) >= bas and k.get("ucuzluk") is not None]
    bugunku.sort(key=lambda k: k["ucuzluk"], reverse=True)
    satirlar = [f"📊 <b>Günlük özet — {bugun()}</b>",
                f"{g['tarama']} tarama · {g['yeni']} yeni ilan · {g['bildirim']} bildirim",
                f"Eşikler: sıfıra göre %{ayar['esik']:.0f}, piyasaya göre %{ayar['piyasa_esik']:.0f}"]
    if bugunku:
        satirlar.append("\n<b>Günün en ucuz 5 ilanı</b>")
        for k in bugunku[:5]:
            satirlar.append(f'• %{k["ucuzluk"]:.0f} — <a href="{k["link"]}">{kacis(k["baslik"][:60])}</a> '
                            f'({tl(k["fiyat"])} TL)')
    else:
        satirlar.append("Bugün değerlendirilebilen yeni ilan olmadı.")
    mesaj("\n".join(satirlar))


def hata_durumu(durum, basarili, aciklama=""):
    h, simdi = durum["hata"], int(time.time())
    if basarili:
        if h["sayac"] >= 2:
            mesaj("✅ Bot yeniden ilanları okuyabiliyor.")
        h["sayac"] = 0
        return
    h["sayac"] += 1
    if h["sayac"] >= 2 and simdi - h["son_uyari"] >= HATA_UYARI_ARALIK:
        h["son_uyari"] = simdi
        mesaj(f"⚠️ <b>Bot ilanları okuyamıyor</b> ({h['sayac']} tarama üst üste)\n{kacis(aciklama)}\n"
              "Site erişimi engellemiş veya sayfa yapısı değişmiş olabilir. Actions kayıtlarına bakın.")


# ================================================================ test raporu
def test_raporu(page, ilanlar):
    satirlar = [f"🧪 <b>Test</b> — {len(ilanlar)} ilan okundu "
                f"({', '.join(sorted({i['site'] for i in ilanlar})) or 'site yok'})"]
    for ilan in ilanlar[:3]:
        d = ilan_detay(page, ilan["link"], ilan["metin"], ilan.get("foto"))
        k = {"sifir": None, "piyasa": None}
        if d["fiyat"]:
            k["sifir"], _ = sifir_fiyat_bul(page, d["baslik"])
            k["piyasa"], n = piyasa_fiyati_bul(page, ilan["site"], d["baslik"], ilan["link"])
        s, p = oranlar(d["fiyat"], k) if d["fiyat"] else (None, None)
        satirlar.append(
            f"• {kacis(d['baslik'][:70])} ({ilan['site']})\n"
            f"  {tl(d['fiyat']) if d['fiyat'] else '?'} TL | sıfır {tl(k['sifir']) if k['sifir'] else '?'}"
            f"{f' (%{s:.0f})' if s is not None else ''} | piyasa {tl(k['piyasa']) if k['piyasa'] else '?'}"
            f"{f' (%{p:.0f})' if p is not None else ''} | foto {'var' if d['foto'] else 'yok'}\n"
            f"  {ilan['link']}")
    mesaj("\n".join(satirlar))


# ================================================================ ana akış
def main():
    from playwright.sync_api import sync_playwright

    durum = durum_yukle()
    ayar, kayit = durum["ayarlar"], durum["ilanlar"]
    simdi = int(time.time())
    if durum["gunluk"]["tarih"] != bugun():
        durum["gunluk"] = {"tarih": bugun(), "tarama": 0, "yeni": 0, "bildirim": 0}
    durum["tur"] += 1
    test = os.environ.get("TEST_MODU") == "1" or komutlari_isle(durum)
    tohumlanan = set(durum["tohumlanan"])

    with sync_playwright() as p:
        tarayici = p.chromium.launch(headless=True)
        ctx = tarayici.new_context(user_agent=UA, locale="tr-TR",
                                   viewport={"width": 412, "height": 915})
        page = ctx.new_page()

        # ---------- 1) tüm aramaları tara
        ilanlar, gorulen_link, yeni_tohum, site_sayac = [], set(), [], {}
        for site, s_ayar in SITELER.items():
            if not s_ayar["her_turda"] and durum["tur"] % 2 and not test:
                continue
            site_sayac[site] = 0
            for terim in ayar["markalar"]:
                anahtar = f"{site}|{terim}"
                try:
                    bulunan = site_ilanlari(page, site, terim)
                except Exception as e:
                    print(f"[uyarı] {site} '{terim}' okunamadı: {e}")
                    continue
                site_sayac[site] += len(bulunan)
                ilk_kez = anahtar not in tohumlanan
                for i in bulunan:
                    if i["link"] in gorulen_link:
                        continue
                    gorulen_link.add(i["link"])
                    i["site"] = site
                    if ilk_kez and i["link"] not in kayit:
                        kayit[i["link"]] = {"link": i["link"], "site": site,
                                            "baslik": i["metin"].split("\n")[0][:120],
                                            "fiyat": kart_fiyati(i["metin"]), "zaman": simdi,
                                            "sessiz": True}
                    ilanlar.append(i)
                if ilk_kez and bulunan:
                    yeni_tohum.append(anahtar)
        print("Okunan ilan sayısı:", site_sayac)
        durum["gunluk"]["tarama"] += 1

        bos_siteler = [s for s, n in site_sayac.items() if n == 0]
        hata_durumu(durum, basarili=not bos_siteler,
                    aciklama="Okunamayan: " + ", ".join(bos_siteler) if bos_siteler else "")

        if test:
            test_raporu(page, ilanlar)
        if yeni_tohum:
            durum["tohumlanan"] = sorted(tohumlanan | set(yeni_tohum))
            ozet = {}
            for a in yeni_tohum:
                s, t = a.split("|", 1)
                ozet.setdefault(s, []).append(t)
            mesaj("✅ Takibe eklenenler:\n" + "\n".join(f"{s}: {', '.join(t)}" for s, t in ozet.items()) +
                  "\nMevcut ilanları kaydedildi; bundan sonra yeni ve indirime girenler bildirilecek.")

        # ---------- 2) yeni ilanlar ve fiyat düşüşleri
        incelenen = 0
        for ilan in ilanlar:
            link, site = ilan["link"], ilan["site"]
            kfiyat = kart_fiyati(ilan["metin"])
            k = kayit.get(link)

            if k:
                # --- daha önce görülen ilan: fiyat düştü mü?
                if not kfiyat or not k.get("fiyat") or kfiyat >= k["fiyat"]:
                    continue
                onceki, k["fiyat"] = k["fiyat"], kfiyat
                print(f"- indirim: {k['baslik']} {onceki:.0f} → {kfiyat:.0f} TL")
                if k.get("bildirildi"):
                    continue
                if k.get("sessiz") and incelenen < MAX_INCELEME:
                    # ilk kayıttan kalan ilan: karşılaştırma bilgilerini şimdi topla
                    incelenen += 1
                    d = ilan_detay(page, link, ilan["metin"], ilan.get("foto"))
                    k.update(baslik=d["baslik"] or k["baslik"], foto=d["foto"], sessiz=False)
                    k["sifir"], k["kaynak"] = sifir_fiyat_bul(page, k["baslik"])
                    k["piyasa"], k["piyasa_n"] = piyasa_fiyati_bul(page, site, k["baslik"], link)
                s, p = oranlar(kfiyat, k)
                k["ucuzluk"] = max(x for x in (s, p, -999) if x is not None)
                if firsat_mi(s, p, ayar):
                    k["bildirildi"] = True
                    durum["gunluk"]["bildirim"] += 1
                    foto_mesaj(k.get("foto") or ilan.get("foto"),
                               bildirim_metni("indirim", k, kfiyat, s, p, ayar, onceki))
                    time.sleep(1)
                continue

            # --- yeni ilan
            if incelenen >= MAX_INCELEME:
                continue  # kalanlar bir sonraki taramada
            incelenen += 1
            durum["gunluk"]["yeni"] += 1
            d = ilan_detay(page, link, ilan["metin"], ilan.get("foto"))
            k = {"link": link, "site": site, "baslik": d["baslik"], "fiyat": d["fiyat"] or kfiyat,
                 "foto": d["foto"], "zaman": simdi}
            kayit[link] = k
            if not k["fiyat"]:
                print(f"- fiyat okunamadı: {link}")
                continue
            k["sifir"], k["kaynak"] = sifir_fiyat_bul(page, k["baslik"])
            k["piyasa"], k["piyasa_n"] = piyasa_fiyati_bul(page, site, k["baslik"], link)
            s, p = oranlar(k["fiyat"], k)
            k["ucuzluk"] = max(x for x in (s, p, -999) if x is not None)
            print(f"- yeni: {k['baslik']} | {k['fiyat']:.0f} TL | sıfır {k['sifir']} | piyasa {k['piyasa']}")
            if firsat_mi(s, p, ayar):
                k["bildirildi"] = True
                durum["gunluk"]["bildirim"] += 1
                foto_mesaj(k["foto"], bildirim_metni("yeni", k, k["fiyat"], s, p, ayar))
                time.sleep(1)

        tarayici.close()

    # ---------- 3) günlük özet
    if datetime.now(TR).hour >= OZET_SAATI and durum["son_ozet"] != bugun():
        gunluk_ozet(durum)
        durum["son_ozet"] = bugun()

    durum_kaydet(durum)
    return 0


if __name__ == "__main__":
    sys.exit(main())
