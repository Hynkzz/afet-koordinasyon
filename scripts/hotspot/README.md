# Wi-Fi erişim noktası ve portal penceresi (isteğe bağlı)

Laptopun Wi-Fi kartı şifresiz `AFET-ACIL-YARDIM` ağını yayınlar. Telefon bu
ağa bağlanınca internet olmadığını fark eder ve portal penceresini kendiliğinden
açar; kullanıcının adres yazması gerekmez.

Demo için şart değil: aynı Wi-Fi ağındaki bir telefon paneldeki **Portal QR**
kodunu okutarak da portala ulaşır.

## Gerekenler

- Erişim noktası (AP) modunu destekleyen Wi-Fi kartı: `iw list` çıktısında
  "Supported interface modes" altında `AP` olmalı.
- `hostapd`, `dnsmasq`, `iptables` (Fedora: `sudo dnf install hostapd`; diğer
  ikisi genelde kurulu).
- sudo yetkisi.

Betik çalışırken laptopun normal Wi-Fi bağlantısı kopar; kart aynı anda hem
istemci hem erişim noktası olamaz. Kapatınca (Ctrl+C) ayarlar geri alınır.

## Çalıştırma

```bash
# 1. terminal: ağı aç (arayüz adı: iw dev)
sudo scripts/hotspot/kur.sh wlp3s0

# 2. terminal: sunucu tüm arayüzlerden dinlesin
AFET_PORTAL_ADRES=http://10.42.0.1/portal .venv/bin/python -m server.main --host 0.0.0.0 --kaynak mock
```

## Nasıl çalışıyor

| Parça | Görevi |
|---|---|
| hostapd | Şifresiz Wi-Fi ağını yayınlar |
| dnsmasq | Telefona IP verir (10.42.0.10–250); her alan adını 10.42.0.1'e çözer; DHCP 114 seçeneğiyle portal adresini bildirir |
| iptables | 80. porta gelen istekleri sunucunun 8000. portuna yönlendirir |
| Sunucu | Telefonların bağlantı kontrolü için yokladığı adreslere (`/generate_204`, `/hotspot-detect.html`, `/connecttest.txt` …) `/portal`'a yönlendirme döner; telefon bunu görünce portal penceresini açar |

## Sınırlar

- HTTPS istekleri yönlendirilemez (sertifika uyarısı çıkar); telefonlar bağlantı
  kontrolünü HTTP ile yaptığı için portal penceresi yine açılır.
- Bazı telefonlar "internet yok" ağından kendiliğinden ayrılabilir; kullanıcı
  "bu ağda kal" demeli.
- Betik bu makinede sözdizimi açısından denendi; gerçek erişim noktası ve telefonla
  henüz denenmedi.
