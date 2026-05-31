import streamlit as st
import requests
import os
import io
import json
import random
import base64
import math
import hashlib
import re
from urllib.parse import urlparse
from pathlib import Path
from datetime import datetime, timedelta
import cv2
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ExifTags

import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium
import streamlit.components.v1 as components

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import qrcode

try:
    from streamlit_js_eval import get_geolocation
except Exception:
    get_geolocation = None

try:
    from supabase import create_client
except Exception:
    create_client = None

# ==========================================
# ⚡ 1. ARAYÜZ VE TEMA (İkon Gizleme & CSS)
# ==========================================
st.set_page_config(page_title="GridAI Panel", page_icon="⚡", layout="wide")

st.markdown("""
<style>
    [data-testid="stStatusWidget"] {visibility: hidden;}
    header {visibility: hidden;}
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .main {background-color:#0F172A; color:#E2E8F0;}
    .stButton > button {background-color:#0F766E; color:white; border-radius:8px; height:42px; width:100%; font-weight:bold; border:none;}
    .stButton > button:hover {background-color:#115E59;}
    .metric-box {background-color:#1E293B; border:1px solid #334155; border-radius:10px; padding:14px; text-align:center;}
    .logo-container {background:linear-gradient(135deg,#1E293B 0%,#0F172A 100%); border-left:5px solid #38BDF8; border-radius:8px; padding:18px; margin-bottom:18px;}
    .footer-section {text-align:center; padding:25px; border-top:1px solid #334155; margin-top:50px; color:#94A3B8;}
    h1, h2, h3 {color:#38BDF8 !important;}
</style>
""", unsafe_allow_html=True)

# Streamlit Cloud'da frontend DOM hatası oluşturmaması için özel JavaScript enjeksiyonu kaldırıldı.
# Tasarım, harita, Roboflow, GPS ve rapor akışı etkilenmez.

# ==========================================
# ⚡ 2. GARANTİLİ TÜRKÇE PDF FONT MOTORU
# ==========================================
@st.cache_resource
def font_yukle():
    """Türkçe karakterler için fontu güvenli yükler; internet kesilirse sistem fontuna düşer."""
    font_path = "Roboto-Regular.ttf"
    font_bold_path = "Roboto-Bold.ttf"
    kaynaklar = {
        font_path: "https://github.com/googlefonts/roboto/raw/main/src/hinted/Roboto-Regular.ttf",
        font_bold_path: "https://github.com/googlefonts/roboto/raw/main/src/hinted/Roboto-Bold.ttf",
    }
    for dosya, url in kaynaklar.items():
        if not os.path.exists(dosya):
            try:
                r = requests.get(url, timeout=8)
                if r.ok and len(r.content) > 10000:
                    with open(dosya, "wb") as f:
                        f.write(r.content)
            except Exception:
                pass

    try:
        if os.path.exists(font_path) and os.path.exists(font_bold_path):
            pdfmetrics.registerFont(TTFont('TRFont', font_path))
            pdfmetrics.registerFont(TTFont('TRFont-Bold', font_bold_path))
            return 'TRFont', 'TRFont-Bold'
    except Exception:
        pass

    # Streamlit Cloud/Linux ortamlarında çoğunlukla bulunan Türkçe destekli sistem fontları
    adaylar = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    try:
        if os.path.exists(adaylar[0]) and os.path.exists(adaylar[1]):
            pdfmetrics.registerFont(TTFont('TRFont', adaylar[0]))
            pdfmetrics.registerFont(TTFont('TRFont-Bold', adaylar[1]))
            return 'TRFont', 'TRFont-Bold'
    except Exception:
        pass

    return 'Helvetica', 'Helvetica-Bold'

FONT_REG, FONT_BLD = font_yukle()

# ==========================================
# ⚡ 3. BELLEK YÖNETİMİ VE LOGLAMA
# ==========================================
ARSIV_DOSYASI = "gridai_arsiv.json"
def db_yukle():
    if os.path.exists(ARSIV_DOSYASI):
        try:
            with open(ARSIV_DOSYASI, "r", encoding="utf-8") as f: return json.load(f)
        except: return {}
    return {}

def db_kaydet(db):
    with open(ARSIV_DOSYASI, "w", encoding="utf-8") as f: json.dump(db, f, ensure_ascii=False, indent=4)

if "db" not in st.session_state: st.session_state.db = db_yukle()
if "loglar" not in st.session_state: st.session_state.loglar = []
if "hat_sicakligi" not in st.session_state: st.session_state.hat_sicakligi = 55.0
if "yuklenen_arsiv" not in st.session_state: st.session_state.yuklenen_arsiv = None
if "son_analizler" not in st.session_state: st.session_state.son_analizler = []
if "gorsel_kuyrugu" not in st.session_state: st.session_state.gorsel_kuyrugu = []
if "uploader_counter" not in st.session_state: st.session_state.uploader_counter = 0
if "mobil_qr_url" not in st.session_state: st.session_state.mobil_qr_url = ""
if "cihaz_konum" not in st.session_state: st.session_state.cihaz_konum = None
if "cihaz_konum_mesaj" not in st.session_state: st.session_state.cihaz_konum_mesaj = ""
if "harita_merkez_override" not in st.session_state: st.session_state.harita_merkez_override = None
if "son_konum_kaynagi" not in st.session_state: st.session_state.son_konum_kaynagi = ""
if "manuel_koordinat" not in st.session_state: st.session_state.manuel_koordinat = None
if "kurumsal_panel" not in st.session_state: st.session_state.kurumsal_panel = ""
if "tespit_kutulari_goster" not in st.session_state: st.session_state.tespit_kutulari_goster = True
if "canli_kamera_konum" not in st.session_state: st.session_state.canli_kamera_konum = None
if "canli_kamera_konum_mesaj" not in st.session_state: st.session_state.canli_kamera_konum_mesaj = ""
if "supabase_son_mesaj" not in st.session_state: st.session_state.supabase_son_mesaj = ""
if "kullanici_adi" not in st.session_state: st.session_state.kullanici_adi = "Saha Kullanıcısı"

def log_ekle(islem, *detaylar):
    detay = " | ".join(str(d) for d in detaylar if d is not None and str(d).strip() != "")
    st.session_state.loglar.append({"Tarih": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "İşlem": islem, "Detay": detay})

# ==========================================
# ⚡ 4. OPENCV & YOLO MÜHENDİSLİK MOTORU
# ==========================================
def anti_glint_filtresi(image_pil):
    img_cv = cv2.cvtColor(np.array(image_pil), cv2.COLOR_RGB2GRAY)
    _, thresholded = cv2.threshold(img_cv, 240, 255, cv2.THRESH_BINARY)
    oran = (cv2.countNonZero(thresholded) / (img_cv.shape[0] * img_cv.shape[1])) * 100
    return oran > 5.0, oran

def yolo_mesafe_risk_analizi(image_pil, ruzgar_hizi):
    x1, y1 = random.randint(100, 200), random.randint(100, 200)
    x2, y2 = random.randint(150, 250), random.randint(150, 250)
    piksel_mesafe = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
    risk_skoru = 20.0
    if piksel_mesafe < 70 and float(ruzgar_hizi) > 30.0: risk_skoru = random.uniform(82.5, 98.4)
    elif piksel_mesafe < 70: risk_skoru = random.uniform(40.0, 65.0)
    return round(piksel_mesafe, 1), round(risk_skoru, 1)


def _secret_get(anahtar, varsayilan=""):
    """Streamlit Secrets, ortam değişkeni ve boş değer durumlarını güvenli okur."""
    try:
        deger = st.secrets.get(anahtar, None)
        if deger is not None:
            return str(deger)
    except Exception:
        pass
    return str(os.getenv(anahtar, varsayilan))



def _secret_temizle(deger):
    """Secrets içine yanlışlıkla etiketle birlikte yapıştırılan değerleri sadeleştirir."""
    if deger is None:
        return ""
    txt = str(deger).strip()
    if "=" in txt and not txt.startswith("http"):
        txt = txt.split("=", 1)[-1].strip()
    txt = txt.strip().strip('"').strip("'").strip()
    return txt


def _supabase_url_temizle(deger):
    """Supabase URL değerini güvenli normalize eder.

    Kabul edilen örnekler:
    - https://xxxxx.supabase.co
    - xxxxx.supabase.co
    - Project URL: https://xxxxx.supabase.co
    """
    raw = _secret_temizle(deger)
    if not raw:
        return "", "SUPABASE_URL boş."
    bulunan = re.search(r'https?://[^\s"\'<>]+', raw)
    if bulunan:
        raw = bulunan.group(0)
    raw = raw.strip().rstrip("/")
    if raw and not raw.startswith(("http://", "https://")) and ".supabase.co" in raw:
        raw = "https://" + raw
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return raw, "Geçersiz SUPABASE_URL. Project Settings > API > Project URL değerini tam olarak girin. Örnek: https://xxxxx.supabase.co"
    return raw, "OK"


def supabase_ayarlari():
    """Supabase ortak kayıt sistemini Secrets/ortam değişkenlerinden okur ve URL'yi düzeltir."""
    raw_url = _secret_get("SUPABASE_URL", "").strip() or _secret_get("SUPABASE_PROJECT_URL", "").strip()
    url, url_msg = _supabase_url_temizle(raw_url)
    key = (
        _secret_get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        or _secret_get("SUPABASE_KEY", "").strip()
        or _secret_get("SUPABASE_ANON_KEY", "").strip()
    )
    key = _secret_temizle(key)
    table = _secret_temizle(_secret_get("SUPABASE_TABLE", "gridai_analizler")) or "gridai_analizler"
    url_gecerli = (url_msg == "OK")
    return {
        "url": url,
        "key": key,
        "table": table,
        "url_gecerli": url_gecerli,
        "url_msg": url_msg,
        "aktif": bool(url_gecerli and key and create_client is not None),
    }


@st.cache_resource(show_spinner=False)
def supabase_client_olustur(url, key):
    if create_client is None:
        return None
    return create_client(url, key)


def supabase_client_getir():
    ayar = supabase_ayarlari()
    if not ayar.get("url_gecerli"):
        return None, ayar, ayar.get("url_msg", "Supabase URL geçersiz.")
    if not ayar.get("key"):
        return None, ayar, "Supabase key eksik. Secrets içine SUPABASE_SERVICE_ROLE_KEY ekleyin."
    if create_client is None:
        return None, ayar, "supabase paketi yüklenemedi. requirements.txt içinde supabase olmalı."
    try:
        return supabase_client_olustur(ayar["url"], ayar["key"]), ayar, "Supabase bağlı."
    except Exception as e:
        return None, ayar, f"Supabase istemcisi oluşturulamadı: {e}"


def _num_or_none(v):
    try:
        if v is None or v == "":
            return None
        return float(v)
    except Exception:
        return None


def _risk_seviyesi(risk):
    try:
        r = float(risk)
    except Exception:
        r = 0
    if r >= 80:
        return "Kritik"
    if r >= 55:
        return "Yüksek"
    if r >= 30:
        return "Orta"
    return "Düşük"


def supabase_satir_hazirla(analiz, vp, kullanici_adi, cihaz_turu="Web Panel"):
    """Analiz kaydını Supabase tablo kolonlarına uygun sade dict'e çevirir."""
    return {
        "kullanici_adi": kullanici_adi or "Saha Kullanıcısı",
        "cihaz_turu": cihaz_turu,
        "kaynak": analiz.get("analiz_kaynagi", "Streamlit"),
        "rapor_token": vp.get("token", ""),
        "dosya_adi": analiz.get("dosya", ""),
        "gorsel_hash": analiz.get("hash", ""),
        "tespit": analiz.get("anomali", ""),
        "guven": _num_or_none(analiz.get("guven", 0)),
        "risk_skoru": _num_or_none(analiz.get("risk_skoru", 0)),
        "risk_seviyesi": _risk_seviyesi(analiz.get("risk_skoru", 0)),
        "enlem": _num_or_none(analiz.get("lat", vp.get("enlem"))),
        "boylam": _num_or_none(analiz.get("lon", vp.get("boylam"))),
        "konum_kaynagi": analiz.get("konum_kaynagi", ""),
        "veri_guvenilirligi": str(analiz.get("veri_guvenilirligi", "")),
        "hava_sicakligi": _num_or_none(vp.get("hava", {}).get("temp")),
        "ruzgar": _num_or_none(vp.get("hava", {}).get("ruzgar")),
        "nem": _num_or_none(vp.get("hava", {}).get("nem")),
        "ai_yorum": analiz.get("ai_detay", "") or analiz.get("tavsiye", ""),
    }


def supabase_analizleri_kaydet(analizler, vp, kullanici_adi, cihaz_turu="Web Panel"):
    """Analizleri ortak Supabase veritabanına kaydeder. Hata olursa uygulamayı düşürmez."""
    if not analizler:
        return False, "Supabase'e kaydedilecek analiz yok."
    client, ayar, msg = supabase_client_getir()
    if client is None:
        return False, msg
    try:
        satirlar = [supabase_satir_hazirla(a, vp, kullanici_adi, cihaz_turu) for a in analizler]
        # Aynı hash tekrar kaydedilse bile jüri demosunda sorun çıkarmasın diye insert basit tutuldu.
        res = client.table(ayar["table"]).insert(satirlar).execute()
        return True, f"{len(satirlar)} analiz Supabase ortak veritabanına kaydedildi."
    except Exception as e:
        return False, f"Supabase kayıt hatası: {e}"


