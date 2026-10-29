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
- Panel kütüphaneleri (Leaflet, protomaps-leaflet, Chart.js, qrcode-generator) `web/vendor/`
  altında, CDN yok. Harita `data/tiles/yozgat.pmtiles` dosyasından çizilir
  (Yozgat merkez, yaklaşık 15×13 km, zoom 0–15, 1,2 MB).

```
afet-projesi/
  shared/          ortak şemalar ve açıklamaları
  server/
    main.py        FastAPI, WebSocket, olay birleştirme
    models.py      pydantic modelleri (shared/ ile birebir)
    crypto.py      şifreleme ve tekrar koruması
    portal.py      afetzede portalı ve kötüye kullanım önlemleri
    llm.py         yerel LLM triyajı, durum raporu, kural tabanlı yedek
    db.py          vaka kuyruğu ve durum geçmişi (SQLite)
    kanal.py       msgpack kodlama, BLE / LoRa / uydu kanal simülasyonu
    senaryo.py     zaman çizelgeli senaryo oynatıcı
    sources/       veri kaynakları: base.py arayüz, mock.py sahte veri
  web/             panel (HTML, CSS, JS, vendor/)
  data/            örnek sığınaklar, düğüm yerleşimi, harita dosyası
  scenarios/       demo senaryoları
  olcumler/        ölçüm sonuçları
  scripts/         ölçüm, karo indirme, hotspot/ erişim noktası
  tests/
```

## Operatör kuyruğu

Olaylar panelinin **Kuyruk** sekmesi açık vakaları öncelik, sonra bekleme
süresine göre sıralar. Her vakanın durumu tek tıkla ilerler: Yeni → Ekip
yönlendirildi → Kurtarıldı. Değişiklik tüm açık panellere ve portaldaki takip
sayfasına yansır.

| Vaka | Öncelik |
|---|---|
| Vuruş (mikrofon) | 1: enkaz altında canlı biri |
| İnsan tespiti (kamera) | 2 |
| Mesh'ten gelen SOS | Mesaj metninden kural tabanlı triyaj (1 ya da 2) |
| Portal çağrısı | Triyaj sonucu (LLM ya da kural) |

Vakalar ve durum geçmişi `data/afet.db` (SQLite) dosyasında; sunucu yeniden
açılınca kaybolmaz. Temiz bir demo için sunucu kapalıyken bu dosyayı silin.
Sorgular milisaniye sürdüğü için ayrı iş parçacığına taşınmadı.

## Afetzede portalı

Telefonla açılan, JS gerektirmeyen yardım isteme sayfası: `http://<bilgisayar IP>:8000/portal`.

- **Adım 1:** Durum seçilir (Enkaz altındayım, Yaralı var, Güvendeyim, Başka
  bir durum). Seçildiği an kayıt açılır, panele düşer ve takip kodu verilir.
- **Adım 2 (isteğe bağlı):** Kişi sayısı, yaralı var mı, adres veya tarif,
  serbest mesaj, ad.
- **Takip:** `/portal/takip` sayfasında kodla durum görülür (yeni / ekip
  yönlendirildi / kurtarıldı); sayfa 30 saniyede bir yenilenir.
- Tarayıcı konumu düz HTTP'de alınamadığı için konum olarak erişim noktasının
  konumu kullanılır (`.env` içinde `AFET_AP_KONUM=enlem,boylam`).
- Panelde **Portal QR** düğmesi portal adresinin QR kodunu gösterir. Adres
  kendiliğinden bulunur; elle vermek için `AFET_PORTAL_ADRES`.

Kötüye kullanım önlemleri:

| Önlem | Davranış |
|---|---|
| Aynı cihazdan tekrar | 10 dakika içindeki yeni çağrı yeni kayıt açmaz, öncekini günceller (son durum geçerli, adet artar) |
| Operatör "Asılsız" işareti | Kayıt silinmez, üstü çizili görünür; o cihazın 1 saat içindeki yeni kayıtlarına "Önceden asılsız" etiketi eklenir; geri alınabilir |
| Uyarı metni | Adım 1'de tek satır |

Cihaz, erişim noktası bu makinedeyse MAC adresinden, değilse IP'den tanınır;
her ikisi de tuzlu karma olarak tutulur.

Telefonla denemek: sunucuyu `--host 0.0.0.0` ile açın, telefonu aynı Wi-Fi
ağına bağlayın, paneldeki QR kodu okutun. Telefonun portal penceresini
kendiliğinden açması için erişim noktası betiği:
[`scripts/hotspot/`](scripts/hotspot/README.md).

## Harita katmanları ve dışa aktarım

