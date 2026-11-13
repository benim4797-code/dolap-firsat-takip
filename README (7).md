# Dolap + Gardrops Fırsat Takip

Üst segment bebek ve çocuk markalarını **10 dakikada bir Dolap'ta**, **20 dakikada bir Gardrops'ta** tarar ve Telegram grubuna bildirim gönderir.

## Bildirimler
| Mesaj | Ne zaman |
|---|---|
| 🔥 Yeni ilan | Sıfır fiyatının en az %70 altında (varsayılan) |
| 💰 Piyasanın altında | Aynı sitedeki benzer ikinci el ilanların medyanının en az %40 altında (varsayılan) |
| 📉 İndirime girdi | Daha önce görülen bir ilan fiyat düşürüp eşiklerden birini geçtiğinde |
| 📊 Günlük özet | Her akşam 21:00 sonrası ilk taramada: tarama sayısı ve günün en ucuz 5 ilanı |
| ⚠️ Hata uyarısı | Site art arda okunamazsa (en fazla 2 saatte bir) veya tarama çökerse |

Bildirimler mümkünse ilan fotoğrafıyla gelir. Aynı ilan için bir kez bildirim gönderilir.

## Taranan markalar
beymen bebek, Stokke, Bugaboo, Cybex, Joolz, UPPAbaby, Nuna, Babyzen YOYO, Doona, Silver Cross, SNOO, BabyBjörn, Ergobaby, Elodie Details, Liewood, Done by Deer, Nattou, Bonpoint, Jacadi, Ralph Lauren bebek, Konges Sløjd, Burberry Kids, Moncler çocuk, Bobo Choses, Mini Rodini, Jellycat, Maileg, Lego Duplo, Grimm's, Plan Toys.

## Telegram komutları
Komutlar gruba yazılır ve bir sonraki taramada (en geç ~10 dk) işlenir.
- `/durum`: Ayarlar ve bugünkü sayılar
- `/markalar`: Taranan markalar
- `/ekle doona`, `/cikar doona`: Marka ya da arama ekle/çıkar
- `/esik 60`: Sıfır fiyatına göre eşik
- `/piyasa 40`: İkinci el piyasasına göre eşik
- `/test`: Test raporu
- `/yardim`: Komut listesi

## Kurulum (bir kez)
1. **Yeni bot:** Telegram'da @BotFather → `/newbot` → **token**'ı kopyalayın.
2. **Grup:** Yeni bir grup açın, botu ekleyin, gruba bir mesaj yazın. Tarayıcıda `https://api.telegram.org/bot<TOKEN>/getUpdates` adresini açın, `"chat":{"id":-100...}` değerini kopyalayın.
   *(Not: Komutların çalışması için bu sayfayı açtıktan sonra webhook kurmayın. Aynı token'ı başka bir programda kullanmayın.)*
3. **GitHub:** Yeni bir **public** depo açın ve bu klasördeki tüm dosyaları yükleyin (`.github` klasörü dahil).
4. **Settings → Secrets and variables → Actions → Secrets:** `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
   İsteğe bağlı Variables: `ESIK_YUZDE`, `PIYASA_ESIK_YUZDE`, `OZET_SAATI`, `DOLAP_URL_EKI`, `GARDROPS_ARAMA_URL`
5. **Actions → Dolap Fırsat Takip → Run workflow → Test modu ✔ → Run.** Gruba test raporu gelir.
6. Bir kez de test modu kapalıyken çalıştırın. Mevcut ilanlar bildirimsiz kaydedilir ve takip başlar.

## Notlar
- Sıfır fiyat (Akakçe/Cimri) ve piyasa fiyatı (benzer ilanların medyanı) tahminidir. Bildirimdeki linklerden doğrulayın.
- Piyasa kıyası için en az 4 benzer ilan gerekir. Daha az varsa sadece sıfır fiyata bakılır.
- Gardrops desteği canlı sitede henüz denenmedi. Test raporunda Gardrops ilanları görünmüyorsa arama linkini `GARDROPS_ARAMA_URL` değişkenine `{q}` içerecek şekilde yazın (ör. `https://www.gardrops.com/arama?q={q}`).
- GitHub'ın kendisi botu durdurursa (ör. depo 60 gün hareketsiz kalırsa) bot bunu kendisi bildiremez. Bot her taramada kayıt dosyasını güncellediği için normalde bu olmaz.