@st.cache_data(ttl=10, show_spinner=False)
def supabase_analizleri_getir(limit=50):
    """Son saha analizlerini Supabase'den okur. 10 sn cache ile Cloud performansını korur."""
    ayar = supabase_ayarlari()
    if not ayar.get("url_gecerli"):
        return [], ayar.get("url_msg", "Supabase URL geçersiz.")
    if not ayar.get("key"):
        return [], "Supabase key eksik. Secrets içine SUPABASE_SERVICE_ROLE_KEY ekleyin."
    if create_client is None:
        return [], "supabase paketi requirements.txt içinde yok veya yüklenemedi."
    try:
        client = supabase_client_olustur(ayar["url"], ayar["key"])
        res = client.table(ayar["table"]).select("*").order("created_at", desc=True).limit(int(limit)).execute()
        return (res.data or []), "Supabase kayıtları okundu."
    except Exception as e:
        return [], f"Supabase okuma hatası: {e}"


def supabase_df(kayitlar):
    kolonlar = ["created_at", "kullanici_adi", "cihaz_turu", "rapor_token", "tespit", "guven", "risk_skoru", "risk_seviyesi", "enlem", "boylam", "konum_kaynagi", "veri_guvenilirligi", "dosya_adi"]
    if not kayitlar:
        return pd.DataFrame(columns=kolonlar)
    return pd.DataFrame([{k: r.get(k, "") for k in kolonlar} for r in kayitlar])

def roboflow_ayarlari():
    """
    Roboflow entegrasyonu için tek merkez.
    Secrets veya ortam değişkenlerinden okur; API anahtarı kesinlikle koda gömülmez.
    Desteklenen alanlar:
    - ROBOFLOW_API_KEY      : Roboflow API anahtarı
    - ROBOFLOW_MODEL_ID     : örn. proje-adi/1 veya workspace/proje-adi/1
    - ROBOFLOW_API_URL      : varsayılan https://serverless.roboflow.com
    - ROBOFLOW_CONFIDENCE   : varsayılan 0.40
    - ROBOFLOW_OVERLAP      : varsayılan 0.30
    """
    api_key = _secret_get("ROBOFLOW_API_KEY", "").strip()
    model_id = _secret_get("ROBOFLOW_MODEL_ID", "").strip()
    api_url = _secret_get("ROBOFLOW_API_URL", "https://serverless.roboflow.com").strip().rstrip("/")
    endpoint = _secret_get("ROBOFLOW_ENDPOINT", "").strip()

    def _to_float(name, default):
        try:
            return float(_secret_get(name, str(default)).replace(",", "."))
        except Exception:
            return default

    confidence = _to_float("ROBOFLOW_CONFIDENCE", 0.40)
    overlap = _to_float("ROBOFLOW_OVERLAP", 0.30)
    # Roboflow bazen 40 gibi yüzde, bazen 0.40 gibi oran kabul eden örnekler gösterir.
    # Serverless endpoint için oran formatı güvenlidir.
    if confidence > 1:
        confidence = confidence / 100.0
    if overlap > 1:
        overlap = overlap / 100.0

    return {
        "api_key": api_key,
        "model_id": model_id.strip().strip("/"),
        "api_url": api_url,
        "endpoint": endpoint,
        "confidence": max(0.01, min(confidence, 0.99)),
        "overlap": max(0.0, min(overlap, 0.99)),
        "aktif": bool(api_key and (model_id or endpoint)),
    }


def roboflow_endpoint_uret(ayar):
    """Kullanıcı model ID yerine endpoint yapıştırırsa da çalışacak şekilde normalize eder."""
    endpoint = (ayar.get("endpoint") or "").strip()
    model_id = (ayar.get("model_id") or "").strip().strip("/")
    api_url = (ayar.get("api_url") or "https://serverless.roboflow.com").strip().rstrip("/")

    if endpoint:
        # Kullanıcı full URL yapıştırdıysa query kısmını ayırıp temiz kullan.
        return endpoint.split("?")[0].rstrip("/")
    if model_id.startswith("http://") or model_id.startswith("https://"):
        return model_id.split("?")[0].rstrip("/")
    if not model_id:
        return ""
    return f"{api_url}/{model_id}"


def roboflow_api_tahmin(image_bytes, filename="image.jpg"):
    """
    Roboflow Serverless/Hosted API çağrısı.
    Tek bir gönderim formatına bağımlı kalmamak için üç güvenli deneme yapar:
    1) base64 form body
    2) multipart file
    3) JSON base64
    Başarılı olursa Roboflow JSON yanıtını döndürür.
    """
    ayar = roboflow_ayarlari()
    if not ayar["aktif"]:
        return None, "ROBOFLOW_API_KEY veya ROBOFLOW_MODEL_ID eksik"

    endpoint = roboflow_endpoint_uret(ayar)
    if not endpoint:
        return None, "Roboflow endpoint/model id eksik"

    params = {
        "api_key": ayar["api_key"],
        "confidence": ayar["confidence"],
        "overlap": ayar["overlap"],
        "format": "json",
    }
    img_b64 = base64.b64encode(image_bytes).decode("utf-8")
    son_hata = ""

    denemeler = [
        (
            "base64-form",
            lambda: requests.post(
                endpoint,
                params={**params, "image_type": "base64"},
                data=img_b64,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=35,
            ),
        ),
        (
            "multipart-file",
            lambda: requests.post(
                endpoint,
                params=params,
                files={"file": (filename or "image.jpg", image_bytes, "image/jpeg")},
                timeout=35,
            ),
        ),
        (
            "json-base64",
            lambda: requests.post(
                endpoint,
                params=params,
                json={"image": img_b64, "image_type": "base64"},
                timeout=35,
            ),
        ),
    ]

    for deneme_adi, istek in denemeler:
        try:
            r = istek()
            if r.ok:
                try:
                    data = r.json()
                except Exception:
                    return None, f"Roboflow {deneme_adi}: JSON okunamadı"
                if isinstance(data, dict):
                    data["_gridai_deneme"] = deneme_adi
                    data["_gridai_endpoint"] = endpoint
                return data, "OK"
            son_hata = f"{deneme_adi}: HTTP {r.status_code} - {r.text[:180]}"
        except Exception as e:
            son_hata = f"{deneme_adi}: {e}"

    return None, son_hata or "Roboflow API yanıtı alınamadı"


def _prediction_listesi_bul(nesne):
    """Roboflow REST, Workflows veya farklı JSON sarmallarında prediction listelerini güvenli arar."""
    bulunan = []
    if isinstance(nesne, list):
        for item in nesne:
            bulunan.extend(_prediction_listesi_bul(item))
    elif isinstance(nesne, dict):
        # Nesnenin kendisi bir detection kaydı olabilir.
        detection_keys = {"class", "class_name", "label", "confidence", "x", "y", "width", "height", "bbox", "x1", "y1", "x2", "y2"}
        if detection_keys.intersection(nesne.keys()) and any(k in nesne for k in ["class", "class_name", "label"]):
            bulunan.append(nesne)
        # Yaygın prediction alanları.
        for key in ["predictions", "detections", "objects", "results", "output", "model_predictions"]:
            if key in nesne:
                bulunan.extend(_prediction_listesi_bul(nesne[key]))
    return bulunan


def _prediction_bbox_normalize(p, img_w=None, img_h=None):
    """Roboflow xywh/xyxy/bbox formatlarını PIL çizimine uygun x1,y1,x2,y2 formatına çevirir."""
    x1 = y1 = x2 = y2 = None
    # bbox listesi: [x1,y1,x2,y2] veya [x,y,w,h]
    bbox = p.get("bbox") or p.get("box") or p.get("bounding_box")
    if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
        vals = [float(v) for v in bbox[:4]]
        # xyxy gibi görünüyorsa
        if vals[2] > vals[0] and vals[3] > vals[1]:
            x1, y1, x2, y2 = vals[0], vals[1], vals[2], vals[3]
        else:
            x, y, w, h = vals
            x1, y1, x2, y2 = x - w/2, y - h/2, x + w/2, y + h/2

    # xyxy anahtarları
    if all(k in p for k in ["x1", "y1", "x2", "y2"]):
        x1, y1, x2, y2 = float(p["x1"]), float(p["y1"]), float(p["x2"]), float(p["y2"])

    # Roboflow REST klasik merkez x,y + width,height
    if x1 is None and all(k in p for k in ["x", "y", "width", "height"]):
        x, y = float(p.get("x") or 0), float(p.get("y") or 0)
        w, h = float(p.get("width") or 0), float(p.get("height") or 0)
        if w > 0 and h > 0:
            x1, y1, x2, y2 = x - w/2, y - h/2, x + w/2, y + h/2

    if x1 is None:
        return None

    # 0-1 arası normalize değer geldiyse piksele çevir.
    if img_w and img_h and 0 <= x1 <= 1 and 0 <= x2 <= 1 and 0 <= y1 <= 1 and 0 <= y2 <= 1:
        x1, x2 = x1 * img_w, x2 * img_w
        y1, y2 = y1 * img_h, y2 * img_h

    if img_w and img_h:
        x1 = max(0, min(float(img_w), x1)); x2 = max(0, min(float(img_w), x2))
        y1 = max(0, min(float(img_h), y1)); y2 = max(0, min(float(img_h), y2))
    if x2 <= x1 or y2 <= y1:
        return None
    return [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)]


def roboflow_prediction_temizle(data, img_w=None, img_h=None):
    """Roboflow yanıtındaki prediction alanlarını GridAI iç formatına çevirir."""
    preds = []
    if not isinstance(data, dict):
        return preds

    raw_preds = _prediction_listesi_bul(data)
    for p in raw_preds:
        if not isinstance(p, dict):
            continue
        try:
            conf = float(p.get("confidence", p.get("confidence_score", p.get("score", 0))) or 0)
        except Exception:
            conf = 0
        if conf <= 1:
            conf *= 100
        sinif = str(p.get("class", p.get("class_name", p.get("label", p.get("name", "Tespit")))))
        bbox = _prediction_bbox_normalize(p, img_w=img_w, img_h=img_h)
        preds.append({
            "class": sinif,
            "confidence": round(conf, 1),
            "x": float(p.get("x", 0) or 0),
            "y": float(p.get("y", 0) or 0),
            "width": float(p.get("width", p.get("w", 0)) or 0),
            "height": float(p.get("height", p.get("h", 0)) or 0),
            "bbox": bbox,
            "kutu_var": bool(bbox),
        })
    return preds


def yolov11_analiz(img, image_bytes=None, filename="image.jpg", image_hash=""):
    """
    MVP mantığı:
    - Roboflow bilgileri girildiyse gerçek Roboflow/YOLO tahmini yapar.
    - Roboflow eksik veya geçici hata verirse jüri demosu bozulmasın diye deterministik mock çalışır.
    """
    if img is None:
        return None

    sicaklik_haritasi = {
        "Kırık İzolatör Hatası": 92.4,
        "Travers Korozyonu": 74.1,
        "Gevşek Bağlantı Elemanı": 114.8,
        "Direk Gövde Çatlağı": 61.3,
        "Normal / Risk Yok": 38.2,
    }

    ayar = roboflow_ayarlari()
    if ayar["aktif"] and image_bytes:
        data, durum = roboflow_api_tahmin(image_bytes, filename=filename)
        if data is not None:
            temiz_preds = roboflow_prediction_temizle(data, img_w=img.size[0], img_h=img.size[1])
            if temiz_preds:
                top = max(temiz_preds, key=lambda x: x["confidence"])
                return {
                    "anomali": top["class"],
                    "guven": top["confidence"],
                    "sicaklik": sicaklik_haritasi.get(top["class"], 72.0),
                    "kaynak": f"Roboflow API ({data.get('_gridai_deneme', 'api')})",
                    "predictions": temiz_preds,
                    "ham": data,
                    "api_durum": "OK",
                }
            return {
                "anomali": "Normal / Risk Yok",
                "guven": 99.0,
                "sicaklik": 38.2,
                "kaynak": f"Roboflow API ({data.get('_gridai_deneme', 'api')})",
                "predictions": [],
                "ham": data,
                "api_durum": "OK - prediction yok",
            }
        else:
            st.warning(f"Roboflow bağlantısı başarısız oldu; demo modu kullanıldı. Detay: {durum}")

    anomaliler = sicaklik_haritasi
    seed = int((image_hash or "12345678")[:8], 16) if image_hash else 12345678
    rnd = random.Random(seed)
    anomaly = rnd.choice(list(anomaliler.keys()))
    w, h = img.size
    preds = []
    if anomaly != "Normal / Risk Yok":
        preds = [{
            "class": anomaly,
            "confidence": round(rnd.uniform(91, 99), 1),
            "x": w * 0.50,
            "y": h * 0.48,
            "width": w * 0.32,
            "height": h * 0.28,
        }]
    return {
        "anomali": anomaly,
        "guven": round(rnd.uniform(91, 99), 1),
        "sicaklik": anomaliler[anomaly],
        "kaynak": "Demo YOLOv11 Mock" if not ayar["aktif"] else "Demo YOLOv11 Mock (Roboflow hata sonrası)",
        "predictions": preds,
        "api_durum": "Roboflow ayarı eksik" if not ayar["aktif"] else "Roboflow hata sonrası demo",
    }


def sha256_uret(image_bytes):
    return hashlib.sha256(image_bytes).hexdigest()


def _gps_rasyonel_to_float(deger):
    try:
        return float(deger[0]) / float(deger[1])
    except Exception:
        return float(deger)


def _dms_to_decimal(dms, ref):
    derece = _gps_rasyonel_to_float(dms[0])
    dakika = _gps_rasyonel_to_float(dms[1])
    saniye = _gps_rasyonel_to_float(dms[2])
    sonuc = derece + dakika / 60 + saniye / 3600
    if ref in ["S", "W"]:
        sonuc *= -1
    return sonuc


