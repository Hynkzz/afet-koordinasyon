# Afet Koordinasyon Sistemi

İnternet ve şebeke yokken tek bir PC üzerinde çalışan afet koordinasyon paneli.
Yapay zekâ (insan ve vuruş tespiti), mesh haberleşme simülatörü ve sığınak
verisi aynı makinedeki sunucuya bağlanır; operatör tarayıcıdaki panelden izler
ve mesaj gönderir.

Bu depo Bilgisayar bölümünün kısmıdır: sunucu, panel, şifreleme ve ortak
veri formatları (`shared/`).

## Kurulum

Python 3.11 veya üstü gerekir.

```bash
cd afet-projesi
python -m venv .venv
.venv/bin/pip install -r requirements.txt      # Windows: .venv\Scripts\pip
```

Mesajlar ortak bir anahtarla (PSK) şifrelenir. Anahtarı bir kez üretip `.env`
dosyasına yazın:

```bash
python -c "import os,base64;print('AFET_PSK='+base64.b64encode(os.urandom(32)).decode())" > .env
```

Mesh simülatörü de aynı anahtarı kullanmalı; `.env` dosyasını ekip içinde
paylaşın, git'e eklemeyin (`.gitignore`'da).

## Çalıştırma

```bash
.venv/bin/python -m server.main --kaynak mock
```

Tarayıcıda `http://localhost:8000` açın. `--kaynak mock` sahte veri üretir;
gerçek kaynaklar bağlandığında `--kaynak yok` ile yalnızca dışarıdan gelen
veri gösterilir.

| Argüman | Varsayılan | Açıklama |
|---|---|---|
| `--kaynak` | `AFET_KAYNAK` ortam değişkeni, o da yoksa `yok` | `mock` veya `yok` |
| `--host` | `127.0.0.1` | Başka cihazlardan erişim için `0.0.0.0` |
| `--port` | `8000` | |

Testler:

```bash
.venv/bin/python -m pytest
```

## Mimari

```
 Yapay zekâ (EEE)        Mesh simülatörü (EEE)      Sığınak verisi (İnşaat)
 YOLO, vuruş tespiti     BLE düğümleri, RSSI        GeoJSON
        |                        |                          |
 POST /api/olay           paket, sinyal          data/siginaklar.geojson
        |                        |                          |
        v                        v                          v
 +--------------------------------------------------------------------+
 |  FastAPI sunucusu (server/)                                        |
 |  şema doğrulama -> olay birleştirme -> şifre çözme -> WebSocket    |
 +--------------------------------------------------------------------+
              |  /ws: olay, mesaj, sinyal         ^  POST /api/mesaj
              v                                   |
 +--------------------------------------------------------------------+
 |  Tarayıcı paneli (web/): izleme, olaylar, mesajlar, harita, sinyal |
 +--------------------------------------------------------------------+
```

- Bölümler birbirine yalnızca `shared/` altındaki JSON şemalarıyla bağlanır.
  Formatların açıklaması ve örnekleri: [`shared/README.md`](shared/README.md).
- Aynı etiketli olaylar 3 saniye içinde tekrar gelirse tek olayda birleşir,
  `adet` artar. Süre son görülmeden sayılır.
- Mesajlar ChaCha20-Poly1305 ile şifrelidir. Başlık (`id`, `tur`, `kaynak`,
  `hedef`, `sayac`) açık ama doğrulanır; metin ve konum şifrelidir. Her
  kaynak için son sayaç tutulur, aynı veya küçük sayaçlı paket reddedilir.
- Panel kütüphaneleri (Leaflet, Chart.js) `web/vendor/` altında, CDN yok.
  Harita karoları şimdilik çevrimiçi OSM'den geliyor; çevrimdışı karolar
  sonraki adımda.

```
afet-projesi/
  shared/          ortak şemalar ve açıklamaları
  server/
    main.py        FastAPI, WebSocket, olay birleştirme
    models.py      pydantic modelleri (shared/ ile birebir)
    crypto.py      şifreleme ve tekrar koruması
    sources/       veri kaynakları: base.py arayüz, mock.py sahte veri
  web/             panel (HTML, CSS, JS, vendor/)
  data/            örnek sığınaklar
  scripts/         ölçüm betikleri
  tests/
```

