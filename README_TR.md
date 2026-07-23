# MailPilot

MailPilot, Windows'ta yerel çalışan modern bir Gmail önceliklendirme ve özet uygulamasıdır. Gmail'i seçtiğin kapsama göre tarar, önemli mailleri öne çıkarır, ne yapman gerektiğini kısa şekilde gösterir.

## Öne Çıkanlar

- Modern PySide6 masaüstü arayüz
- Plus Jakarta Sans font asset'i
- Açık mod / koyu mod
- Birleşik tarama kapsamı:
  - Son taramadan beri
  - Son X saat
  - Tek gün
  - Tarih aralığı
- Takvim açılır tarih seçimi
- Önem sırasına göre mail listesi
- Aksiyon etiketleri: Acil, Cevap, Fatura/Ödeme, Toplantı, Güvenlik, Onay
- Gmail'de açma
- Tamamlandı / geri al
- Windows bildirimi
- Günlük rapor saati
- Önemli gönderen listesi
- Ayrı Özet ve Log sekmeleri
- Windows açılışında başlatma seçeneği

## Kurulum

1. Python 3.10 veya daha yeni bir sürüm kurulu olmalı.
2. Bu klasörde bir komut penceresi aç.
3. Gerekli paketleri kur:

```bat
pip install -r requirements.txt
```

4. Google Cloud Console'da Gmail API etkin bir OAuth istemcisi oluştur.
5. İndirilen OAuth dosyasını bu klasöre `credentials.json` adıyla koy.
6. Uygulamayı başlat:

```bat
run.bat
```

İlk Gmail bağlantısında tarayıcı açılır ve Google izin ekranı gelir. İzin tamamlanınca `token.json` yerelde oluşur.

## Kullanım

- Sol panelden uygulamayı aç/kapatabilir, temayı değiştirebilir ve taramayı başlatabilirsin.
- `Kapsam` alanı taramanın hangi mailleri getireceğini belirler.
- `Tek gün` ve `Tarih aralığı` seçildiğinde tarih alanları takvim açılır seçiciyle gelir.
- `Önemli gönderenler` alanına virgülle e-posta/ad parçaları yazabilirsin.
- Özet sekmesindeki filtreyle sadece acil, cevap, fatura, toplantı gibi mailleri görebilirsin.
- `Gmail'de Aç` seçili maili Gmail'de açar.
- `Tamamlandı` seçili maili yapılacaklardan düşürür; tekrar basınca geri alır.

## Yerel Notlar

- Mail içerikleri bu kod tarafından başka bir servise gönderilmez.
- Gmail erişimi Google OAuth ile yapılır.
- Ayarlar `settings.json` dosyasında tutulur.
- Özetler `summaries/` klasörüne yazılır.
- `credentials.json`, `token.json`, `settings.json` ve özetler git'e alınmaz.