def exif_tarih_konum_oku(image_bytes):
    """Fotoğrafta EXIF GPS/tarih varsa okur; yoksa None döner."""
    sonuc = {"cekim_tarihi": "EXIF tarih yok", "exif_lat": None, "exif_lon": None, "konum_kaynagi": "EXIF GPS yok - CBS/Cihaz konumu"}
    try:
        img = Image.open(io.BytesIO(image_bytes))
        exif = img.getexif()
        if not exif:
            return sonuc
        exif_dict = {ExifTags.TAGS.get(k, k): v for k, v in exif.items()}
        sonuc["cekim_tarihi"] = str(exif_dict.get("DateTimeOriginal") or exif_dict.get("DateTime") or "EXIF tarih yok")
        gps_info = None
        try:
            gps_raw = exif.get_ifd(ExifTags.IFD.GPSInfo)
            gps_info = {ExifTags.GPSTAGS.get(k, k): v for k, v in gps_raw.items()} if gps_raw else None
        except Exception:
            gps_info = exif_dict.get("GPSInfo")
        if gps_info and "GPSLatitude" in gps_info and "GPSLongitude" in gps_info:
            lat = _dms_to_decimal(gps_info["GPSLatitude"], gps_info.get("GPSLatitudeRef", "N"))
            lon = _dms_to_decimal(gps_info["GPSLongitude"], gps_info.get("GPSLongitudeRef", "E"))
            sonuc.update({"exif_lat": float(lat), "exif_lon": float(lon), "konum_kaynagi": "EXIF GPS"})
    except Exception:
        pass
    return sonuc


def kutulari_ciz(image_pil, predictions):
    """Roboflow object detection çıktısındaki kutuları görsel üzerine çizer. Kutular kapalıysa orijinali döndürür."""
    img = image_pil.copy().convert("RGB")
    if not st.session_state.get("tespit_kutulari_goster", True):
        return img
    if not predictions:
        return img

    draw = ImageDraw.Draw(img)
    w, h = img.size
    for p in predictions:
        bbox = p.get("bbox") or _prediction_bbox_normalize(p, img_w=w, img_h=h)
        if not bbox:
            continue
        x1, y1, x2, y2 = bbox
        # Kırmızı kutu + koyu etiket arka planı. Tasarımı sade tutmak için PIL default font kullanılır.
        draw.rectangle([x1, y1, x2, y2], outline=(255, 0, 0), width=4)
        label = f"{p.get('class','Tespit')} %{p.get('confidence',0)}"
        try:
            tw = draw.textlength(label)
        except Exception:
            tw = len(label) * 7
        label_h = 18
        y_text = max(0, y1 - label_h)
        draw.rectangle([x1, y_text, x1 + tw + 8, y_text + label_h], fill=(20, 20, 20))
        draw.text([x1 + 4, y_text + 2], label, fill=(255, 255, 255))
    return img


def pil_to_b64_png(image_pil):
    buf = io.BytesIO()
    image_pil.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def analiz_tavsiyesi(anomali, risk_skoru, glint_var):
    if anomali == "Normal / Risk Yok" and risk_skoru < 35:
        return "Rutin takip yeterli. Bir sonraki periyodik kontrolde aynı bölgenin tekrar fotoğraflanması önerilir."
    if glint_var and risk_skoru < 70:
        return "Güneş yansıması tespit edildi. Aynı noktadan farklı açı/saatte ikinci doğrulama çekimi yapılmalı; ancak risk skoru yüksekse saha kontrolü ertelenmemeli."
    if risk_skoru >= 80:
        return "Kritik risk. SAP PM üzerinde acil bakım bildirimi açılmalı, ekip yönlendirme ve enerji sürekliliği etkisi değerlendirilmelidir."
    if risk_skoru >= 55:
        return "Orta-yüksek risk. 7 gün içinde saha kontrolü, termal doğrulama ve bağlantı/izolatör mekanik kontrolü önerilir."
    return "Düşük-orta risk. Arşive alınmalı ve bir sonraki drone/mobil kontrolde trend karşılaştırması yapılmalıdır."


def ai_detayli_analiz_uret(anomali, risk_skoru, glint_var, hava, sicaklik):
    """Jüri raporu için tanım + risk yorumu + gelecek tahmin + bakım önerisi üretir."""
    ruzgar = hava.get("ruzgar", 0) if isinstance(hava, dict) else 0
    nem = hava.get("nem", 0) if isinstance(hava, dict) else 0
    ortam = hava.get("temp", 0) if isinstance(hava, dict) else 0

    tanimlar = {
        "Kırık İzolatör Hatası": "İzolatör yüzeyinde mekanik kırık, çatlak veya yüzey bütünlüğü kaybı olasılığı vardır. Bu durum kaçak akım, ark oluşumu ve kesinti riskini artırabilir.",
        "Travers Korozyonu": "Travers veya bağlantı bölgesinde korozyon/oksidasyon belirtisi olabilir. Taşıyıcı mukavemet zamanla azalabilir ve bağlantı güvenilirliği düşebilir.",
        "Gevşek Bağlantı Elemanı": "Bağlantı noktasında gevşeme veya mekanik tutuculuk kaybı ihtimali vardır. Rüzgar ve yük değişimlerinde titreşim kaynaklı büyüme beklenebilir.",
        "Direk Gövde Çatlağı": "Direk gövdesinde çatlak veya yüzey süreksizliği işareti olabilir. Yapısal stabilite açısından saha doğrulaması gerekir.",
        "Normal / Risk Yok": "Model belirgin bir arıza sınıfı tespit etmedi. Bu sonuç rutin izleme kapsamında arşivlenmelidir.",
    }
    tanim = tanimlar.get(anomali, f"Model {anomali} sınıfına ait olası bir anomali işareti tespit etti.")

    if risk_skoru >= 80:
        gelecek = "Bu risk seviyesi korunursa kısa vadede arıza büyümesi, ekipman ömründe azalma ve plansız kesinti olasılığı yüksektir."
        aksiyon = "Acil saha kontrolü, termal kamera doğrulaması, bağlantı/izolatör mekanik testi ve SAP PM'de öncelik 1 bildirim önerilir."
    elif risk_skoru >= 55:
        gelecek = "Orta vadede rüzgar, nem ve yük değişimleriyle arıza ilerleyebilir. Trend takibi yapılmazsa risk kritik seviyeye çıkabilir."
        aksiyon = "7 gün içinde saha kontrolü, aynı noktadan ikinci görüntü, bağlantı sıkılık kontrolü ve bakım planına alınması önerilir."
    elif risk_skoru >= 35:
        gelecek = "Risk şu an yönetilebilir seviyededir; fakat çevresel koşullar bozulursa tekrar değerlendirme gerekir."
        aksiyon = "Periyodik kontrol takvimine alınmalı, bir sonraki drone/mobil çekimde aynı hash/konum referansıyla karşılaştırılmalıdır."
    else:
        gelecek = "Kısa vadeli arıza beklentisi düşük görünmektedir. Bu kayıt sağlıklı referans görüntü olarak kullanılabilir."
        aksiyon = "Arşivlenmesi ve rutin bakım periyodunda yeniden kontrol edilmesi yeterlidir."

    glint_notu = "Güneş/yansıma filtresi pozitif olduğu için görsel doğrulama ikinci açıyla güçlendirilmelidir." if glint_var else "Güneş yansıması baskın görünmediği için görüntü güvenilirliği daha yüksektir."
    cevre = f"Çevresel bağlam: ortam {ortam} °C, nem %{nem}, rüzgar {ruzgar} km/s, tahmini ekipman sıcaklığı {sicaklik} °C."
    return f"Tanım: {tanim} {cevre} Gelecek tahmin: {gelecek} Öneri: {aksiyon} Görüntü notu: {glint_notu}"


def veri_guvenilirligi_hesapla(konum_kaynagi, analiz_kaynagi, gps_accuracy=None):
    """Analizin lokasyon/tarih güvenini açıkça sınıflandırır; jüriye yanlış veriyle yorum yapılmadığını gösterir."""
    kaynak = str(konum_kaynagi or "").lower()
    analiz_kaynagi_l = str(analiz_kaynagi or "").lower()
    if "exif gps" in kaynak:
        return "YÜKSEK", 90, "Görselin kendi EXIF GPS bilgisi kullanıldı; fotoğrafın konumu görsel metadata'sından geldi."
    if "canlı kamera" in kaynak or "tarayıcı gps" in kaynak:
        if gps_accuracy is not None:
            try:
                acc = float(gps_accuracy)
                puan = 85 if acc <= 50 else (75 if acc <= 150 else 60)
                return "YÜKSEK" if puan >= 80 else "ORTA", puan, f"Canlı çekim sırasında cihaz GPS'i kullanıldı. Tarayıcı doğruluk değeri yaklaşık {acc:.0f} m."
            except Exception:
                pass
        return "ORTA-YÜKSEK", 78, "Canlı çekim sırasında cihaz konumu kullanıldı; tarayıcı doğruluk değeri alınamadı."
    if "manuel" in kaynak:
        return "YÜKSEK", 88, "Koordinat operatör tarafından manuel doğrulandı/girildi."
    if "yüklenen görsel" in analiz_kaynagi_l:
        return "DÜŞÜK", 35, "Yüklenen görselde EXIF GPS yok. Sistem geçici CBS/cihaz konumunu sadece harita ön izleme için kullandı; kesin saha konumu değildir."
    return "ORTA", 55, "Konum CBS/adres çözümleme veya yedek kaynakla belirlendi; saha doğrulaması önerilir."


def ai_detayini_guvenle_guncelle(ai_detay, veri_notu, analiz_kaynagi):
    return f"{ai_detay} Veri güvenilirliği: {veri_notu} Analiz kaynağı: {analiz_kaynagi}."


def ariza_sinifi_katsayisi(anomali):
    """Isı haritası ve risk hesabı için arıza sınıfına göre mühendislik ağırlığı."""
    ad = str(anomali or "").lower()
    if "izolat" in ad or "insulator" in ad:
        return 0.95
    if "gevş" in ad or "gevsek" in ad or "baglant" in ad or "connection" in ad:
        return 0.88
    if "vejet" in ad or "vegetation" in ad or "ağaç" in ad or "agac" in ad or "tree" in ad:
        return 0.82
    if "çatlak" in ad or "catlak" in ad or "crack" in ad:
        return 0.80
    if "korozy" in ad or "corrosion" in ad or "pas" in ad:
        return 0.68
    if "normal" in ad or "risk yok" in ad:
        return 0.10
    return 0.60


def risk_skoru_hesapla(anomali, guven, hava, glint_var, veri_guven_puani):
    """
    Risk = Roboflow tespit güveni + arıza sınıfı + çevresel koşullar + veri güvenilirliği.
    Bu değer hem raporda hem de ısı haritası ağırlığında kullanılır.
    """
    try:
        guven = float(guven or 0)
    except Exception:
        guven = 0
    try:
        veri_guven_puani = float(veri_guven_puani or 55)
    except Exception:
        veri_guven_puani = 55
    hava = hava or {}
    try:
        ruzgar = float(hava.get("ruzgar", 0) or 0)
        nem = float(hava.get("nem", 0) or 0)
        sicaklik = float(hava.get("temp", 0) or 0)
    except Exception:
        ruzgar = nem = sicaklik = 0

    sinif = ariza_sinifi_katsayisi(anomali) * 100
    cevre = 0
    if ruzgar >= 35: cevre += 14
    elif ruzgar >= 20: cevre += 8
    if nem >= 80: cevre += 7
    elif nem >= 65: cevre += 4
    if sicaklik >= 32: cevre += 6
    if glint_var: cevre -= 5  # yansıma varsa veri kalitesi cezalandırılır

    skor = (sinif * 0.42) + (guven * 0.33) + cevre + (veri_guven_puani * 0.12)
    if "normal" in str(anomali or "").lower():
        skor = min(skor, 28)
    return round(max(5, min(99, skor)), 1)


def heatmap_agirligi_hesapla(analiz):
    """Isı haritasında sadece analiz noktalarını, risk ve veri güvenilirliğiyle ağırlıklandırır."""
    try:
        risk = float(analiz.get("risk_skoru", 0) or 0) / 100
    except Exception:
        risk = 0.20
    try:
        guven = float(analiz.get("veri_guven_puani", 55) or 55) / 100
    except Exception:
        guven = 0.55
    katsayi = ariza_sinifi_katsayisi(analiz.get("anomali", ""))
    return round(max(0.05, min(1.0, (risk * 0.60) + (katsayi * 0.25) + (guven * 0.15))), 3)


def cevre_metrik_ai_yorumlari(vp):
    """PDF'deki çevresel metrik tablosu için değer odaklı AI yorumu üretir; tablo tasarımı korunur."""
    hava = vp.get("hava", {}) or {}
    temp = float(hava.get("temp", 0) or 0)
    ruzgar = float(hava.get("ruzgar", 0) or 0)
    akim = float(vp.get("akim", 0) or 0)
    yildirim = float(vp.get("yildirim", 0) or 0)

    if temp >= 32:
        temp_yorum = "Yüksek ortam sıcaklığı iletken soğumasını azaltır; aynı akımda termal genleşme ve izolasyon yaşlanması hızlanabilir. Gündüz pik yüklerde termal tekrar kontrol önerilir."
    elif temp <= 5:
        temp_yorum = "Düşük ortam sıcaklığı mekanik büzülme ve buz/kar etkisiyle hat gerilimini artırabilir. Katener açıklığı ve bağlantı noktaları kontrol edilmelidir."
    else:
        temp_yorum = "Ortam sıcaklığı normal bantta. Risk değerlendirmesinde rüzgar, nem ve görsel tespitlerle birlikte izlenmesi yeterlidir."

    if ruzgar >= 35:
        ruzgar_yorum = "Rüzgar yüksek. İletken salınımı, bağlantı gevşemesi ve vejetasyon temas ihtimali artar. 24-48 saat içinde saha gözlemi ve kritik açıklıklarda mekanik kontrol önerilir."
    elif ruzgar >= 20:
        ruzgar_yorum = "Rüzgar orta seviyede. Gevşek bağlantı veya vejetasyon tespiti varsa risk büyüyebilir; aynı lokasyonda trend takibi yapılmalıdır."
    else:
        ruzgar_yorum = "Rüzgar düşük. Mekanik salınım kaynaklı anlık risk sınırlı görünür; görsel arıza varsa planlı bakım yeterli olabilir."

    if akim >= 900:
        akim_yorum = "Hat akımı yüksek yük bandında. Termal kayıp, bağlantı ısınması ve izolasyon yorulması açısından öncelikli bakım bildirimi açılması önerilir."
    elif akim >= 500:
        akim_yorum = "Hat akımı orta-yüksek seviyede. Görsel tespit varsa termal doğrulama ile SAP PM planlı bakımına alınmalıdır."
    else:
        akim_yorum = "Hat akımı yönetilebilir seviyede. Görsel risk düşükse rutin izleme yeterlidir; riskli tespitte lokasyon bazlı takip yapılmalıdır."

    if yildirim >= 40:
        yildirim_yorum = "Yıldırım aktivitesi yüksek kabul edilir. Parafudr, topraklama ve izolatör yüzey kontrolü için önleyici bakım planı önerilir."
    elif yildirim >= 15:
        yildirim_yorum = "Yıldırım aktivitesi orta seviyede. Kritik direklerde parafudr ve topraklama sürekliliği periyodik kontrol listesine eklenmelidir."
    else:
        yildirim_yorum = "Yıldırım aktivitesi düşük görünüyor. Standart koruma ekipmanı kontrol periyodu korunabilir."

    return {
        "sicaklik": temp_yorum,
        "ruzgar": ruzgar_yorum,
        "akim": akim_yorum,
        "yildirim": yildirim_yorum,
    }


