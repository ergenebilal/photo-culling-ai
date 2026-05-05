# AI Fotoğraf Ayıklama Sistemi

## Açıklama

AI Fotoğraf Ayıklama Sistemi, fotoğraf eleme sürecini hızlandıran, benzer tekrarları ayıran ve en iyi kareleri ön seçen web tabanlı bir sistemdir.

Sistem yerel olarak çalışır, fotoğrafları analiz eder, en iyi kareleri `Seçilenler` olarak hazırlar; düşük kaliteli, gereksiz ve benzer/tekrar kareleri `Elenenler` çıktısında toplar.

## Özellikler

- Web arayüz
- Otomatik ayıklama
- Benzer fotoğraf tespiti
- ZIP çıktıları
- Offline çalışma
- n8n entegrasyon hazırlığı

## Kurulum

Sanal ortam oluşturun:

```bash
python -m venv .venv
```

Windows PowerShell için sanal ortamı etkinleştirin:

```bash
.venv\Scripts\Activate.ps1
```

macOS veya Linux için sanal ortamı etkinleştirin:

```bash
source .venv/bin/activate
```

Paketleri yükleyin:

```bash
pip install -r requirements.txt
```

## Web ile Çalıştırma

Web uygulamasını başlatın:

```bash
python -m uvicorn app:app --reload
```

Tarayıcıdan açın:

```text
http://127.0.0.1:8000
```

## CLI Kullanım

```bash
python main.py --input ./input --output ./output
```

## Desteklenen Formatlar

Web arayüzünde desteklenen formatlar:

```text
.jpg .jpeg .png .webp .raw .cr2 .cr3 .nef .arw .dng .orf .rw2 .raf .pef .srw
```

CLI tarafında desteklenen formatlar:

```text
.jpg .jpeg .png .webp .raw .cr2 .cr3 .nef .arw .dng .orf .rw2 .raf .pef .srw
```

RAW desteği deneysel olarak sunulur. RAW dosyaları `rawpy` ile tanınır ve hız için dosyanın içindeki gömülü önizleme görseli analiz edilir. RAW içinde önizleme bulunamazsa sistem tam RAW çözümlemeye geri döner; kamera modeli, dosya yapısı veya RAW varyantına göre bazı dosyalar işlenemeyebilir.

## n8n Entegrasyonu

n8n entegrasyonu zorunlu değildir. Sistem n8n olmadan offline şekilde çalışır.

Webhook kullanmak için `.env` dosyası oluşturun ve `N8N_WEBHOOK_URL` değerini ekleyin:

```text
N8N_WEBHOOK_URL=
```

Bu alan boş bırakılırsa webhook tetiklenmez. Doluysa işlem tamamlandıktan sonra n8n webhook adresine işlem özeti gönderilir.

## Sunucuya Kurulum (VPS)

1. Sunucuya bağlanın:

```bash
ssh kullanici@SUNUCU_IP
```

2. Repoyu klonlayın:

```bash
git clone REPO_URL
cd photo-culling-ai
```

3. Sanal ortam oluşturun:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

4. Paketleri yükleyin:

```bash
pip install -r requirements.txt
```

5. Uygulamayı çalıştırın:

```bash
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

## Production Notları

- Nginx ile reverse proxy kullanın.
- SSL için Let's Encrypt ekleyin.
- Uygulamayı systemd ile sürekli çalışacak şekilde yapılandırın.
- Büyük dosya yüklemeleri için limit koyun.
- `runs/` klasörü düzenli olarak temizlenmelidir.
- Disk alanı düzenli izlenmelidir.

## Güvenlik Uyarısı

Bu sistem varsayılan olarak herkese açık kullanım için tasarlanmamıştır.

Public kullanım için şu ek önlemler uygulanmalıdır:

- Kullanıcı giriş sistemi
- Upload limiti
- Rate limit
- Disk kontrolü
- Düzenli çıktı temizliği

Gerçek gizli bilgiler `.env` dosyasında tutulmalıdır. `.env` dosyası GitHub'a gönderilmemelidir.

## GitHub'a Gönderme

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin REPO_URL
git push -u origin main
```
