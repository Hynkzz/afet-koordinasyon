#!/bin/bash
# Sifresiz "AFET-ACIL-YARDIM" Wi-Fi agi acar; baglanan telefon portal penceresini kendiliginden gorur.
# Kullanim: sudo scripts/hotspot/kur.sh [wifi-arayuzu]    (Ctrl+C ile kapanir, ayarlar geri alinir)
set -euo pipefail

ARAYUZ="${1:-wlp3s0}"
SSID="AFET-ACIL-YARDIM"
IP="10.42.0.1"
PORT=8000
GECICI="$(mktemp -d)"

[ "$(id -u)" -eq 0 ] || { echo "sudo ile calistirin"; exit 1; }
for arac in hostapd dnsmasq iptables; do
    command -v "$arac" >/dev/null || { echo "$arac kurulu degil (Fedora: sudo dnf install $arac)"; exit 1; }
done

temizle() {
    echo "Kapatiliyor..."
    kill "${HOSTAPD:-}" "${DNSMASQ:-}" 2>/dev/null || true
    iptables -t nat -D PREROUTING -i "$ARAYUZ" -p tcp --dport 80 -j REDIRECT --to-port "$PORT" 2>/dev/null || true
    ip addr flush dev "$ARAYUZ" || true
    command -v nmcli >/dev/null && nmcli device set "$ARAYUZ" managed yes || true
    rm -rf "$GECICI"
}
trap temizle EXIT

# NetworkManager arayuzu birakmazsa hostapd baslayamaz; bu arada normal Wi-Fi baglantisi kopar.
command -v nmcli >/dev/null && nmcli device set "$ARAYUZ" managed no
ip addr flush dev "$ARAYUZ"
ip addr add "$IP/24" dev "$ARAYUZ"
ip link set "$ARAYUZ" up

cat > "$GECICI/hostapd.conf" <<KONF
interface=$ARAYUZ
driver=nl80211
ssid=$SSID
hw_mode=g
channel=6
auth_algs=1
KONF

# address=/#/ : her alan adi bu makineye cozulur, telefonun baglanti kontrolu portala duser.
# dhcp-option=114 : RFC 8910 portal adresi; yeni Android ve iOS surumleri dogrudan bunu acar.
cat > "$GECICI/dnsmasq.conf" <<KONF
interface=$ARAYUZ
bind-interfaces
dhcp-range=10.42.0.10,10.42.0.250,12h
dhcp-option=3,$IP
dhcp-option=6,$IP
dhcp-option=114,http://$IP/portal
address=/#/$IP
no-resolv
KONF

# Telefon 80. porta gider, sunucu 8000'de; HTTPS yonlendirilmez, telefonlar kontrolu HTTP ile yapar.
iptables -t nat -A PREROUTING -i "$ARAYUZ" -p tcp --dport 80 -j REDIRECT --to-port "$PORT"

dnsmasq --conf-file="$GECICI/dnsmasq.conf" --keep-in-foreground --log-facility=- &
DNSMASQ=$!
hostapd "$GECICI/hostapd.conf" &
HOSTAPD=$!

echo "Ag acik: $SSID ($IP). Sunucuyu baska bir terminalde baslatin:"
echo "  AFET_PORTAL_ADRES=http://$IP/portal .venv/bin/python -m server.main --host 0.0.0.0 --kaynak mock"
wait