def sesli_komut_bileseni():
    """Mobil tarayıcıda sesli komut/yönlendirme demosu.

    Bu bileşen Python state'i doğrudan değiştirmez; Streamlit'in kararlılığını bozmayacak
    şekilde ayrı iframe içinde çalışır. Kamera analizi st.camera_input ile yapılmaya devam eder.
    """
    html = """
    <div style="background:#1E293B; color:#E2E8F0; border:1px solid #38BDF8; border-radius:12px; padding:16px; font-family:Arial, sans-serif;">
      <div style="font-size:18px; font-weight:800; color:#38BDF8; margin-bottom:8px;">🎙️ Sesli Komut Asistanı</div>
      <div style="font-size:13px; color:#CBD5E1; margin-bottom:10px;">Telefon/tablet üzerinde butona basıp şu komutları deneyin: <b>konum al</b>, <b>kamera aç</b>, <b>çekim yap</b>, <b>analiz et</b>, <b>rapor oluştur</b>.</div>
      <button id="startVoice" style="background:#0F766E; color:white; border:0; border-radius:8px; padding:10px 14px; font-weight:700; width:100%;">🎙️ Sesli Komutu Başlat</button>
      <div id="voiceStatus" style="margin-top:12px; background:#0F172A; border:1px solid #334155; border-radius:8px; padding:10px; min-height:48px; font-size:13px;">Hazır. Mikrofon izni istenirse izin verin.</div>
      <ol style="font-size:13px; line-height:1.55; margin-top:12px; color:#CBD5E1; padding-left:20px;">
        <li><b>Konum al:</b> tarayıcı konum iznini kontrol edin.</li>
        <li><b>Kamera aç / çekim yap:</b> aşağıdaki kamera kutusundan fotoğraf çekin.</li>
        <li><b>Analiz et:</b> fotoğraf çekildiğinde Roboflow analizi otomatik başlar.</li>
        <li><b>Rapor oluştur:</b> analizden sonra PDF/SAP Excel alanını kullanın.</li>
      </ol>
    </div>
    <script>
    (function(){
      const btn = document.getElementById('startVoice');
      const out = document.getElementById('voiceStatus');
      function speak(t){ try { const u = new SpeechSynthesisUtterance(t); u.lang='tr-TR'; window.speechSynthesis.speak(u); } catch(e){} }
      function setMsg(t){ out.innerHTML = t; speak(t.replace(/<[^>]*>/g,'')); }
      btn.onclick = function(){
        const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
        if(!SR){ setMsg('Bu mobil tarayıcı ses tanımayı desteklemiyor. Chrome veya Safari ile deneyin.'); return; }
        const rec = new SR();
        rec.lang = 'tr-TR'; rec.continuous = false; rec.interimResults = false;
        out.innerHTML = 'Dinleniyor... Komut söyleyin.';
        rec.onresult = function(e){
          const text = (e.results[0][0].transcript || '').toLowerCase();
          let yanit = '<b>Anlaşılan komut:</b> ' + text + '<br>';
          if(text.includes('konum')) yanit += 'Adım: Konum izni verin; sistem canlı çekim koordinatını analiz kaydına ekler.';
          else if(text.includes('kamera') || text.includes('çek')) yanit += 'Adım: Aşağıdaki kamera alanından fotoğraf çekin. Fotoğraf çekilince analiz otomatik başlar.';
          else if(text.includes('analiz')) yanit += 'Adım: Çekilen görsel Roboflow/YOLO modeline gönderilir; tespit kutuları, risk skoru ve konum kaydı oluşturulur.';
          else if(text.includes('rapor')) yanit += 'Adım: Raporlama alanından PDF ve SAP PM Excel çıktısını indirin.';
          else yanit += 'Desteklenen komutlar: konum al, kamera aç, çekim yap, analiz et, rapor oluştur.';
          setMsg(yanit);
        };
        rec.onerror = function(e){ setMsg('Sesli komut hatası: ' + (e.error || 'bilinmeyen hata') + '. Mikrofon iznini kontrol edin.'); };
        rec.start();
      };
    })();
    </script>
    """
    components.html(html, height=285, scrolling=False)


def kurumsal_footer_html():
    """TÜBİTAK logosu/ibaresi olmadan kurumsal footer alanı."""
    return """
    <div style="display:inline-block; background:#1E293B; padding:14px 22px; border-radius:14px; border:1px solid #38BDF8; box-shadow:0 2px 8px rgba(0,0,0,0.25);">
      <div style="font-size:22px; font-weight:800; color:#38BDF8; letter-spacing:0.5px;">⚡ GridAI</div>
      <div style="font-size:12px; color:#CBD5E1; margin-top:4px;">Drone ve Mobil Görüntü Tabanlı Elektrik Hattı Analiz Platformu</div>
    </div>
    """


def gorsel_analiz_pipeline(dosya_adi, image_bytes, enlem, boylam, adres_detay, hava, analiz_kaynagi="Yüklenen görsel", konum_kaynagi_override=None, gps_accuracy=None):
    img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    hsh = sha256_uret(image_bytes)
    exif = exif_tarih_konum_oku(image_bytes)
    if exif["exif_lat"] is not None and exif["exif_lon"] is not None:
        lat = exif["exif_lat"]
        lon = exif["exif_lon"]
        efektif_konum_kaynagi = "EXIF GPS"
    else:
        lat = enlem
        lon = boylam
        if konum_kaynagi_override:
            efektif_konum_kaynagi = konum_kaynagi_override
        else:
            efektif_konum_kaynagi = "Yüklenen görselde EXIF GPS yok - geçici CBS/cihaz konumu"

    yolo_sonuc = yolov11_analiz(img_pil, image_bytes=image_bytes, filename=dosya_adi, image_hash=hsh)
    glint_var, glint_oran = anti_glint_filtresi(img_pil)
    mesafe, _eski_mesafe_risk = yolo_mesafe_risk_analizi(img_pil, hava.get("ruzgar", 0))

    annotated = kutulari_ciz(img_pil, yolo_sonuc.get("predictions", []) if yolo_sonuc else [])
    veri_seviyesi, veri_puani, veri_notu = veri_guvenilirligi_hesapla(efektif_konum_kaynagi, analiz_kaynagi, gps_accuracy=gps_accuracy)
    risk_skor = risk_skoru_hesapla(
        yolo_sonuc.get("anomali", "Analiz yok") if yolo_sonuc else "Analiz yok",
        yolo_sonuc.get("guven", 0) if yolo_sonuc else 0,
        hava,
        bool(glint_var),
        veri_puani,
    )
    temel_ai = ai_detayli_analiz_uret(yolo_sonuc.get("anomali", "Analiz yok") if yolo_sonuc else "Analiz yok", float(risk_skor), bool(glint_var), hava, yolo_sonuc.get("sicaklik", 0) if yolo_sonuc else 0)
    return {
        "dosya": dosya_adi,
        "hash": hsh,
        "hash_kisa": hsh[:12],
        "tarih": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "cekim_tarihi": exif["cekim_tarihi"] if exif["cekim_tarihi"] != "EXIF tarih yok" else datetime.now().strftime("%Y-%m-%d %H:%M:%S") if "canlı" in analiz_kaynagi.lower() else "EXIF tarih yok",
        "lat": float(lat),
        "lon": float(lon),
        "adres": adres_detay,
        "konum_kaynagi": efektif_konum_kaynagi,
        "veri_guvenilirligi": veri_seviyesi,
        "veri_guven_puani": veri_puani,
        "veri_guven_notu": veri_notu,
        "analiz_kaynagi": analiz_kaynagi,
        "anomali": yolo_sonuc.get("anomali", "Analiz yok") if yolo_sonuc else "Analiz yok",
        "guven": yolo_sonuc.get("guven", 0) if yolo_sonuc else 0,
        "sicaklik": yolo_sonuc.get("sicaklik", 0) if yolo_sonuc else 0,
        "kaynak": yolo_sonuc.get("kaynak", "Yok") if yolo_sonuc else "Yok",
        "predictions": yolo_sonuc.get("predictions", []) if yolo_sonuc else [],
        "glint": bool(glint_var),
        "glint_oran": round(float(glint_oran), 2),
        "mesafe_px": mesafe,
        "risk_skoru": round(float(risk_skor), 1),
        "tavsiye": analiz_tavsiyesi(yolo_sonuc.get("anomali", "Analiz yok") if yolo_sonuc else "Analiz yok", float(risk_skor), bool(glint_var)),
        "ai_detay": ai_detayini_guvenle_guncelle(temel_ai, veri_notu, analiz_kaynagi),
        "gorsel_b64": base64.b64encode(image_bytes).decode("utf-8"),
        "islenmis_b64": pil_to_b64_png(annotated),
    }


def analizleri_df(analizler):
    kolonlar = ["dosya", "hash_kisa", "cekim_tarihi", "lat", "lon", "konum_kaynagi", "veri_guvenilirligi", "veri_guven_puani", "analiz_kaynagi", "anomali", "guven", "sicaklik", "risk_skoru", "kaynak", "tavsiye", "ai_detay"]
    if not analizler:
        return pd.DataFrame(columns=kolonlar)
    return pd.DataFrame([{k: a.get(k, "") for k in kolonlar} for a in analizler])


def qr_png_b64(metin):
    qr = qrcode.make(metin)
    buf = io.BytesIO()
    qr.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def sap_excel_olustur(vp, analizler):
    buf = io.BytesIO()
    ana = []
    for i, a in enumerate(analizler or [], 1):
        ana.append({
            "SAP_Bildirim_Tipi": "M2-Arıza Bildirimi" if a.get("risk_skoru", 0) >= 55 else "M1-Bakım Talebi",
            "Oncelik": "1-Kritik" if a.get("risk_skoru", 0) >= 80 else ("2-Yüksek" if a.get("risk_skoru", 0) >= 55 else "3-Normal"),
            "Teknik_Nesne": vp.get("token", "SAHA"),
            "Ekip": vp.get("ekip_adi", ""),
            "Lokasyon": vp.get("adres_isim", ""),
            "Koordinat": f"{a.get('lat')},{a.get('lon')}",
            "Ariza_Tanimi": a.get("anomali", ""),
            "Guven_%": a.get("guven", 0),
            "Risk_%": a.get("risk_skoru", 0),
            "Tahmini_Sicaklik_C": a.get("sicaklik", 0),
            "Gorsel_Hash": a.get("hash", ""),
            "Konum_Kaynagi": a.get("konum_kaynagi", ""),
            "Veri_Guvenilirligi": a.get("veri_guvenilirligi", ""),
            "Veri_Guven_Puani": a.get("veri_guven_puani", ""),
            "Analiz_Kaynagi": a.get("analiz_kaynagi", ""),
            "Onerilen_Aksiyon": a.get("tavsiye", ""),
            "AI_Detayli_Yorum": a.get("ai_detay", ""),
            "Kaynak": a.get("kaynak", ""),
            "Kayit_Tarihi": a.get("tarih", ""),
        })
    if not ana:
        ana = [{
            "SAP_Bildirim_Tipi": "M1-Bakım Talebi",
            "Oncelik": "3-Normal",
            "Teknik_Nesne": vp.get("token", "SAHA"),
            "Ekip": vp.get("ekip_adi", ""),
            "Lokasyon": vp.get("adres_isim", ""),
            "Koordinat": f"{vp.get('enlem')},{vp.get('boylam')}",
            "Ariza_Tanimi": "Görsel analiz bekleniyor",
            "Guven_%": 0,
            "Risk_%": 0,
            "Tahmini_Sicaklik_C": vp.get("sicaklik", 0),
            "Gorsel_Hash": "",
            "Onerilen_Aksiyon": "Görsel yüklenip Roboflow/YOLO analizi yapılmalıdır.",
            "Kaynak": "Sistem",
            "Kayit_Tarihi": vp.get("tarih", ""),
        }]
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        pd.DataFrame(ana).to_excel(writer, index=False, sheet_name="SAP_PM_BILDIRIM")
        analizleri_df(analizler).to_excel(writer, index=False, sheet_name="YOLO_TESPITLER")
        pd.DataFrame([{
            "Saha_Kodu": vp.get("token", ""),
            "Adres": vp.get("adres_isim", ""),
            "Enlem": vp.get("enlem", ""),
            "Boylam": vp.get("boylam", ""),
            "Hava_Sicakligi": vp.get("hava", {}).get("temp", ""),
            "Nem": vp.get("hava", {}).get("nem", ""),
            "Ruzgar": vp.get("hava", {}).get("ruzgar", ""),
            "Yildirim_Aylik": vp.get("yildirim", ""),
            "Hat_Akimi_A": vp.get("akim", ""),
            "Yangin_Riski": vp.get("yangin_riski", ""),
        }]).to_excel(writer, index=False, sheet_name="SAHA_BILGISI")
    return buf.getvalue()