Haritanın sağ üstündeki katman düğmesiyle açılıp kapanır: sığınaklar, mesajlar
ve SOS, açık vakaların ısı haritası (öncelik 1 en ağır), düğümler (renk son
RSSI'ya göre), kapsama alanları (düğüm menzili), kamera ve mikrofon.
Düğüm ve sensör konumları `data/dugumler.geojson` dosyasından gelir
(biçim: `shared/dugum.schema.json`); şu anki konumlar ve 80 m menzil tahmin.
Kamera ve mikrofon olayları sensörün konumunda, GPS'siz SOS onu gönderen
düğümün konumunda gösterilir.

**Dışa aktar** düğmesi (`GET /api/disa-aktar`) tüm vakaları durumlarıyla
birlikte GeoJSON olarak indirir; QGIS'te açılabilir. Ad ve cihaz kimliği
dosyaya yazılmaz.

## Enerji simülasyonu

Sahte veri üreticisinde her düğümün pili zamanla azalır. İki mod var:

| Mod | Akım | Ölçüm aralığı | Bu akımla 2000 mAh pil |
|---|---|---|---|
| Düşük güç | 5 mA | 5 sn | 400 saat |
| Acil | 20 mA | 1 sn | 100 saat |

Kamera ya da mikrofon olayı gelince (kaynaktan ya da `POST /api/olay` ile)
tüm düğümler, bir düğümden SOS gelince o düğüm 2 dakika acil moda geçer.
Pili biten düğüm susar. Sinyal panelinde pil yüzdesi ve acil moddaki düğümler
görünür. Demoda görünsün diye simülasyon saati hızlandırılmıştır: 1 sn = 2 dk
(`AFET_ENERJI_HIZ`). 2000 mAh ve 5 mA 12 Ekim planındaki örnekten, 20 mA
tahmin; EEE'nin güç bütçesi gelince `server/sources/mock.py` güncellenecek.
Pil ömrü sütunu bu varsayımlardan hesaplandı, ölçüm değil.

## Senaryo oynatıcı

Demoda her seferinde aynı akışı göstermek için. Panelin üst çubuğunda senaryo
seçilir, **Senaryoyu başlat** ile oynatılır; ilerleme, süre ve o anki adımın
notu yanında görünür. **Kuyruğu temizle** işaretliyse başlamadan önce eski
vakalar ve portal kayıtları silinir (onay sorulur). Başlarken tüm kanallar
açılır; senaryo süresince sahte veri üreticisi kendi olay ve mesajlarını
durdurur, sinyal ve pil verisi akmaya devam eder.

Adımlar sunucunun normal yollarından geçer: olaylar birleştirilir, düğüm
mesajları şifrelenip çözülür, portal çağrıları triyaj ve kanal seçiminden geçer.

Örnek: `scenarios/yozgat-deprem.json` (3,5 dk; vuruş ve insan tespiti,
düğümlerden SOS, 4 portal çağrısı, BLE ve LoRa kopması). Biçim:
`shared/senaryo.schema.json`. Önerilen demo komutu:

```bash
.venv/bin/python -m server.main --kaynak mock --host 0.0.0.0
```

## Kanal simülasyonu

Her giden mesaj (paneldeki SOS ve hazır mesajlar, portal kayıtları) msgpack
ile kodlanır ve sırayla BLE (380 B), LoRa (200 B), uydu (340 B) kanallarından
ilk açık ve sığanından gönderilir. Panelde her mesajın yanında kanal ve boyut
görünür; **Kanallar** düğmeleriyle bir kanal elle çökertilip açılabilir.
Portal mesajı açık hiçbir kanala sığmıyorsa en geniş açık kanala sığacak kadar
sondan kırpılır ("kırpıldı"). Sınırlar simülasyon değeri: `server/kanal.py`.

Gerçek mesajlarla boyut ölçümü: `python -m scripts.boyut_olc`, sonuç
`olcumler/paket-boyutu-2026-10-29.md`.

## Yerel LLM (isteğe bağlı)

Afetzedenin serbest metni yerel bir dil modeliyle sınıflandırılır (kişi sayısı,
yaralı, sıkışma, öncelik 1–3, tek cümle özet) ve her 60 saniyede bir kısa durum
raporu yazılır. Model yoksa ya da hata verirse kural tabanlı yedek çalışır;
panelde hangi yöntemin kullanıldığı görünür.

[llama.cpp](https://github.com/ggml-org/llama.cpp/releases) ve bir GGUF model
dosyasını `~/llm/` altına koyun, sonra:

```bash
scripts/llm_baslat.sh gpu      # ya da cpu
```

`.env`:

```
AFET_LLM_ADRES=http://127.0.0.1:8080/v1
AFET_LLM_MODEL=qwen3-4b-instruct-2507-q4_k_m
```

OpenAI uyumlu her sunucu (Ollama dahil) çalışır. Ölçüm:
`python -m scripts.llm_olc`, sonuçlar `olcumler/` altında.

## Çevrimdışı çalışma

Çalışırken hiçbir dış adrese istek gitmez. İnternet yalnızca harita
dosyasını hazırlarken bir kez gerekir.

### Harita bölgesini değiştirmek

[pmtiles aracını](https://github.com/protomaps/go-pmtiles/releases) indirin,
sonra bölgenin sınırını (batı, güney, doğu, kuzey) ve zoom aralığını verin:

```bash
python scripts/karo_indir.py --bbox 34.72,39.75,34.90,39.87 --maxzoom 15 \
    --cikti data/tiles/yozgat.pmtiles --pmtiles ./pmtiles
```

Betik Protomaps'in günlük OSM tabanlı haritasından yalnızca bu dikdörtgeni
keser; OSM'nin karo sunucusuna istek atmaz. Başka bir bölge için
`web/app.js` içindeki `BOLGE` sınırını ve dosya adını da güncelleyin.

### İnternetsiz test

1. Sunucuyu açın: `.venv/bin/python -m server.main --kaynak mock`
2. İnterneti kapatın: Wi-Fi'ı kapatıp kabloyu çekin ya da Linux'ta
   `nmcli networking off` (geri açmak için `nmcli networking on`).
3. Tarayıcıda `http://localhost:8000` açın, sayfayı `Ctrl+Shift+R` ile
   önbelleksiz yenileyin.
4. Kontrol: harita koyu stille çizilir, paneller güncellenir, SOS çalışır.
   Geliştirici araçlarının (F12) Ağ sekmesinde `localhost` dışında istek
   olmamalı.

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