## Diğer bölümler nasıl bağlanır

Önce sunucuyu açın (`python -m server.main`), sonra kendi programınızı
çalıştırın. Gönderdiğiniz veri panelde hemen görünür; şemaya uymazsa sunucu
422 ve sebebini döner.

### Yapay zekâ: `POST /api/olay`

Ek kütüphane gerekmez. YOLO (ultralytics) ile örnek:

```python
import json
import urllib.request
from datetime import datetime

from ultralytics import YOLO

SUNUCU = "http://127.0.0.1:8000/api/olay"
ESIK = 0.5


def olay_gonder(olay):
    istek = urllib.request.Request(SUNUCU, json.dumps(olay).encode(), {"Content-Type": "application/json"})
    urllib.request.urlopen(istek, timeout=2)


model = YOLO("yolo11n.pt")
for kare_no, sonuc in enumerate(model(source=0, stream=True, classes=[0])):  # 0 = person
    for i, (kutu, guven) in enumerate(zip(sonuc.boxes.xywhn.tolist(), sonuc.boxes.conf.tolist())):
        if guven < ESIK:
            continue
        x, y, w, h = kutu  # YOLO merkez veriyor, şema sol üst köşe istiyor
        olay_gonder({
            "olay_id": f"kam1-{kare_no}-{i}",
            "kaynak": "kamera",
            "etiket": "insan",
            "guven": round(guven, 3),
            "zaman": datetime.now().astimezone().isoformat(),
            "kutu": {"x": x - w / 2, "y": y - h / 2, "w": w, "h": h},
        })
```

Vuruş tespiti aynı uca gönderir: `"kaynak": "mikrofon"`, `"etiket": "vurus"`,
`kutu` yok.

Her karede istek atmak sorun değil; sunucu 3 saniye içindeki tekrarları
birleştirir.

### Mesh simülatörü: kaynak olarak takılır

Simülatör mesajları şifreli `paket` olarak üretir (`shared/README.md` içindeki
`paketle()` örneği). Sunucuya bağlamak için `server/sources/base.py`'deki
`Kaynak` sınıfını uygulayan bir `server/sources/simulator.py` yazılır ve
`server/main.py` içindeki `KAYNAKLAR` sözlüğüne eklenir:

```python
from server.sources.base import Kaynak


class SimulatorKaynak(Kaynak):
    def __init__(self, psk: bytes):
        ...

    async def calistir(self, olay, paket, sinyal):
        while True:
            ...
            await paket(uretilen_paket)    # models.Paket
            await sinyal(uretilen_sinyal)  # models.Sinyal
```

Örnek uygulama: `server/sources/mock.py`.

### İnşaat: sığınak dosyası

`data/siginaklar.geojson` dosyasını `siginak` şemasına uygun GeoJSON ile
değiştirin; sunucu açılışta okur ve doğrular. QGIS'ten "GeoJSON, EPSG:4326"
olarak dışa aktarılan dosya uyar. Şu anki dosyadaki 5 sığınak örnektir,
hepsi `kaynak: "tahmin"`.

## Ölçüm

Olayın `POST /api/olay` ile gönderilmesinden WebSocket istemcisine ulaşmasına
kadar geçen süre:

```bash
.venv/bin/python -m server.main --kaynak mock &
.venv/bin/python scripts/gecikme_olc.py --adet 500
```

29.10.2026 tarihli ölçüm, AMD Ryzen 5 5600H, Python 3.14, sunucu ve istemci
aynı makinede, 500 olay:

| Durum | Ortalama | Medyan | p95 | En yüksek |
|---|---|---|---|---|
| `--kaynak yok` | 3,05 ms | 3,20 ms | 3,67 ms | 6,14 ms |
| `--kaynak mock` | 3,06 ms | 3,18 ms | 3,57 ms | 6,20 ms |

Süre HTTP isteğini de içerir; istemci tarayıcı değil Python betiğidir.