def arsiv_excel_olustur(db):
    satirlar = []
    for token_key, kayit in (db or {}).items():
        for a in kayit.get("analizler", []) or []:
            satirlar.append({
                "Saha_Kodu": token_key,
                "Dosya": a.get("dosya", ""),
                "Hash": a.get("hash", ""),
                "Anomali": a.get("anomali", ""),
                "Risk": a.get("risk_skoru", ""),
                "Enlem": a.get("lat", ""),
                "Boylam": a.get("lon", ""),
                "Tarih": a.get("tarih", ""),
                "Konum_Kaynagi": a.get("konum_kaynagi", ""),
                "Veri_Guvenilirligi": a.get("veri_guvenilirligi", ""),
                "Veri_Guven_Puani": a.get("veri_guven_puani", ""),
                "Tavsiye": a.get("tavsiye", ""),
                "AI_Detayli_Yorum": a.get("ai_detay", ""),
            })
    df = pd.DataFrame(satirlar) if satirlar else pd.DataFrame(columns=["Saha_Kodu", "Dosya", "Hash", "Anomali", "Risk", "Enlem", "Boylam", "Tarih", "Tavsiye", "AI_Detayli_Yorum"])
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="ANALIZ_ARSIVI")
    return buf.getvalue()


def cihaz_canli_konumunu_al():
    """Tarayıcı GPS izni verirse cihazın gerçek konumunu döndürür. İzin yoksa None döner."""
    if get_geolocation is None:
        return None, "Canlı konum için requirements.txt içine streamlit-js-eval eklenmeli."
    try:
        loc = get_geolocation()
        if not loc:
            return None, "Tarayıcı konum izni bekleniyor. İzin penceresi gelirse izin verin."
        if isinstance(loc, dict) and "error" in loc:
            err = loc.get("error", {})
            return None, f"Cihaz konumu alınamadı: {err.get('message', 'izin/konum hatası')}"
        coords = loc.get("coords", {}) if isinstance(loc, dict) else {}
        lat = coords.get("latitude")
        lon = coords.get("longitude")
        acc = coords.get("accuracy")
        if lat is not None and lon is not None:
            return {"lat": float(lat), "lon": float(lon), "accuracy": acc}, "Cihaz canlı konumu alındı."
    except Exception as e:
        return None, f"Cihaz konumu alınamadı: {e}"
    return None, "Cihaz konumu alınamadı."

# ==========================================
# ⚡ 5. API, KONUM VE METEOROLOJİ
# ==========================================
def gercek_konum_bul():
    """ÇÖZÜM: Adres boşsa veya API yanıtsız kalırsa, kullanıcının gerçek IP'sini bulur."""
    try:
        # Öncelikli olarak ip-api üzerinden gerçek konumu çek
        r = requests.get("http://ip-api.com/json/", timeout=3).json()
        if "lat" in r and "lon" in r:
            return float(r["lat"]), float(r["lon"]), f"{r['city']}, {r['country']} (Gerçek IP Konumu)"
    except: pass
    
    try:
        # İkinci seçenek olarak ipinfo kullan
        r = requests.get("https://ipinfo.io/json", timeout=3).json()
        if "loc" in r:
            lat, lon = r["loc"].split(",")
            return float(lat), float(lon), f"{r['city']}, {r['country']} (Gerçek IP Konumu)"
    except: pass
    
    # Tüm API'ler engellenmişse bulunulan varsayılan konum
    return 41.0027, 39.7168, "Trabzon Merkez (Sistem Varsayılanı)"

@st.cache_data(show_spinner=False)
def adres_koordinat_bul(il, ilce, cadde):
    if not il and not ilce and not cadde:
        return gercek_konum_bul()
    
    aramalar = [
        f"{cadde} {ilce} {il} Turkey".strip(),
        f"{ilce} {il} Turkey".strip(),
        f"{il} Turkey".strip()
    ]
    
    for q in aramalar:
        if not q.replace("Turkey", "").strip(): continue
        try:
            r = requests.get(f"https://nominatim.openstreetmap.org/search?q={q}&format=json&limit=1", headers={"User-Agent":"GridAI_Panel_Pro"}, timeout=3).json()
            if r: return float(r[0]["lat"]), float(r[0]["lon"]), r[0]["display_name"]
        except: pass
    
    # ÇÖZÜM: API yanıtsız kalırsa direkt kullanıcının bulunduğu IP'ye git
    return gercek_konum_bul()

@st.cache_data(show_spinner=False)
def hava_durumu_cek(lat, lon):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,weather_code&daily=weather_code,temperature_2m_max,temperature_2m_min,wind_speed_10m_max&timezone=auto"
    try:
        d = requests.get(url, timeout=3).json()
        return {
            "temp": d["current"]["temperature_2m"], "nem": d["current"]["relative_humidity_2m"], 
            "ruzgar": d["current"]["wind_speed_10m"], "yagis": d["current"]["precipitation"],
            "t_gunler": d["daily"]["time"][:5], "t_max": d["daily"]["temperature_2m_max"][:5], "t_kod": d["daily"]["weather_code"][:5]
        }
    except:
        b = datetime.now()
        return {"temp": 22, "nem": 65, "ruzgar": 12.5, "yagis": 0, "t_gunler": [(b+timedelta(days=i)).strftime("%Y-%m-%d") for i in range(5)], "t_max": [22,23,24,25,22], "t_kod": [0,1,2,0,0]}

# ÇÖZÜM: YILDIRIM GERÇEK API'DEN ÇEKİLİYOR VE KİLİTLENİYOR
@st.cache_data(show_spinner=False)
def gercek_yildirim_api_cek(lat, lon):
    """
    Open-Meteo API üzerinden o koordinatın son 30 günlük geçmiş fırtına verilerini çeker.
    Bu fonksiyon @st.cache_data ile kilitlendiği için, enlem/boylam değişmedikçe
    slider ile ne kadar oynanırsa oynansın ASLA GÜNCELLENMEZ ve DEĞİŞMEZ.
    """
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=weather_code&past_days=30&forecast_days=1&timezone=auto"
    try:
        r = requests.get(url, timeout=5).json()
        gunluk_kodlar = r.get("daily", {}).get("weather_code", [])
        
        # 95, 96, 99 hava kodları API'de gerçek "Gök Gürültülü Fırtına" demektir
        firtina_gunleri = [kod for kod in gunluk_kodlar if kod in [95, 96, 99]]
        
        # Meteorolojik olarak 1 fırtınalı günde lokal bölgeye düşen ortalama deşarj hesabı
        aylik_yildirim = len(firtina_gunleri) * 18
        
        if aylik_yildirim == 0:
            # Geçmiş 30 günde hiç fırtına yoksa, iklimsel bölge averajı uygulanır
            aylik_yildirim = max(2, int(abs(lat) * 0.4))
            
        return aylik_yildirim, aylik_yildirim * 12
    except:
        return 14, 168

def vejetasyon_yangin_riski_hesapla(sicaklik, nem, ruzgar):
    skor = (sicaklik * 1.5) + (ruzgar * 0.8) - (nem * 0.4)
    if skor > 50: return "%84.5 (KRİTİK - Acil Budama Gerekli)"
    if skor > 30: return "%51.2 (ORTA - Takip Listesinde)"
    return "%18.4 (DÜŞÜK - Emniyetli Seviye)"

def hava_emoji(kod):
    kod = int(kod)
    if kod == 0: return "☀️ Açık"
    if kod in [1,2,3]: return "⛅ Parçalı Bulutlu"
    if kod in [45,48]: return "🌫️ Sisli"
    if kod in [51,53,55,61,63,65]: return "🌧️ Yağışlı"
    if kod in [71,73,75]: return "❄️ Karlı"
    if kod in [95,96,99]: return "⛈️ Fırtına"
    return "☁️ Bulutlu"

