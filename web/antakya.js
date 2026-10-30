"use strict";

const renk = Object.fromEntries(
  ["yazi-3", "notr", "kritik", "uyari"].map((ad) => [ad, getComputedStyle(document.documentElement).getPropertyValue("--" + ad).trim()])
);
const sayi = (x, basamak = 2) => x.toFixed(basamak).replace(".", ",");
const durum = { esik: 0.5, gorunum: "model", gizli: false };

const harita = L.map("harita", { maxZoom: 19, zoomSnap: 0.25, attributionControl: true });
harita.attributionControl.setPrefix("Leaflet");
// 4.700 cokgen SVG'de yavas; tek canvas'ta cizilir.
const tuval = L.canvas({ padding: 0.3 });
const goruntu = {};
let binalar;

function stil(f) {
  const { p, gercek } = f.properties;
  if (durum.gizli) return { stroke: false, fill: false };
  const isaretli = p >= durum.esik;
  if (durum.gorunum === "model") {
    if (isaretli) return { color: renk.kritik, weight: 1.5, fillColor: renk.kritik, fillOpacity: 0.3 };
    if (p >= durum.esik / 2) return { color: renk.uyari, weight: 1, fill: false };
    return { color: renk.notr, weight: 0.5, opacity: 0.5, fill: false };
  }
  if (durum.gorunum === "gercek") {
    if (gercek === "yikik") return { color: renk.kritik, weight: 1.5, fillColor: renk.kritik, fillOpacity: 0.3 };
    if (gercek === "hasarsiz") return { color: renk.notr, weight: 0.5, opacity: 0.6, fill: false };
    return { color: renk["yazi-3"], weight: 0.5, opacity: 0.2, fill: false };
  }
  // Karsilastirma: yalniz etiketli binalar.
  if (gercek === null) return { stroke: false, fill: false };
  if (gercek === "yikik" && isaretli) return { color: renk.kritik, weight: 1.5, fillColor: renk.kritik, fillOpacity: 0.4 };
  if (gercek === "yikik") return { color: renk.uyari, weight: 2.5, fill: false };
  if (isaretli) return { color: renk.kritik, weight: 1.5, dashArray: "4 3", fill: false };
  return { color: renk.notr, weight: 0.5, opacity: 0.4, fill: false };
}

const LEJANT = {
  model: [
    [renk.kritik, 0.3, "solid", "İşaretli: olasılık ≥ eşik"],
    [renk.uyari, 0, "solid", "Şüpheli: eşiğin yarısı ile eşik arası"],
    [renk.notr, 0, "solid", "İşaretsiz"],
  ],
  gercek: [
    [renk.kritik, 0.3, "solid", "Yıkık (HOT/OSM, Copernicus)"],
    [renk.notr, 0, "solid", "Hasarsız (Copernicus)"],
  ],
  karsilastirma: [
    [renk.kritik, 0.4, "solid", "Doğru işaret: yıkık ve işaretli"],
    [renk.uyari, 0, "solid", "Kaçan: yıkık ama işaretsiz"],
    [renk.kritik, 0, "dashed", "Yanlış alarm: hasarsız ama işaretli"],
    [renk.notr, 0, "solid", "Doğru hasarsız"],
  ],
};

function lejantCiz() {
  document.getElementById("lejant").innerHTML = LEJANT[durum.gorunum]
    .map(([r, dolgu, cizgi, metin]) => {
      const zemin = dolgu ? `background:${r}${Math.round(dolgu * 255).toString(16).padStart(2, "0")};` : "";
      return `<li><i style="border:2px ${cizgi} ${r};${zemin}"></i>${metin}</li>`;
    })
    .join("");
}

function olc(ozellikler) {
  let dogru = 0, kacan = 0, yanlis = 0, isaret = 0;
  for (const { properties: { p, gercek } } of ozellikler) {
    const isaretli = p >= durum.esik;
    if (isaretli) isaret++;
    if (gercek === "yikik") isaretli ? dogru++ : kacan++;
    else if (gercek === "hasarsiz" && isaretli) yanlis++;
  }
  return { dogru, kacan, yanlis, isaret };
}

