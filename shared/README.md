# Ortak Veri Formatları

Bu klasör, bölümlerin bilgisayar paneline gönderdiği verinin biçimini tanımlar.
Her dosya bir JSON Schema'dır (draft 2020-12). Gönderdiğiniz JSON bu şemaya
uymuyorsa sunucu reddeder ve sebebini döner.

| Dosya | Kim gönderir | Ne zaman |
|---|---|---|
| `olay.schema.json` | Yapay zekâ | Kamera insan, mikrofon vuruş tespit ettiğinde |
| `paket.schema.json` | Haberleşme | Mesh ağından mesaj geldiğinde (şifreli hali) |
| `mesaj.schema.json` | — | Paketin çözülmüş hali; panel bunu gösterir |
| `sinyal.schema.json` | Haberleşme | Düğüm bağlantı ölçümü güncellendiğinde |
| `siginak.schema.json` | İnşaat | Bir kez, dosya olarak (`data/siginaklar.geojson`) |
| `dugum.schema.json` | EEE + İnşaat | Bir kez, dosya olarak (`data/dugumler.geojson`) |

Genel kurallar:
- Alan adları Türkçe karaktersiz ve küçük harf.
- Zaman ISO 8601, saat dilimiyle: `2026-10-29T14:03:12.481+03:00`.
- Şemada olmayan alan eklemeyin; reddedilir. Yeni alan gerekiyorsa önce şemayı birlikte güncelleyelim.

## Olay (yapay zekâ → bilgisayar)

| Alan | Tür | Zorunlu | Açıklama |
|---|---|---|---|
| `olay_id` | metin | evet | Sizin ürettiğiniz tekil kimlik, ör. `kam1-000123` |
| `kaynak` | `"kamera"` / `"mikrofon"` | evet | |
| `etiket` | `"insan"` / `"vurus"` | evet | |
| `guven` | sayı, 0–1 | evet | Modelin güven skoru |
| `zaman` | ISO 8601 | evet | Tespit anı |
| `kutu` | `{x, y, w, h}` | hayır | Sadece `insan` için. Değerler görüntü boyutuna oranlı (0–1), `x, y` sol üst köşe. Vuruş olayında gönderilmez. |

Kutu oranlı, çünkü panel görüntüyü farklı boyutta çizebilir. YOLO'da
`xywhn` çıktısı merkez noktası verir; sol üst köşe için `x - w/2`, `y - h/2` alın.

```json
{"olay_id": "kam1-000123", "kaynak": "kamera", "etiket": "insan", "guven": 0.87,
 "zaman": "2026-10-29T14:03:12.481+03:00", "kutu": {"x": 0.42, "y": 0.31, "w": 0.12, "h": 0.35}}
```
```json
{"olay_id": "mik1-000045", "kaynak": "mikrofon", "etiket": "vurus", "guven": 0.64,
 "zaman": "2026-10-29T14:03:15.020+03:00"}
```

## Mesaj (haberleşme → bilgisayar)

| Alan | Tür | Zorunlu | Açıklama |
|---|---|---|---|
| `id` | metin | evet | Tekil mesaj kimliği, ör. `d3-000017` |
| `tur` | `"SOS"` / `"hazir_mesaj"` / `"ack"` | evet | |
| `kaynak` | metin | evet | Gönderen düğüm |
| `hedef` | metin | evet | Alıcı düğüm; `"*"` herkese |
| `ttl` | tam sayı, 0–16 | evet | Kalan atlama sayısı, her aktarımda 1 azalır |
| `yuk` | metin, en fazla 200 karakter | evet | Mesaj metni. `ack` için onaylanan mesajın `id`'si |
| `gps` | `{lat, lon}` | hayır | Ondalık derece |
| `sayac` | tam sayı ≥ 0 | evet | Her kaynak için her mesajda artar. Aynı veya küçük sayaç gelirse mesaj tekrar sayılıp reddedilir |
| `imza` | base64, 24 karakter | evet | ChaCha20-Poly1305 doğrulama etiketi (16 bayt) |

```json
{"id": "d3-000017", "tur": "SOS", "kaynak": "d3", "hedef": "merkez", "ttl": 5,
 "yuk": "Enkaz altindayim", "gps": {"lat": 39.8195, "lon": 34.8080},
 "sayac": 17, "imza": "q8fH2k1Zb7Xw0pLmN4sT9A=="}
```
```json
{"id": "merkez-000002", "tur": "ack", "kaynak": "merkez", "hedef": "d3", "ttl": 5,
 "yuk": "d3-000017", "sayac": 2, "imza": "Zm9vYmFyYmF6cXV4MTIzNA=="}
```

## Paket: mesajın ağdaki şifreli hali

Simülatör sunucuya `mesaj` değil `paket` gönderir. Başlık açık kalır ki ara
düğümler `hedef`/`ttl`'e bakıp yönlendirebilsin; metin ve konum şifrelidir.