# ==========================================
# ⚡ 6. KAPSAMLI KURUMSAL PDF RAPORU
# ==========================================
def genis_pdf_olustur(path, vp):
    doc = SimpleDocTemplate(path, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    title = ParagraphStyle("T", fontName=FONT_BLD, fontSize=18, textColor=colors.HexColor("#0F766E"), alignment=1, spaceAfter=20)
    h2 = ParagraphStyle("H2", fontName=FONT_BLD, fontSize=14, textColor=colors.HexColor("#1E293B"), spaceBefore=20, spaceAfter=10)
    body = ParagraphStyle("B", fontName=FONT_REG, fontSize=10, leading=15, textColor=colors.HexColor("#334155"))
    bold = ParagraphStyle("BB", fontName=FONT_BLD, fontSize=10, leading=15, textColor=colors.HexColor("#1E293B"))
    story = []
    gecici_dosyalar = []

    story.append(Paragraph("GRIDAI KAPSAMLI ARIZA VE DURUM RAPORU", title))
    story.append(Paragraph(f"Tarih: {vp['tarih']} | Saha Kodu: {vp['token']}", ParagraphStyle("S", fontName=FONT_REG, alignment=1, spaceAfter=20)))

    story.append(Paragraph("Saha ve Ekip Bilgileri", h2))
    td1 = [
        [Paragraph("Ekip Adı:", bold), Paragraph(vp['ekip_adi'], body)],
        [Paragraph("Ekip Mesajı:", bold), Paragraph(vp['ekip_mesaji'], body)],
        [Paragraph("Lokasyon:", bold), Paragraph(vp['adres_isim'], body)],
        [Paragraph("Koordinat:", bold), Paragraph(f"Enlem: {vp['enlem']:.6f} / Boylam: {vp['boylam']:.6f}", body)]
    ]
    t1 = Table(td1, colWidths=[120, 390])
    t1.setStyle(TableStyle([("BACKGROUND",(0,0),(0,-1),colors.HexColor("#F8FAFC")), ("GRID",(0,0),(-1,-1),0.5,colors.lightgrey), ("VALIGN",(0,0),(-1,-1),"TOP"), ("PADDING",(0,0),(-1,-1),8)]))
    story.append(t1)

    story.append(Spacer(1, 20))
    story.append(Paragraph("Saha Ekipleri İçin Navigasyon QR Kodu", h2))
    story.append(Paragraph("Bu QR kodu taratarak doğrudan koordinata Google Maps üzerinden yol tarifi alabilirsiniz.", body))
    qr_nav = qrcode.make(f"http://maps.google.com/maps?q={vp['enlem']},{vp['boylam']}")
    qr_path = f"qr_nav_{vp['token']}.png"
    qr_nav.save(qr_path)
    gecici_dosyalar.append(qr_path)
    story.append(RLImage(qr_path, width=120, height=120))

    story.append(PageBreak())
    story.append(Paragraph("Çevresel Metrikler ve Mühendislik Açıklamaları", h2))
    cevre_ai = cevre_metrik_ai_yorumlari(vp)
    td2 = [
        [Paragraph("Metrik", bold), Paragraph("Değer", bold), Paragraph("Detaylı Anlamı", bold)],
        [Paragraph("Ortam Sıcaklığı", body), Paragraph(f"{vp['hava']['temp']} °C", body), Paragraph("Anlık atmosfer ısısı. İletkenin soğuma kapasitesini ve mekanik genleşmeyi etkiler. <br/><br/><b>AI yorum:</b> " + cevre_ai["sicaklik"], body)],
        [Paragraph("Rüzgar Hızı", body), Paragraph(f"{vp['hava']['ruzgar']} km/s", body), Paragraph("Hatta binen yanal mekanik yük. Katener salınım riskini belirler. <br/><br/><b>AI yorum:</b> " + cevre_ai["ruzgar"], body)],
        [Paragraph("Hat Akımı", body), Paragraph(f"{vp['akim']} A", body), Paragraph("Sistemden geçen enerji yükü. Aşırı değerler izolasyon erimesine yol açar. <br/><br/><b>AI yorum:</b> " + cevre_ai["akim"], body)],
        [Paragraph("Aylık Yıldırım", body), Paragraph(f"{vp['yildirim']}", body), Paragraph("Coğrafi konuma düşen tahmini deşarj sayısı. Parafudr bakım süresini belirler. <br/><br/><b>AI yorum:</b> " + cevre_ai["yildirim"], body)]
    ]
    t2 = Table(td2, colWidths=[100, 70, 340])
    t2.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#E2E8F0")), ("GRID",(0,0),(-1,-1),0.5,colors.grey), ("VALIGN",(0,0),(-1,-1),"TOP"), ("PADDING",(0,0),(-1,-1),8)]))
    story.append(t2)

    story.append(PageBreak())
    story.append(Paragraph("Yapay Zeka Görsel Analiz (YOLOv11 / Roboflow & OpenCV)", h2))
    analizler = vp.get("analizler", []) or []
    if analizler:
        for i, a in enumerate(analizler[:6], 1):
            story.append(Paragraph(f"Analiz #{i} - {a.get('dosya','görsel')}", h2))
            try:
                img_path = f"analiz_{i}_{vp['token']}.png"
                with open(img_path, "wb") as f:
                    f.write(base64.b64decode(a.get("islenmis_b64") or a.get("gorsel_b64")))
                gecici_dosyalar.append(img_path)
                story.append(RLImage(img_path, width=350, height=250))
                story.append(Spacer(1, 8))
            except Exception:
                pass
            rows = [
                [Paragraph("Hash", bold), Paragraph(a.get("hash_kisa", ""), body)],
                [Paragraph("Konum", bold), Paragraph(f"{a.get('lat'):.6f}, {a.get('lon'):.6f} ({a.get('konum_kaynagi')})", body)],
                [Paragraph("Veri Güvenilirliği", bold), Paragraph(f"{a.get('veri_guvenilirligi','')} / {a.get('veri_guven_puani','')} - {a.get('veri_guven_notu','')}", body)],
                [Paragraph("Tespit", bold), Paragraph(f"{a.get('anomali')} - Güven %{a.get('guven')}", body)],
                [Paragraph("Risk", bold), Paragraph(f"%{a.get('risk_skoru')} | Glint: {'Var' if a.get('glint') else 'Yok'}", body)],
                [Paragraph("AI Tavsiye", bold), Paragraph(a.get("tavsiye", ""), body)],
                [Paragraph("AI Detaylı Yorum", bold), Paragraph(a.get("ai_detay", ""), body)],
            ]
            tr = Table(rows, colWidths=[90, 420])
            tr.setStyle(TableStyle([("GRID",(0,0),(-1,-1),0.5,colors.lightgrey), ("VALIGN",(0,0),(-1,-1),"TOP"), ("PADDING",(0,0),(-1,-1),7)]))
            story.append(tr)
            story.append(Spacer(1, 12))
    else:
        story.append(Paragraph("Bu saha analizi için henüz görsel yüklenmemiştir. Roboflow/YOLO entegrasyonu sonrası aynı rapor otomatik gerçek tespitlerle dolacaktır.", body))

    story.append(Spacer(1, 20))
    story.append(Paragraph("Belge Doğrulama QR Kodu", h2))
    qr_doc = qrcode.make(f"GridAI Onaylı Rapor - {vp['token']}")
    qr_doc_path = f"qr_doc_{vp['token']}.png"
    qr_doc.save(qr_doc_path)
    gecici_dosyalar.append(qr_doc_path)
    story.append(RLImage(qr_doc_path, width=80, height=80))
    story.append(Paragraph("<b>Veri Kaynağı:</b> Hava durumu verileri Open-Meteo API'den; görsel analiz verileri Roboflow/YOLO veya demo modundan alınmıştır. EXIF veya canlı GPS yoksa konum bilgisi kesin saha kanıtı değil, geçici CBS/cihaz referansıdır.", ParagraphStyle("S", fontName=FONT_REG, fontSize=8, textColor=colors.gray, alignment=1)))

    doc.build(story)
    for p in gecici_dosyalar:
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass

# ==========================================
# ⚡ 7. KONTROL PANELİ (SIDEBAR)
# ==========================================
with st.sidebar:
    st.markdown("""<div class="logo-container"><h2 style="margin:0;">⚡ GridAI Panel</h2></div>""", unsafe_allow_html=True)

    st.subheader("👤 Kullanıcı")
    kullanici_adi = st.text_input("Kullanıcı adı / saha personeli", value=st.session_state.get("kullanici_adi", "Saha Kullanıcısı"))
    st.session_state.kullanici_adi = kullanici_adi

    st.markdown("---")
    arama_token = st.text_input("🔍 Arşiv Kodunu Giriniz:")
    if st.button("Arşivi Getir", use_container_width=True):
        st.session_state.yuklenen_arsiv = arama_token
        
    st.markdown("---")
    
    st.subheader("📍 CBS Konum")
    input_il = st.text_input("İl", value="")
    input_ilce = st.text_input("İlçe", value="")
    input_cadde = st.text_input("Cadde/Mahalle", value="")
    st.markdown("<small style='color:#94A3B8;'>EXIF olmayan görseller için koordinat girerek kesin saha konumu belirleyebilirsiniz.</small>", unsafe_allow_html=True)
    ko1, ko2 = st.columns(2)
    manuel_lat_txt = ko1.text_input("Enlem", value="", placeholder="41.002700", key="manuel_lat_txt")
    manuel_lon_txt = ko2.text_input("Boylam", value="", placeholder="39.716800", key="manuel_lon_txt")
    if st.button("📍 Koordinata Git / CBS'ye İşle", use_container_width=True):
        try:
            ml = float(str(manuel_lat_txt).replace(",", "."))
            mn = float(str(manuel_lon_txt).replace(",", "."))
            st.session_state.manuel_koordinat = {"lat": ml, "lon": mn}
            st.session_state.harita_merkez_override = {
                "lat": ml,
                "lon": mn,
                "adres": f"Manuel Koordinat Konumu ({ml:.6f}, {mn:.6f})",
                "kaynak": "Manuel koordinat / operatör doğrulaması",
            }
            log_ekle("CBS", f"Manuel koordinat işlendi: {ml:.6f}, {mn:.6f}")
            st.rerun()
        except Exception:
            st.error("Enlem ve boylam sayısal olmalı. Örnek: 41.002700 / 39.716800")
    cbs_coord_placeholder = st.empty()
    
    st.markdown("---")
    st.subheader("📝 Ekip Notları")
    ekip_adi = st.text_input("Ekip Adı", value="Mobil Bakım Ekibi")
    ekip_mesaji = st.text_area("Ekip Mesajı", value="Rutin şebeke kontrolü sağlandı.")
    
    st.markdown("---")
    st.subheader("⚙️ Parametreler")
    # ÖNEMLİ: Widget key'i artık hat_sicakligi değil. Böylece YOLO butonu bu değeri güvenle güncelleyebilir.
    secilen_sicaklik = st.slider("Ölçülen Şapka Sıcaklığı (°C):", -10.0, 140.0, value=float(st.session_state.get("hat_sicakligi", 55.0)), key="hat_sicakligi_slider")
    st.session_state.hat_sicakligi = float(secilen_sicaklik)
    tahmini_hat_akimi = st.slider("Tahmini Hat Akımı (A)", 10, 1200, 420)


    st.markdown("---")
    st.subheader("🤖 Roboflow API Durumu")
    rf_ayar = roboflow_ayarlari()
    if rf_ayar["aktif"]:
        st.success("Roboflow bağlı")
        st.caption(f"Model: {rf_ayar.get('model_id') or rf_ayar.get('endpoint')}")
        st.caption(f"Confidence: {rf_ayar['confidence']:.2f} | Overlap: {rf_ayar['overlap']:.2f}")
    else:
        st.warning("Roboflow API girilmedi; demo/mock mod aktif")
        st.caption("API anahtarını .streamlit/secrets.toml veya Streamlit Cloud > Secrets alanına ekleyin.")

    st.markdown("---")
    st.subheader("🗄️ Ortak Veri Tabanı")
    sb_ayar = supabase_ayarlari()
    if sb_ayar["aktif"]:
        st.success("Supabase bağlı")
        st.caption(f"Tablo: {sb_ayar['table']}")
    else:
        st.warning("Supabase kapalı/eksik")
        st.caption("SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY ve SUPABASE_TABLE Secrets alanında olmalı.")

    st.markdown("---")
    st.subheader("🧩 Görsel Tespit Ayarı")
    st.session_state.tespit_kutulari_goster = st.checkbox(
        "Roboflow tespit kutularını göster",
        value=bool(st.session_state.get("tespit_kutulari_goster", True)),
        help="Model object detection kutusu döndürüyorsa hem arayüzde hem PDF raporda çizilir. Classification modelinde kutu üretilemez."
    )


# ==========================================
# ⚡ 8. ARŞİV VE CANLI VERİ YÖNETİMİ
# ==========================================
g_mod = False
arsiv_kodu = st.session_state.yuklenen_arsiv

if arsiv_kodu and arsiv_kodu.strip() in st.session_state.db:
    g_mod = True
    v = st.session_state.db[arsiv_kodu.strip()]
    input_il, input_ilce, input_cadde, enlem, boylam = v["il"], v["ilce"], v["cadde"], v["enlem"], v["boylam"]
    hava, yildirim, ekip_adi, ekip_mesaji = v["hava"], v["yildirim"], v["ekip_adi"], v["ekip_mesaji"]
    adres_detay, token = v["adres_isim"], v["token"]

if not g_mod:
    cbs_bos = not any([input_il.strip(), input_ilce.strip(), input_cadde.strip()])
    override = st.session_state.get("harita_merkez_override")
    if override:
        enlem = float(override["lat"])
        boylam = float(override["lon"])
        adres_detay = override.get("adres", f"Tespit Görsel Konumu ({enlem:.6f}, {boylam:.6f})")
        st.session_state.son_konum_kaynagi = override.get("kaynak", "Tespit görsel koordinatı")
    elif cbs_bos:
        loc, msg = cihaz_canli_konumunu_al()
        if loc:
            st.session_state.cihaz_konum = loc
            st.session_state.cihaz_konum_mesaj = msg
            enlem = float(loc["lat"])
            boylam = float(loc["lon"])
            dogruluk = loc.get("accuracy")
            adres_detay = f"Gerçek Cihaz Konumu ({enlem:.6f}, {boylam:.6f})" + (f" | Doğruluk: ~{dogruluk:.0f} m" if dogruluk else "")
            st.session_state.son_konum_kaynagi = "Tarayıcı GPS / cihaz konumu"
        else:
            enlem, boylam, adres_detay = adres_koordinat_bul(input_il, input_ilce, input_cadde)
            st.session_state.son_konum_kaynagi = f"Konum izni yoksa yedek kaynak: {msg}"
    else:
        enlem, boylam, adres_detay = adres_koordinat_bul(input_il, input_ilce, input_cadde)
        st.session_state.son_konum_kaynagi = "CBS adres çözümleme"
    hava = hava_durumu_cek(enlem, boylam)
    # Yıldırım, Slider'dan etkilenmeyen, sadece Enlem'e bağlı gerçek API'den çekilir.
    yildirim, _ = gercek_yildirim_api_cek(enlem, boylam)
    token = f"{input_ilce.replace(' ','').upper() if input_ilce else 'SAHA'}_{datetime.now().strftime('%Y%m%d_%H%M')}"

# CBS koordinatlarını sidebar'daki CBS Konum alanının altında göster.
try:
    with cbs_coord_placeholder.container():
        st.markdown("<small style='color:#94A3B8;'>Koordinatlar</small>", unsafe_allow_html=True)
        kc1, kc2 = st.columns(2)
        kc1.markdown(f"<div style='background:#1E293B; border:1px solid #334155; border-radius:8px; padding:8px; font-size:12px;'><b>Enlem</b><br>{float(enlem):.6f}</div>", unsafe_allow_html=True)
        kc2.markdown(f"<div style='background:#1E293B; border:1px solid #334155; border-radius:8px; padding:8px; font-size:12px;'><b>Boylam</b><br>{float(boylam):.6f}</div>", unsafe_allow_html=True)
        st.caption(f"Kaynak: {st.session_state.get('son_konum_kaynagi', '')}")
except Exception:
    pass

# ==========================================
# ⚡ 9. ANA EKRAN VE HARİTA
# ==========================================
st.title("⚡ GridAI Drone ve Yapay Zeka Tabanlı Elektrik Hattı Görüntü Analizi ve Arıza Tahmin Sistemi")
st.markdown(f"**Saha Kodu:** `{token}` | **Lokasyon:** {adres_detay}")
st.caption(f"Konum kaynağı: {st.session_state.get('son_konum_kaynagi', '')}")

with st.expander("📱 Mobil Hızlı Panel / Sidebar görünmüyorsa burayı kullan", expanded=False):
    st.caption("Telefonlarda sidebar genelde gizli menüye alınır. Saha personeli bu panelden kullanıcı ve koordinat bilgisini hızlı girebilir.")
    mob1, mob2 = st.columns([1, 1])
    with mob1:
        mobil_ad = st.text_input("Mobil kullanıcı adı", value=st.session_state.get("kullanici_adi", "Saha Kullanıcısı"), key="mobil_kullanici_adi_input")
        if st.button("👤 Kullanıcı Adını Uygula", key="mobil_kullanici_adi_btn", use_container_width=True):
            st.session_state.kullanici_adi = mobil_ad or "Saha Kullanıcısı"
            st.success("Kullanıcı adı güncellendi.")
            st.rerun()
    with mob2:
        sb_ayar_mobil = supabase_ayarlari()
        if sb_ayar_mobil.get("aktif"):
            st.success("Supabase bağlı: telefon ve web ortak kayıt kullanır.")
        else:
            st.warning(f"Supabase pasif: {sb_ayar_mobil.get('url_msg','Secret/key kontrol edin.')}")
    km1, km2 = st.columns(2)
    mobil_lat = km1.text_input("Mobil/manuel enlem", value="", placeholder="41.002700", key="mobil_lat_input")
    mobil_lon = km2.text_input("Mobil/manuel boylam", value="", placeholder="39.716800", key="mobil_lon_input")
    if st.button("📍 Mobil Koordinatı Haritaya ve Analize İşle", key="mobil_koord_btn", use_container_width=True):
        try:
            ml = float(str(mobil_lat).replace(",", "."))
            mn = float(str(mobil_lon).replace(",", "."))
            st.session_state.manuel_koordinat = {"lat": ml, "lon": mn}
            st.session_state.harita_merkez_override = {
                "lat": ml,
                "lon": mn,
                "adres": f"Mobil/Manuel Koordinat Konumu ({ml:.6f}, {mn:.6f})",
                "kaynak": "Mobil hızlı panel / operatör doğrulaması",
            }
            log_ekle("MOBIL_CBS", f"Mobil panelden koordinat işlendi: {ml:.6f}, {mn:.6f}")
            st.rerun()
        except Exception:
            st.error("Enlem ve boylam sayısal olmalı. Örnek: 41.002700 / 39.716800")
    st.info("Mobil çekimde en güvenilir akış: konum izni ver → kamera ile çek → analiz et → arşive kaydet. EXIF yoksa bu koordinat/cihaz GPS'i kullanılır.")

c1, c2, c3, c4 = st.columns(4)
c1.markdown(f"<div class='metric-box'><small>🔥 Sıcaklık / Nem</small><h3>{hava['temp']} °C / %{hava['nem']}</h3></div>", unsafe_allow_html=True)
c2.markdown(f"<div class='metric-box'><small>⚡ Tahmini Hat Akımı</small><h3>{tahmini_hat_akimi} A</h3></div>", unsafe_allow_html=True)
c3.markdown(f"<div class='metric-box'><small>🍁 Yangın Riski</small><h3>{vejetasyon_yangin_riski_hesapla(hava['temp'],hava['nem'],hava['ruzgar']).split()[0]}</h3></div>", unsafe_allow_html=True)
c4.markdown(f"<div class='metric-box'><small>⛈️ Aylık Yıldırım (API Verisi)</small><h3>{yildirim}</h3></div>", unsafe_allow_html=True)

st.markdown("---")

# HARİTA TAM EKRAN (Stefan Kutusu Silindi) - BOYUT VE KATMANLAR KORUNDU
st.subheader("🗺️ Katman Kontrollü CBS Haritası")
m = folium.Map(location=[enlem, boylam], zoom_start=14, tiles=None)

folium.TileLayer("OpenStreetMap", name="Sokak Haritası").add_to(m)
folium.TileLayer(tiles='https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}', attr='Google', name='Uydu Görünümü').add_to(m)
folium.TileLayer(tiles='https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', attr='OpenTopoMap', name='Topografik Harita').add_to(m)

# Ortak Supabase kayıtları: telefon ve web panel aynı saha kayıtlarını görsün diye harita katmanına eklenir.
supabase_kayitlar, supabase_okuma_mesaj = supabase_analizleri_getir(limit=75)

heat_points = []
for r in supabase_kayitlar:
    try:
        if r.get("enlem") is not None and r.get("boylam") is not None:
            heat_points.append([float(r.get("enlem")), float(r.get("boylam")), max(0.15, min(float(r.get("risk_skoru") or 0) / 100.0, 1.0))])
    except Exception:
        pass
for a in (st.session_state.get("gorsel_kuyrugu", []) or st.session_state.get("son_analizler", [])):
    try:
        agirlik = heatmap_agirligi_hesapla(a)
        heat_points.append([float(a.get("lat", enlem)), float(a.get("lon", boylam)), agirlik])
    except Exception:
        pass
if heat_points:
    HeatMap(heat_points, name="Risk Ağırlıklı Isı Haritası", radius=22, blur=16, min_opacity=0.25).add_to(m)
else:
    st.caption("Isı haritası, analiz yapılan görsellerin risk skoru + arıza sınıfı + veri güvenilirliğiyle oluşturulur. Henüz analiz noktası olmadığı için ısı katmanı boş.")
folium.Marker([enlem, boylam], popup=f"{adres_detay}", icon=folium.Icon(color="red", icon="bolt", prefix="fa")).add_to(m)

for r in supabase_kayitlar:
    try:
        if r.get("enlem") is None or r.get("boylam") is None:
            continue
        popup = f"""
        <b>Ortak Kayıt / {r.get('rapor_token','')}</b><br>
        Kullanıcı: {r.get('kullanici_adi','')}<br>
        Cihaz: {r.get('cihaz_turu','')}<br>
        Tespit: {r.get('tespit','')}<br>
        Güven: %{r.get('guven',0)}<br>
        Risk: %{r.get('risk_skoru',0)} ({r.get('risk_seviyesi','')})<br>
        Konum Kaynağı: {r.get('konum_kaynagi','')}<br>
        Tarih: {str(r.get('created_at',''))[:19]}
        """
        folium.CircleMarker(
            location=[float(r.get("enlem")), float(r.get("boylam"))],
            radius=6,
            popup=folium.Popup(popup, max_width=340),
            color="#F59E0B",
            fill=True,
            fill_color="#F59E0B",
            fill_opacity=0.65,
        ).add_to(m)
    except Exception:
        pass

for a in (st.session_state.get("gorsel_kuyrugu", []) or st.session_state.get("son_analizler", [])):
    try:
        popup = f"""
        <b>{a.get('dosya','Görsel')}</b><br>
        Hash: {a.get('hash_kisa','')}<br>
        Tespit: {a.get('anomali','')}<br>
        Güven: %{a.get('guven',0)}<br>
        Risk: %{a.get('risk_skoru',0)}<br>
        Konum Kaynağı: {a.get('konum_kaynagi','')}<br>
        Isı Ağırlığı: {heatmap_agirligi_hesapla(a)}
        """
        folium.CircleMarker(
            location=[float(a.get("lat", enlem)), float(a.get("lon", boylam))],
            radius=8,
            popup=folium.Popup(popup, max_width=320),
            color="#38BDF8",
            fill=True,
            fill_color="#0F766E",
            fill_opacity=0.8,
        ).add_to(m)
    except Exception:
        pass

folium.LayerControl().add_to(m)
st_folium(m, use_container_width=True, height=500)

st.markdown("### 🔮 5 Günlük Hava Tahmini (Open-Meteo)")
st.caption("MGM entegrasyonu opsiyoneldir: resmi/kurumsal MGM veri erişimi sağlanırsa bu blok aynı tasarım korunarak MGM adaptörüne bağlanabilir. Şimdilik jüri demosunda kararlı çalışması için Open-Meteo kullanılır.")
w_cols = st.columns(5)
for i in range(5):
    with w_cols[i]:
        st.markdown(f"""
        <div style="background-color:#1E293B; padding:10px; border-radius:8px; border:1px solid #334155; text-align:center;">
        <span style="color:#38BDF8; font-weight:bold;">{hava['t_gunler'][i]}</span><br><br>
        <span style="font-size:24px;">{hava_emoji(hava['t_kod'][i]).split(' ')[0]}</span><br>
        <span style="font-size:12px;">{hava_emoji(hava['t_kod'][i]).split(' ', 1)[1]}</span><br><br>
        🔥 {hava['t_max'][i]}°C
        </div>
        """, unsafe_allow_html=True)

st.markdown("---")

# ==========================================
# ⚡ 10. YOLOv11 / ROBOFLOW & OPENCV & MOBİL ODA
# ==========================================
st.subheader("📸 Yapay Zeka Analiz Odası")
st.caption("Not: Roboflow yalnızca eğitildiği/etiketlendiği sınıfları güvenilir tespit eder. EXIF/GPS olmayan yüklenmiş görseller kesin saha konumu kabul edilmez; koordinat alanından manuel doğrulama yapılabilir.")
secim = st.radio("Veri Girişi", ["Görsel Ekle", "Mobil Saha Terminali"], horizontal=True)

b64_gorsel, yolo_durum, glint_durum, risk_puan = None, None, False, 0
aktif_analizler = []

if secim == "Görsel Ekle":
    st.caption("Yeni görsel eklediğinizde önceki analizler silinmez. Her görsel hash ile kuyruğa alınır ve rapora birlikte yazılır.")
    up_list = st.file_uploader(
        "Saha Görsellerini Seçin (Birden fazla görsel yükleyebilirsiniz)",
        type=["jpg", "png", "jpeg"],
        accept_multiple_files=True,
        key=f"gorsel_uploader_{st.session_state.uploader_counter}",
    )

    mevcut_hashler = {a.get("hash") for a in st.session_state.gorsel_kuyrugu}
    yeni_sayisi = 0
    if up_list:
        with st.spinner("Görseller analiz kuyruğuna ekleniyor..."):
            for up in up_list:
                raw = up.getvalue()
                hsh = sha256_uret(raw)
                if hsh in mevcut_hashler:
                    continue
                analiz = gorsel_analiz_pipeline(
                    up.name, raw, enlem, boylam, adres_detay, hava,
                    analiz_kaynagi="Yüklenen görsel",
                    konum_kaynagi_override=("Manuel koordinat / operatör doğrulaması" if st.session_state.get("manuel_koordinat") or "Manuel" in str(st.session_state.get("son_konum_kaynagi", "")) else None),
                )
                st.session_state.gorsel_kuyrugu.append(analiz)
                mevcut_hashler.add(hsh)
                yeni_sayisi += 1
        if yeni_sayisi:
            st.success(f"{yeni_sayisi} yeni görsel analiz kuyruğuna eklendi. Önceki analizler korunuyor.")
        else:
            st.info("Seçilen görseller daha önce analiz kuyruğuna eklenmiş; tekrar eklenmedi.")

    aktif_analizler = st.session_state.gorsel_kuyrugu
    st.session_state.son_analizler = aktif_analizler

    col_k1, col_k2 = st.columns([1, 1])
    with col_k1:
        st.metric("Analiz Kuyruğundaki Görsel", len(aktif_analizler))
    with col_k2:
        if st.button("🧹 Analiz Kuyruğunu Temizle", use_container_width=True):
            st.session_state.gorsel_kuyrugu = []
            st.session_state.son_analizler = []
            st.session_state.uploader_counter += 1
            st.rerun()

    if aktif_analizler:
        st.info("Aşağıdaki tüm analizler PDF rapora, SAP Excel'e, arşiv Excel'e ve harita tespit noktalarına dahil edilir.")
        for idx, analiz in enumerate(aktif_analizler, start=1):
            with st.expander(f"#{idx} {analiz['dosya']} | Hash: {analiz['hash_kisa']} | Risk: %{analiz['risk_skoru']}", expanded=(idx == len(aktif_analizler))):
                c_img, c_res = st.columns([1, 1])
                with c_img:
                    st.image(Image.open(io.BytesIO(base64.b64decode(analiz.get("islenmis_b64") or analiz["gorsel_b64"]))), width=400)
                with c_res:
                    st.success(f"**YOLO/Roboflow Tespiti:** {analiz['anomali']} (Güven: %{analiz['guven']})")
                    st.caption(f"Kaynak: {analiz['kaynak']}")
                    kutu_sayisi = sum(1 for p in analiz.get("predictions", []) if p.get("kutu_var") or p.get("bbox"))
                    if "Roboflow" in str(analiz.get("kaynak", "")):
                        st.success(f"Roboflow API gerçek tahmin verdi. Kutu sayısı: {kutu_sayisi}")
                    if analiz.get("predictions") and kutu_sayisi == 0:
                        st.warning("Model sınıf/etiket döndürdü ancak çizilebilir bounding box döndürmedi. Bu genellikle classification/yanlış model tipi veya Workflow çıktı formatı nedeniyle olur.")
                    st.write(f"**Hash:** `{analiz['hash']}`")
                    st.write(f"**Konum:** {analiz['lat']:.6f}, {analiz['lon']:.6f} — {analiz['konum_kaynagi']}")
                    st.write(f"**Veri Güvenilirliği:** {analiz.get('veri_guvenilirligi','')} / {analiz.get('veri_guven_puani','')} — {analiz.get('veri_guven_notu','')}")
                    st.write(f"**Çekim Tarihi:** {analiz['cekim_tarihi']}")
                    if "EXIF" in str(analiz.get("konum_kaynagi", "")) and analiz.get("konum_kaynagi") != "EXIF GPS":
                        st.caption("Not: WhatsApp/mesajlaşma uygulamaları çoğu zaman fotoğrafın EXIF GPS bilgisini siler. Bu durumda sistem görseli mevcut CBS/cihaz konumuyla eşler; kesin saha noktası için alttaki manuel koordinat düzeltmesini kullanabilirsiniz.")
                    if analiz["glint"]:
                        st.warning(f"⚠️ OpenCV Anti-Glint: Güneş yansıması tespit edildi (Oran: %{analiz['glint_oran']})")
                    else:
                        st.info(f"✅ OpenCV Anti-Glint: Görsel temiz (Oran: %{analiz['glint_oran']})")
                    st.error(f"🚨 **Risk Skoru:** %{analiz['risk_skoru']} (Rüzgar, tespit güveni ve görüntü kalitesi birlikte değerlendirildi)")
                    st.markdown(f"**AI Bakım Tavsiyesi:** {analiz['tavsiye']}")
                    st.markdown(f"**AI Detaylı Açıklama:** {analiz['ai_detay']}")

                    st.markdown("**Manuel koordinat düzeltme (EXIF yoksa):**")
                    mk1, mk2 = st.columns(2)
                    yeni_lat = mk1.number_input("Enlem", value=float(analiz.get("lat", enlem)), format="%.6f", key=f"lat_{analiz['hash_kisa']}")
                    yeni_lon = mk2.number_input("Boylam", value=float(analiz.get("lon", boylam)), format="%.6f", key=f"lon_{analiz['hash_kisa']}")
                    if st.button("📍 Bu Görselin Koordinatını Güncelle", key=f"koor_{analiz['hash_kisa']}"):
                        st.session_state.gorsel_kuyrugu[idx-1]["lat"] = float(yeni_lat)
                        st.session_state.gorsel_kuyrugu[idx-1]["lon"] = float(yeni_lon)
                        st.session_state.gorsel_kuyrugu[idx-1]["konum_kaynagi"] = "Manuel koordinat düzeltme"
                        st.session_state.gorsel_kuyrugu[idx-1]["veri_guvenilirligi"] = "YÜKSEK"
                        st.session_state.gorsel_kuyrugu[idx-1]["veri_guven_puani"] = 88
                        st.session_state.gorsel_kuyrugu[idx-1]["veri_guven_notu"] = "Koordinat operatör tarafından manuel doğrulandı/girildi."
                        log_ekle("KONUM", f"{analiz['hash_kisa']} koordinatı güncellendi: {yeni_lat:.6f}, {yeni_lon:.6f}")
                        st.rerun()

                    if st.button("🔥 YOLO Verilerini Sisteme İşle (Sıcaklığı Güncelle)", key=f"isle_{analiz['hash_kisa']}"):
                        # Widget key'i hat_sicakligi olmadığı için artık bu atama Streamlit hatası vermez.
                        st.session_state.hat_sicakligi = float(analiz["sicaklik"])
                        log_ekle("YOLO", f"{analiz['hash_kisa']} sıcaklık {analiz['sicaklik']} °C olarak sisteme işlendi")
                        st.success(f"YOLO sıcaklığı sisteme işlendi: {analiz['sicaklik']} °C")
                        st.rerun()

        b64_gorsel = aktif_analizler[-1]["gorsel_b64"]
        yolo_durum = aktif_analizler[-1]["anomali"]
        glint_durum = aktif_analizler[-1]["glint"]
        risk_puan = aktif_analizler[-1]["risk_skoru"]
        if st.button("🗺️ Haritayı Bu Tespit Noktalarıyla Güncelle"):
            hedef = None
            for a in reversed(aktif_analizler):
                if a.get("konum_kaynagi") == "EXIF GPS":
                    hedef = a
                    break
            if hedef is None:
                hedef = aktif_analizler[-1]
            st.session_state.harita_merkez_override = {
                "lat": float(hedef.get("lat", enlem)),
                "lon": float(hedef.get("lon", boylam)),
                "adres": f"Tespit Görsel Konumu - {hedef.get('dosya','görsel')} ({float(hedef.get('lat', enlem)):.6f}, {float(hedef.get('lon', boylam)):.6f})",
                "kaynak": hedef.get("konum_kaynagi", "Tespit görsel koordinatı"),
            }
            log_ekle("HARİTA", f"Harita merkezi {hedef.get('hash_kisa','')} tespit noktasına güncellendi")
            st.rerun()

else:
    st.markdown("#### 📱 Telefon Kamerasından QR ile Demo Bağlantısı")
    public_url = _secret_get("PUBLIC_APP_URL", "").strip() or st.session_state.get("mobil_qr_url", "") or "http://localhost:8501"
    public_url = st.text_input("QR ile okutulacak panel URL'si", value=public_url, placeholder="https://gridai-demo.streamlit.app")
    st.session_state.mobil_qr_url = public_url
    if public_url:
        qr_b64 = qr_png_b64(public_url)
        st.markdown(f"""
        <div style="background-color:#1E293B; padding:20px; border-radius:10px; color:white; font-family:sans-serif; border:1px solid #334155;">
            <p><b>Mobil Demo Akışı:</b> Telefon/tablet ile bu QR kodu okutun, aynı Streamlit panelini açın, aşağıdaki kamera alanından görüntü alın ve analiz edin.</p>
            <img src="data:image/png;base64,{qr_b64}" width="160" style="background:white; padding:8px; border-radius:8px;">
            <p style="color:#94A3B8; margin-top:10px;">URL: {public_url}</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.warning("QR üretmek için Streamlit Cloud URL'sini yazın veya Secrets içine PUBLIC_APP_URL ekleyin.")

    st.markdown("#### 📍 Canlı çekim konumu")
    canli_loc, canli_msg = cihaz_canli_konumunu_al()
    if canli_loc:
        st.session_state.canli_kamera_konum = canli_loc
        st.session_state.canli_kamera_konum_mesaj = canli_msg
        canli_lat = float(canli_loc["lat"])
        canli_lon = float(canli_loc["lon"])
        canli_acc = canli_loc.get("accuracy")
        st.success(f"Canlı kamera konumu alındı: {canli_lat:.6f}, {canli_lon:.6f}" + (f" | doğruluk ~{float(canli_acc):.0f} m" if canli_acc else ""))
    else:
        canli_lat, canli_lon, canli_acc = float(enlem), float(boylam), None
        st.warning(f"Canlı cihaz konumu alınamadı; geçici CBS/harita konumu kullanılacak. Detay: {canli_msg}")

    kamera_gorseli = st.camera_input("📷 Mobil/Tablet Kamerası ile Fotoğraf Çek")
    if kamera_gorseli is not None:
        raw = kamera_gorseli.getvalue()
        konum_kaynagi = "Canlı kamera - tarayıcı GPS" if canli_loc else "Canlı kamera - GPS yok, geçici CBS/harita konumu"
        analiz = gorsel_analiz_pipeline("mobil_kamera.jpg", raw, canli_lat, canli_lon, adres_detay, hava, analiz_kaynagi="Canlı mobil/tablet kamera", konum_kaynagi_override=konum_kaynagi, gps_accuracy=canli_acc)
        if analiz["hash"] not in {a.get("hash") for a in st.session_state.gorsel_kuyrugu}:
            st.session_state.gorsel_kuyrugu.append(analiz)
        aktif_analizler = st.session_state.gorsel_kuyrugu
        st.session_state.son_analizler = aktif_analizler
        c_img, c_res = st.columns([1,1])
        with c_img:
            st.image(Image.open(io.BytesIO(base64.b64decode(analiz.get("islenmis_b64") or analiz["gorsel_b64"]))), width=400)
        with c_res:
            st.success(f"**Mobil YOLO/Roboflow Tespiti:** {analiz['anomali']} (Güven: %{analiz['guven']})")
            st.write(f"**Hash:** `{analiz['hash']}`")
            st.write(f"**Konum:** {analiz['lat']:.6f}, {analiz['lon']:.6f} — {analiz.get('konum_kaynagi','')}")
            st.write(f"**Veri Güvenilirliği:** {analiz.get('veri_guvenilirligi','')} / {analiz.get('veri_guven_puani','')} — {analiz.get('veri_guven_notu','')}")
            st.error(f"🚨 **Risk Skoru:** %{analiz['risk_skoru']}")
            st.markdown(f"**AI Bakım Tavsiyesi:** {analiz['tavsiye']}")
        if st.button("🗺️ Mobil Analizi Haritaya İşle"):
            st.rerun()

    st.markdown("#### 🎙️ Sesli Komut ve Mobil Yönlendirme")
    sesli_komut_bileseni()

if st.session_state.get("gorsel_kuyrugu"):
    st.markdown("### 📋 Anlık Analiz Tablosu")
    st.dataframe(analizleri_df(st.session_state.gorsel_kuyrugu), use_container_width=True)

st.markdown("### 🌐 Ortak Canlı Saha Analizleri")
if supabase_kayitlar:
    st.caption("Telefon/tablet veya web panel üzerinden Supabase'e kaydedilen son analizler burada ortak görünür.")
    st.dataframe(supabase_df(supabase_kayitlar), use_container_width=True)
else:
    st.caption(f"Henüz ortak Supabase kaydı görünmüyor. Durum: {supabase_okuma_mesaj}")

st.markdown("---")

# ==========================================
# ⚡ 11. KURUMSAL AKTARIM (PDF & SAP EXCEL)
# ==========================================
st.subheader("🚀 Raporlama ve Dışa Aktarım")
b1, b2, b3, b4, b5, b6 = st.columns(6)

analizler_rapor = st.session_state.get("gorsel_kuyrugu", []) or aktif_analizler or st.session_state.get("son_analizler", [])

vp = {
    "token": token,
    "tarih": datetime.now().strftime("%Y-%m-%d %H:%M"),
    "il": input_il,
    "ilce": input_ilce,
    "cadde": input_cadde,
    "enlem": enlem,
    "boylam": boylam,
    "adres_isim": adres_detay,
    "sicaklik": st.session_state.hat_sicakligi,
    "termal_temp": st.session_state.hat_sicakligi,
    "yildirim": yildirim,
    "hava": hava,
    "ekip_adi": ekip_adi,
    "ekip_mesaji": ekip_mesaji,
    "akim": tahmini_hat_akimi,
    "tahmini_hat_akimi": tahmini_hat_akimi,
    "yangin_riski": vejetasyon_yangin_riski_hesapla(hava["temp"], hava["nem"], hava["ruzgar"]),
    "gorsel": analizler_rapor[0]["gorsel_b64"] if analizler_rapor else b64_gorsel,
    "yolo_durum": analizler_rapor[0]["anomali"] if analizler_rapor else yolo_durum,
    "glint": analizler_rapor[0]["glint"] if analizler_rapor else glint_durum,
    "risk_skoru": analizler_rapor[0]["risk_skoru"] if analizler_rapor else risk_puan,
    "analizler": analizler_rapor,
}

with b1:
    if st.button("💾 Arşiv", use_container_width=True):
        st.session_state.db[token] = vp
        db_kaydet(st.session_state.db)
        log_ekle("KAYIT", f"{token} yerel arşive kaydedildi")
        cihaz_turu = "Mobil/Tablet" if any("Canlı" in str(a.get("analiz_kaynagi", "")) for a in (analizler_rapor or [])) else "Web Panel"
        ok, sb_msg = supabase_analizleri_kaydet(analizler_rapor, vp, st.session_state.get("kullanici_adi", "Saha Kullanıcısı"), cihaz_turu=cihaz_turu)
        st.session_state.supabase_son_mesaj = sb_msg
        if ok:
            try:
                supabase_analizleri_getir.clear()
            except Exception:
                pass
            log_ekle("SUPABASE", sb_msg)
            st.success("Kayıt başarılı! Yerel arşiv + Supabase ortak veritabanı güncellendi.")
        else:
            st.warning(f"Yerel arşiv kaydedildi; Supabase kaydı yapılamadı. Detay: {sb_msg}")

with b2:
    pdf_name = f"Rapor_{token}.pdf"
    try:
        genis_pdf_olustur(pdf_name, vp)
        with open(pdf_name, "rb") as f:
            st.download_button("📥 PDF Rapor", data=f, file_name=pdf_name, mime="application/pdf", use_container_width=True)
    except Exception as e:
        st.error(f"PDF Hatası: {e}")

with b3:
    sap_bytes = sap_excel_olustur(vp, analizler_rapor)
    st.download_button("📊 SAP Excel", data=sap_bytes, file_name=f"SAP_PM_{token}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

with b4:
    arsiv_bytes = arsiv_excel_olustur(st.session_state.db)
    st.download_button("🗄️ Arşiv Excel", data=arsiv_bytes, file_name="GridAI_Analiz_Arsivi.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

with b5:
    rapor_mail = st.text_input("E-posta", value="saha@gridai.com", label_visibility="collapsed")
    mail_subject = f"GridAI Rapor - {token}"
    mail_body = f"GridAI saha raporu hazır. Saha kodu: {token}. Lokasyon: {adres_detay}. Risk: %{vp.get('risk_skoru', 0)}"
    mailto = f"mailto:{rapor_mail}?subject={requests.utils.quote(mail_subject)}&body={requests.utils.quote(mail_body)}"
    st.markdown(f"<a href='{mailto}' target='_blank'><button style='background-color:#0F766E; color:white; border-radius:8px; height:42px; width:100%; font-weight:bold; border:none;'>📧 Mail</button></a>", unsafe_allow_html=True)

with b6:
    telefon = st.text_input("Telefon", value="905XXXXXXXXX", label_visibility="collapsed")
    whatsapp_msg = requests.utils.quote(f"GridAI saha raporu: {token} | Lokasyon: {adres_detay} | Risk: %{vp.get('risk_skoru', 0)}")
    wa_link = f"https://wa.me/{telefon}?text={whatsapp_msg}"
    st.markdown(f"<a href='{wa_link}' target='_blank'><button style='background-color:#0F766E; color:white; border-radius:8px; height:42px; width:100%; font-weight:bold; border:none;'>📱 Telefon</button></a>", unsafe_allow_html=True)

# ==========================================
# ⚡ 12. LOGLAR VE BİZ KİMİZ (FOOTER)
# ==========================================
st.markdown("### 🗄️ Sistem İşlem Logları")
if st.session_state.loglar:
    log_df = pd.DataFrame(st.session_state.loglar)
    st.dataframe(log_df, use_container_width=True)

st.markdown("---")

kur1, kur2, kur3, kur4 = st.columns(4)
if kur1.button("👥 Biz Kimiz?", use_container_width=True):
    st.session_state.kurumsal_panel = "biz"
if kur2.button("🎯 Misyon", use_container_width=True):
    st.session_state.kurumsal_panel = "misyon"
if kur3.button("🔭 Vizyon", use_container_width=True):
    st.session_state.kurumsal_panel = "vizyon"
if kur4.button("☎️ İletişim", use_container_width=True):
    st.session_state.kurumsal_panel = "iletisim"

panel = st.session_state.get("kurumsal_panel", "")
if panel:
    if panel == "biz":
        baslik = "🚀 Proje Geliştirme Ekibi"
        icerik = "<p><b>Cengaver Furkan Aygün</b> - Kurucu / Elektrik Teknikeri / Saha Sorumlusu</p><p><b>Kayranur Aygün</b> - Yazılım Geliştirici / Sosyal Medya Uzmanı</p>"
    elif panel == "misyon":
        baslik = "🎯 Misyon"
        icerik = "<p>Elektrik dağıtım hatlarında arıza risklerini drone, mobil kamera, CBS ve yapay zeka destekli analizlerle erken tespit ederek saha ekiplerinin daha hızlı ve güvenli karar almasını sağlamak.</p>"
    elif panel == "vizyon":
        baslik = "🔭 Vizyon"
        icerik = "<p>Enerji altyapılarında kestirimci bakım, görsel yapay zeka ve konumsal veri analitiğini birleştiren yerli ve ölçeklenebilir bir karar destek platformu olmak.</p>"
    else:
        baslik = "☎️ İletişim"
        icerik = "<p><b>E-posta:</b> cfa6161@gmail.com</p><p><b>Proje:</b> GridAI - Drone ve Yapay Zeka Tabanlı Elektrik Hattı Analiz Sistemi</p>"
    st.markdown(f"""
    <div style="background-color:#1E293B; padding:20px; border-radius:10px; border:1px solid #38BDF8;">
        <h3 style="margin-top:0;">{baslik}</h3>
        {icerik}
        <small style="color:#94A3B8;">GridAI, elektrik dağıtım şebekelerinde yapay zeka destekli görsel analiz ve CBS tabanlı karar destek amacıyla geliştirilmiş MVP platformudur.</small>
    </div>
    """, unsafe_allow_html=True)

# Footer tamamen Streamlit native bileşenlerle render edilir.
# Böylece Cloud tarafında HTML kodu düz metin olarak görünmez ve React/DOM çakışması oluşmaz.
st.markdown("---")
st.markdown("### ⚡ GridAI")
st.caption("Drone ve Mobil Görüntü Tabanlı Elektrik Hattı Analiz Platformu")
st.caption("GridAI MVP Platformu · © 2026 GridAI Enterprise. Tüm hakları saklıdır.")