function guncelle() {
  document.getElementById("esik-deger").textContent = sayi(durum.esik);
  if (!binalar) return;
  binalar.setStyle(stil);
  const s = olc(binalar.toGeoJSON().features);
  const yikik = s.dogru + s.kacan;
  document.getElementById("s-dogru").textContent = `${s.dogru} / ${yikik} (%${sayi((100 * s.dogru) / yikik, 1)})`;
  document.getElementById("s-kacan").textContent = s.kacan;
  document.getElementById("s-yanlis").textContent = s.yanlis;
  document.getElementById("s-isaret").textContent = s.isaret;
  lejantCiz();
}

function popupMetni(f) {
  const { p, gercek } = f.properties;
  const g = { yikik: "Yıkık", hasarsiz: "Hasarsız" }[gercek] || "Etiket yok";
  return `<b>Hasar olasılığı: ${sayi(p)}</b><br>Gerçek etiket: ${g}<br>Bu eşikte: ${p >= durum.esik ? "İşaretli" : "İşaretsiz"}`;
}

function goruntuSec(ad) {
  for (const [k, katman] of Object.entries(goruntu)) {
    if (k === ad) katman.addTo(harita).bringToBack();
    else katman.remove();
  }
  document.querySelectorAll("#goruntu-sec button").forEach((b) => b.classList.toggle("secili", b.dataset.goruntu === ad));
}

Promise.all([fetch("demo/antakya_ozet.json").then((c) => c.json()), fetch("demo/antakya.geojson").then((c) => c.json())])
  .then(([ozet, veri]) => {
    durum.esik = ozet.esik;
    const esik = document.getElementById("esik");
    esik.value = ozet.esik;
    for (const ad of ["oncesi", "sonrasi"]) {
      goruntu[ad] = L.imageOverlay(`demo/${ad}.jpg`, ozet[ad].sinir, { attribution: "Maxar Open Data (CC BY-NC 4.0)" });
      const dugme = document.querySelector(`#goruntu-sec [data-goruntu="${ad}"]`);
      dugme.textContent = `${ad === "oncesi" ? "Deprem öncesi" : "Deprem sonrası"} (${ozet[ad].tarih.split("-").reverse().join(".")})`;
    }
    const sinir = L.latLngBounds(ozet.sonrasi.sinir);
    harita.fitBounds(sinir);
    harita.setMaxBounds(sinir.pad(0.2));
    harita.setMinZoom(harita.getZoom() - 1);
    goruntuSec("sonrasi");

    binalar = L.geoJSON(veri, { renderer: tuval, style: stil, onEachFeature: (f, k) => k.bindPopup(() => popupMetni(f)) }).addTo(harita);

    document.getElementById("s-auc").textContent = sayi(ozet.auc, 3);
    document.getElementById("olcum-alt").textContent = `etiketli ${ozet.etiketli.toLocaleString("tr-TR")} bina, ${ozet.etiketli_yikik} yıkık`;
    document.getElementById("model").textContent = `${ozet.bina.toLocaleString("tr-TR")} bina. ${ozet.model}.`;
    document.getElementById("kaynak").textContent = ozet.kaynak;
    guncelle();
  })
  .catch(() => {
    document.getElementById("model").textContent = "Demo verisi yüklenemedi (web/demo/).";
  });

document.getElementById("esik").addEventListener("input", (e) => {
  durum.esik = Number(e.target.value);
  guncelle();
});
document.getElementById("cizgi-gizle").addEventListener("change", (e) => {
  durum.gizli = e.target.checked;
  guncelle();
});
document.querySelectorAll("#gorunum-sec button").forEach((b) =>
  b.addEventListener("click", () => {
    durum.gorunum = b.dataset.gorunum;
    document.querySelectorAll("#gorunum-sec button").forEach((x) => x.classList.toggle("secili", x === b));
    guncelle();
  })
);
document.querySelectorAll("#goruntu-sec button").forEach((b) => b.addEventListener("click", () => goruntuSec(b.dataset.goruntu)));