| Alan | Açıklama |
|---|---|
| `id`, `tur`, `kaynak`, `hedef`, `ttl`, `sayac` | Mesajdakiyle aynı, açık |
| `sifreli` | `{"yuk": "...", "gps": {...}}` JSON'unun ChaCha20 ile şifrelenmiş hali, base64. JSON UTF-8 yazılır (`ensure_ascii=False`); Türkçe harf kaçış dizisi olunca 3 kat yer kaplar |
| `imza` | Poly1305 etiketi, base64 |

Şifreleme kuralları (sunucudaki `server/crypto.py` ile aynı olmalı):
- Anahtar: ortak 32 baytlık PSK (`.env` içindeki `AFET_PSK`, base64).
- Nonce (12 bayt): `sha256(kaynak)` ilk 4 bayt + `sayac` 8 bayt big-endian.
  Kaynak eklenir çünkü tüm düğümler aynı anahtarı kullanıyor; iki düğümün
  aynı sayacı aynı nonce'u üretmesin.
- Ek doğrulanan veri (AAD): `[id, tur, kaynak, hedef, sayac]` listesinin
  boşluksuz JSON'u (`json.dumps(..., separators=(",", ":"))`). `ttl` dahil
  değil; ara düğümler onu değiştiriyor.
- Başlıktan biri değişirse veya şifreli kısım bozulursa paket reddedilir.

Örnek Python:
```python
import base64, hashlib, json
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

def paketle(psk, id, tur, kaynak, hedef, ttl, sayac, yuk, gps=None):
    nonce = hashlib.sha256(kaynak.encode()).digest()[:4] + sayac.to_bytes(8, "big")
    aad = json.dumps([id, tur, kaynak, hedef, sayac], separators=(",", ":")).encode()
    acik = {"yuk": yuk, **({"gps": gps} if gps else {})}
    cikti = ChaCha20Poly1305(psk).encrypt(nonce, json.dumps(acik, ensure_ascii=False).encode(), aad)
    return {"id": id, "tur": tur, "kaynak": kaynak, "hedef": hedef, "ttl": ttl, "sayac": sayac,
            "sifreli": base64.b64encode(cikti[:-16]).decode(), "imza": base64.b64encode(cikti[-16:]).decode()}
```

## Sinyal (haberleşme → bilgisayar)

| Alan | Tür | Zorunlu | Açıklama |
|---|---|---|---|
| `dugum_id` | metin | evet | |
| `rssi` | sayı, −120–0 | evet | dBm |
| `paket_alim_orani` | sayı, 0–1 | evet | Son ölçüm penceresinde alınan / gönderilen paket |
| `zaman` | ISO 8601 | evet | |

```json
{"dugum_id": "d3", "rssi": -71, "paket_alim_orani": 0.92, "zaman": "2026-10-29T14:03:10+03:00"}
```

## Sığınak (inşaat → bilgisayar)

Standart GeoJSON `FeatureCollection`. Her Feature bir `Point`; koordinat
sırası **[boylam, enlem]** (GeoJSON kuralı, `gps` alanının tersi).
QGIS'ten "GeoJSON, EPSG:4326" olarak dışa aktarılan dosya uyar.

| `properties` alanı | Tür | Açıklama |
|---|---|---|
| `ad` | metin | |
| `kapasite` | tam sayı ≥ 0 | Kişi |
| `kaynak` | `"AFAD"` / `"OSM"` / `"tahmin"` | Verinin nereden geldiği |

`properties` içine başka alan ekleyebilirsiniz, panel görmezden gelir.

```json
{"type": "FeatureCollection", "features": [
  {"type": "Feature", "geometry": {"type": "Point", "coordinates": [34.8080, 39.8195]},
   "properties": {"ad": "Ornek Park Toplanma Alani", "kapasite": 1200, "kaynak": "AFAD"}}
]}
```

## Düğüm ve sensör yerleşimi (EEE + İnşaat → bilgisayar)

Mesh düğümlerinin, kameranın ve mikrofonun nerede olduğu. Panel haritada
düğümleri ve kapsama dairelerini çizer; kamera ve mikrofon olaylarını sensörün
konumuna koyar. GeoJSON `FeatureCollection`, her Feature bir `Point`.

| `properties` alanı | Tür | Açıklama |
|---|---|---|
| `id` | metin | Düğümde `sinyal` mesajlarındaki `dugum_id` ile aynı (`d1`…) |
| `tur` | `"dugum"` / `"kamera"` / `"mikrofon"` | |
| `menzil_m` | sayı | Yalnızca düğüm: kapsama yarıçapı, metre (bağlantı bütçesinden) |
| `kaynak` | `"olcum"` / `"hesap"` / `"tahmin"` | Değer nereden geliyor |

```json
{"type": "FeatureCollection", "features": [
  {"type": "Feature", "geometry": {"type": "Point", "coordinates": [34.8085, 39.8188]},
   "properties": {"id": "d1", "tur": "dugum", "menzil_m": 80, "kaynak": "hesap"}}
]}
```

Şu anki `data/dugumler.geojson` örnektir: konumlar ve 80 m menzil tahmin.

## Kendi verinizi kontrol etmek

```bash
pip install jsonschema
python -c "import json,jsonschema; jsonschema.validate(json.load(open('ornek.json')), json.load(open('shared/olay.schema.json')))"
```
Hata yoksa çıktı boştur.
