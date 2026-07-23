# MailPilot 🌸

MailPilot, Windows için hazırlanan küçük ama iş gören bir masaüstü mail asistanıdır. Gmail ve Outlook hesaplarını yerelde tarar, gelen mailleri önem sırasına göre toparlar ve sana kısaca şunu söyler:

> “Bunlardan hangisine bakman gerekiyor, ne bilmen gerekiyor, ne yapman gerekiyor?”

Amaç basit: gelen kutusunu açıp kaybolmak yerine, önemli işleri tek ekranda görmek.

## Neler Yapıyor? ✨

- Gmail ve Outlook hesabı ekleme
- Birden fazla mail hesabı arasında geçiş
- Seçilen hesaba göre otomatik tarama
- Önem sırasına göre mail özetleme
- Genel Özet ve Detaylı Özet modu
- Acil, Cevap, Güvenlik, Onay gibi renkli etiketler
- Tarih aralığı / tek gün / son taramadan beri tarama
- Takvimli tarih seçimi
- Açık mod ve koyu mod
- Windows başlangıcında otomatik çalışma
- Simge alanına küçültme
- Rapor saati geldiğinde mini genel özet pop-up’ı
- Özet ve log dosyalarını yerelde tutma
- CMD penceresi açmadan `.exe` ile çalışma

## Hazır Kullanım: EXE Paketi 🚀

Build sonrası kullanım için beklenen klasör yapısı:

```text
MailPilot-EXE
├─ MailPilot.exe
├─ credentials
│  ├─ credentials.json
│  ├─ outlook_credentials.json
│  ├─ settings.json
│  ├─ token.json
│  └─ accounts
└─ ozet-loglari
```

Çalıştırmak için sadece:

```text
MailPilot.exe
```

CMD penceresi açılmaz. Uygulama normal Windows masaüstü uygulaması gibi çalışır.

## Credentials Klasörü 🔐

MailPilot kişisel bağlantı dosyalarını exe’nin içinde tutmaz. Bunlar exe’nin yanında duran `credentials` klasöründe kalır.

Bu klasör şunlar için kullanılır:

- Gmail OAuth dosyası
- Outlook OAuth dosyası
- Oturum token’ları
- Uygulama ayarları
- Çoklu hesap token kayıtları

GitHub’a gönderilmez. `.gitignore` içinde korumaya alınmıştır.

## Gmail Kurulumu 📬

Gmail için `credentials/credentials.json` gerekir.

Kısa yol:

1. Google Cloud Console’da proje oluştur.
2. Gmail API’yi aç.
3. OAuth Client oluştur.
4. Uygulama türü olarak Desktop App seç.
5. İndirilen JSON dosyasını şu isimle koy:

```text
credentials/credentials.json
```

Sonra uygulamada:

```text
E-posta ekle > Gmail ekle
```

İlk girişte tarayıcı açılır. İzin verince token dosyası yerelde oluşur.

## Outlook Kurulumu 💌

Outlook için `credentials/outlook_credentials.json` gerekir.

Dosya formatı:

```json
{
  "client_id": "MICROSOFT_APP_CLIENT_ID",
  "tenant": "common"
}
```

Microsoft Entra tarafında:

1. App registration oluştur.
2. Supported account types kısmında kişisel Microsoft hesaplarını da destekleyen seçeneği seç.
3. Authentication altında `Allow public client flows` ayarını `Yes` yap.
4. Microsoft Graph izinlerinde şunlar olsun:
   - `User.Read`
   - `Mail.Read`
   - `offline_access`

Sonra uygulamada:

```text
E-posta ekle > Outlook ekle
```

Tarayıcıda Microsoft girişini tamamlayınca hesap MailPilot’a eklenir.

## Özet Logları 📝

MailPilot özet dosyalarını şu klasöre yazar:

```text
ozet-loglari
```

Bu klasör de GitHub’a gönderilmez. İçinde kişisel mail özetleri olabileceği için yerelde kalır.

## Geliştirici Modu 🛠️

Projeyi Python ile çalıştırmak için:

```bat
pip install -r requirements.txt
python main.py
```

Eski yardımcı dosyalar hâlâ duruyor:

```bat
run.bat
run_hidden.vbs
```

Ama son kullanıcı için önerilen kullanım `.exe` paketidir.

## EXE Üretmek 🧩

PyInstaller ile konsolsuz tek dosya exe üretmek için:

```bat
pyinstaller --noconfirm --clean --onefile --windowed --name MailPilot --icon assets\brand\logo\mailpilot.ico --add-data "assets;assets" main.py
```

Çıktı:

```text
dist/MailPilot.exe
```

Sonra exe’nin yanına şu klasörleri koy:

```text
credentials
ozet-loglari
```

## Güvenlik Notu 🧠

MailPilot yerel çalışır. Mail bağlantı token’ları ve özet logları bilgisayarında kalır.

GitHub’a gönderilmemesi gerekenler:

- `credentials/`
- `ozet-loglari/`
- `accounts/`
- `token.json`
- `settings.json`
- `credentials.json`
- `outlook_credentials.json`
- `dist/`
- `build/`
- `.venv/`

Bunların hepsi `.gitignore` içinde.

## Proje Ruh Hali 🌼

MailPilot’un amacı “mail uygulamasının yerine geçmek” değil; gelen kutusundaki gürültüyü azaltmak.

Kısaca:

- Önce önemli olanı gösterir.
- Gereksiz laf kalabalığını azaltır.
- Yapılacakları netleştirir.
- Detaya inmek istersen seni asıl maile götürür.

Küçük, yerel, hızlı ve sakin bir gelen kutusu yardımcısı.

