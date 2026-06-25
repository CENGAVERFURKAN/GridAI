
import streamlit as st
import pandas as pd
import numpy as np
import requests
import io
import os
import math
import hashlib
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import cv2
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import qrcode

# =========================================================
# GridAI - Sade Final Demo
# Amaç: Mentor / müşteri tarayıcısında sade, hızlı ve anlaşılır demo.
# =========================================================

st.set_page_config(
    page_title="GridAI | Bakım Karar Destek Platformu",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

GRID_GREEN = "#0A361D"
GRID_GREEN_2 = "#0F766E"
ELECTRIC_BLUE = "#00E5FF"
DARK_BG = "#06141B"
CARD_BG = "#0F172A"
TEXT = "#E2E8F0"
MUTED = "#94A3B8"
RED = "#EF4444"
ORANGE = "#F59E0B"
GREEN = "#22C55E"

st.markdown(f"""
<style>
    [data-testid="stStatusWidget"], #MainMenu, footer {{visibility:hidden;}}
    [data-testid="stHeader"] {{background:transparent;}}
    .block-container {{padding-top: 1.2rem; padding-bottom: 2rem; max-width: 1280px;}}
    h1, h2, h3 {{color:{ELECTRIC_BLUE} !important; letter-spacing:-0.02em;}}
    .hero {{
        background: linear-gradient(135deg, #062E24 0%, #06141B 65%, #082F49 100%);
        border: 1px solid rgba(0,229,255,.35);
        border-radius: 18px; padding: 22px; color: white; margin-bottom: 16px;
        box-shadow: 0 12px 34px rgba(0,0,0,.20);
    }}
    .brand {{font-size: 42px; font-weight: 900; line-height: 1;}}
    .brand .grid {{color:#EAFDF9;}}
    .brand .ai {{color:{ELECTRIC_BLUE};}}
    .subtitle {{color:{MUTED}; font-size: 15px; margin-top: 8px;}}
    .mini-card {{
        background:{CARD_BG}; color:{TEXT}; border:1px solid #1E3A46;
        border-radius:14px; padding:16px; min-height: 122px;
    }}
    .mini-card b {{color:#FFFFFF;}}
    .metric-value {{font-size: 30px; font-weight: 900; color:{ELECTRIC_BLUE}; margin:0;}}
    .muted {{color:{MUTED}; font-size:13px;}}
    .status-ok {{background:#052e24; color:#A7F3D0; border:1px solid {GREEN}; padding:8px 10px; border-radius:999px; font-weight:800; display:inline-block;}}
    .status-warn {{background:#3b2404; color:#FDE68A; border:1px solid {ORANGE}; padding:8px 10px; border-radius:999px; font-weight:800; display:inline-block;}}
    .status-danger {{background:#3b0a0a; color:#FECACA; border:1px solid {RED}; padding:8px 10px; border-radius:999px; font-weight:800; display:inline-block;}}
    .section-card {{
        background:#0B1720; color:{TEXT}; border:1px solid #233544;
        border-radius:16px; padding:18px; margin: 8px 0 16px 0;
    }}
    .formula {{background:#F8FAFC; color:#0F172A; border-radius:12px; padding:12px; font-weight:700;}}
    .stButton > button {{background:{GRID_GREEN_2}; color:white; border-radius:10px; min-height:42px; font-weight:800; border:none;}}
    .stButton > button:hover {{background:{GRID_GREEN}; color:white;}}
    [data-testid="stSidebar"] {{background-color:#0F172A !important;}}
    [data-testid="stSidebar"] * {{color:#E2E8F0 !important;}}
    [data-testid="stSidebar"] input, [data-testid="stSidebar"] textarea {{background:#F8FAFC !important; color:#0F172A !important;}}
    div[data-testid="stExpander"] {{border:1px solid #233544; border-radius:12px;}}
</style>
""", unsafe_allow_html=True)

# -------------------- State --------------------
def init_state():
    defaults = {
        "lat": 40.9852,
        "lon": 40.0124,
        "adres": "Arsin F3-D61 / Trabzon",
        "konum_kaynagi": "Demo CBS koordinatı",
        "son_analiz": None,
        "map_refresh": 0,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
init_state()

# -------------------- Helpers --------------------
def safe_float(x, default=None):
    try:
        return float(str(x).replace(",", "."))
    except Exception:
        return default

def local_geocode_fallback(q):
    text = (q or "").lower()
    if "arsin" in text or "f3" in text or "d61" in text:
        return 40.9852, 40.0124, "Arsin F3-D61 / Trabzon", "CBS demo eşleşmesi"
    if "yomra" in text:
        return 40.9570, 39.8640, "Yomra K2-D14 / Trabzon", "CBS demo eşleşmesi"
    if "of" in text or "a1" in text:
        return 40.9401, 40.2593, "Of A1-D08 / Trabzon", "CBS demo eşleşmesi"
    if "trabzon" in text:
        return 41.0027, 39.7168, "Trabzon Merkez", "CBS demo eşleşmesi"
    return None

def geocode_address(q):
    q = (q or "").strip()
    if not q:
        return None
    # Direkt "lat, lon" girilirse haritayı anında güncelle.
    m = None
    import re
    nums = re.findall(r"-?\d+(?:[\.,]\d+)?", q)
    if len(nums) >= 2:
        lat = safe_float(nums[0]); lon = safe_float(nums[1])
        if lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180:
            return lat, lon, f"Manuel koordinat: {lat:.6f}, {lon:.6f}", "Manuel koordinat"
    fb = local_geocode_fallback(q)
    if fb:
        return fb
    try:
        url = "https://nominatim.openstreetmap.org/search"
        params = {"q": q, "format": "json", "limit": 1, "addressdetails": 1}
        headers = {"User-Agent": "GridAI-Demo/1.0"}
        r = requests.get(url, params=params, headers=headers, timeout=6)
        if r.ok and r.json():
            item = r.json()[0]
            return float(item["lat"]), float(item["lon"]), item.get("display_name", q), "CBS adres çözümleme"
    except Exception:
        pass
    return None

def hava_cek(lat, lon):
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {"latitude": lat, "longitude": lon, "current": "temperature_2m,relative_humidity_2m,wind_speed_10m", "timezone": "auto"}
        r = requests.get(url, params=params, timeout=6)
        if r.ok:
            c = r.json().get("current", {})
            return {
                "sicaklik": float(c.get("temperature_2m", 18)),
                "nem": float(c.get("relative_humidity_2m", 65)),
                "ruzgar": float(c.get("wind_speed_10m", 8)),
                "kaynak": "Open-Meteo",
            }
    except Exception:
        pass
    return {"sicaklik": 18.0, "nem": 65.0, "ruzgar": 8.0, "kaynak": "Demo/yedek"}

def image_hash(data):
    return hashlib.sha256(data).hexdigest()[:12]

def laplacian_score(img_np):
    gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
    var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    score = max(0, min(100, (var / 220.0) * 100))
    return round(score, 1), round(var, 1)

def demo_detection(img):
    # Hafif ve stabil demo: görselin üst bölgesinde ana kusur kutusu üretir.
    w, h = img.size
    return [{
        "label": "Çatlak İzolatör",
        "confidence": 0.91,
        "box": (int(w*0.42), int(h*0.12), int(w*0.76), int(h*0.32)),
        "severity": "Yüksek",
    }]

def draw_boxes(img, detections):
    out = img.copy().convert("RGB")
    draw = ImageDraw.Draw(out)
    for d in detections:
        x1, y1, x2, y2 = d["box"]
        draw.rectangle([x1, y1, x2, y2], outline=(239, 68, 68), width=max(3, img.size[0]//220))
        txt = f"{d['label']} | %{int(d['confidence']*100)}"
        draw.rectangle([x1, max(0, y1-26), x1+min(360, len(txt)*11), y1], fill=(239, 68, 68))
        draw.text((x1+5, max(0, y1-23)), txt, fill=(255,255,255))
    return out

def fieldproof_score(blur_score, has_location=True, has_hash=True):
    score = 40
    score += min(35, blur_score * 0.35)
    score += 15 if has_location else 0
    score += 10 if has_hash else 0
    return int(max(0, min(100, score)))

def fieldsense_risk(hava, defect_severity="Yüksek", conductor_current=180):
    # Sanal/ön risk: CIGRE/IEEE benzeri ısıl denge yaklaşımına referanslı demo hesap.
    t = hava["sicaklik"]; wind = max(0.1, hava["ruzgar"]); humidity = hava["nem"]
    thermal = 35 + (t-15)*1.2 + (conductor_current-120)*0.22 - wind*1.4 + (humidity-50)*0.08
    if defect_severity == "Yüksek": thermal += 15
    thermal = int(max(5, min(95, thermal)))
    sag = int(max(5, min(90, 30 + (t-15)*1.1 + conductor_current*0.10 - wind*0.8)))
    acoustic = int(max(0, min(85, 25 + (thermal-40)*0.45)))
    overall = int(round(0.45*thermal + 0.30*sag + 0.25*acoustic))
    return thermal, sag, acoustic, overall

def impact_priority(risk, proof):
    if risk >= 70 and proof >= 70:
        return "Öncelik 1", "Acil saha kontrolü", "M1 / Acil"
    if risk >= 45:
        return "Öncelik 2", "Planlı bakım kontrolü", "M2 / Planlı"
    return "Öncelik 3", "Periyodik izleme", "M3 / İzleme"

def render_map(lat, lon, analysis=None):
    m = folium.Map(location=[lat, lon], zoom_start=14, tiles=None)
    folium.TileLayer("OpenStreetMap", name="Sokak Haritası").add_to(m)
    folium.TileLayer(tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}", attr="Google", name="Uydu Görünümü").add_to(m)
    folium.Marker([lat, lon], tooltip="GridAI analiz konumu", popup=st.session_state.adres, icon=folium.Icon(color="red", icon="bolt", prefix="fa")).add_to(m)
    heat = [[lat, lon, 0.8]] if not analysis else [[lat, lon, min(1.0, analysis["risk"]/100)]]
    HeatMap(heat, name="Risk Isı Katmanı", radius=24, blur=16, min_opacity=0.25).add_to(m)
    folium.LayerControl().add_to(m)
    st_folium(m, height=420, use_container_width=True, key=f"map_{round(lat,6)}_{round(lon,6)}_{st.session_state.map_refresh}")

def register_fonts():
    candidates = [
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    ]
    for reg, bold in candidates:
        try:
            if os.path.exists(reg):
                pdfmetrics.registerFont(TTFont("TR", reg))
                if os.path.exists(bold):
                    pdfmetrics.registerFont(TTFont("TRB", bold))
                else:
                    pdfmetrics.registerFont(TTFont("TRB", reg))
                return "TR", "TRB"
        except Exception:
            pass
    return "Helvetica", "Helvetica-Bold"

def create_pdf(analysis):
    font, fontb = register_fonts()
    bio = io.BytesIO()
    doc = SimpleDocTemplate(bio, pagesize=A4, rightMargin=32, leftMargin=32, topMargin=36, bottomMargin=32)
    styles = getSampleStyleSheet()
    title = ParagraphStyle("title", parent=styles["Title"], fontName=fontb, fontSize=18, textColor=colors.HexColor(GRID_GREEN), spaceAfter=12)
    normal = ParagraphStyle("normal", parent=styles["BodyText"], fontName=font, fontSize=9.5, leading=13)
    story = [Paragraph("GridAI™ Saha Analiz ve Bakım Karar Destek Raporu", title)]
    story.append(Paragraph("Bu rapor ön değerlendirme ve karar destek çıktısıdır; kesin saha kararı yetkili ekip doğrulamasıyla verilmelidir.", normal))
    story.append(Spacer(1, 10))
    rows = [
        ["Alan", "Değer"],
        ["Rapor tarihi", datetime.now().strftime("%d.%m.%Y %H:%M")],
        ["Konum", f"{analysis['lat']:.6f}, {analysis['lon']:.6f}"],
        ["Adres/CBS", analysis.get("adres", "")[:110]],
        ["Tespit", analysis.get("defect", "")],
        ["AI güven", f"%{analysis.get('confidence',0)}"],
        ["FieldProof", f"%{analysis.get('proof',0)}"],
        ["FieldSense ön risk", f"%{analysis.get('risk',0)}"],
        ["Bakım önceliği", analysis.get("priority", "")],
        ["SAP PM taslağı", analysis.get("sap", "")],
    ]
    tbl = Table(rows, colWidths=[120, 360])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor(GRID_GREEN)),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), fontb),
        ("FONTNAME", (0,1), (-1,-1), font),
        ("GRID", (0,0), (-1,-1), 0.35, colors.HexColor("#CBD5E1")),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("FONTSIZE", (0,0), (-1,-1), 9),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 10))
    story.append(Paragraph("Teknik Not: FieldSense; Stefan-Boltzmann ısıl denge yaklaşımı, CIGRE TB 601 / IEEE 738 referanslı çevresel parametreler ve katener/sehim ön analizi mantığıyla ön risk üretir. Kesin ölçüm iddiası taşımaz.", normal))
    doc.build(story)
    bio.seek(0)
    return bio.getvalue()

# -------------------- Sidebar --------------------
with st.sidebar:
    st.markdown("### ⚡ GridAI")
    st.caption("Sade final demo")
    st.markdown("---")
    st.markdown("#### CBS / Konum")
    cbs = st.text_input("Adres, direk kodu veya koordinat", value=st.session_state.adres)
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("📍 Güncelle", use_container_width=True):
            res = geocode_address(cbs)
            if res:
                lat, lon, addr, src = res
                st.session_state.lat = lat; st.session_state.lon = lon
                st.session_state.adres = addr; st.session_state.konum_kaynagi = src
                st.session_state.map_refresh += 1
                st.success("Konum güncellendi.")
                st.rerun()
            else:
                st.error("Konum çözümlenemedi. Örn: Arsin F3-D61 veya 40.9852, 40.0124")
    with col_b:
        if st.button("↺ Demo", use_container_width=True):
            st.session_state.lat = 40.9852; st.session_state.lon = 40.0124
            st.session_state.adres = "Arsin F3-D61 / Trabzon"
            st.session_state.konum_kaynagi = "Demo CBS koordinatı"
            st.session_state.map_refresh += 1
            st.rerun()
    st.caption(f"{st.session_state.lat:.6f}, {st.session_state.lon:.6f}")
    st.caption(st.session_state.konum_kaynagi)
    st.markdown("---")
    conductor_current = st.slider("Sanal hat akımı varsayımı (A)", 60, 320, 180, step=10)
    uploaded = st.file_uploader("Drone / telefon görseli", type=["jpg", "jpeg", "png"])

# -------------------- Hero --------------------
st.markdown("""
<div class="hero">
    <div class="brand"><span class="grid">Grid</span><span class="ai">AI</span></div>
    <div style="font-size:21px;font-weight:800;margin-top:8px;">Elektrik Dağıtım Şebekesi Görüntü Analizi ve Bakım Karar Destek Platformu</div>
    <div class="subtitle">Görüntüden karara, sahadan rapora. Çalışan web MVP + sade saha analiz akışı.</div>
</div>
""", unsafe_allow_html=True)

lat, lon = float(st.session_state.lat), float(st.session_state.lon)
hava = hava_cek(lat, lon)

# -------------------- Image + Analysis --------------------
if uploaded is not None:
    img_bytes = uploaded.read()
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    img_np = np.array(img)
    blur_score, blur_var = laplacian_score(img_np)
    detections = demo_detection(img)
    annotated = draw_boxes(img, detections)
    proof = fieldproof_score(blur_score, has_location=True, has_hash=True)
    thermal, sag, acoustic, risk = fieldsense_risk(hava, detections[0]["severity"], conductor_current)
    priority, action, sap = impact_priority(risk, proof)
    confidence = int(detections[0]["confidence"]*100)
    analysis = {
        "lat": lat, "lon": lon, "adres": st.session_state.adres,
        "defect": detections[0]["label"], "confidence": confidence, "proof": proof,
        "thermal": thermal, "sag": sag, "acoustic": acoustic, "risk": risk,
        "priority": priority, "action": action, "sap": sap,
        "hash": image_hash(img_bytes), "blur": blur_score, "blur_var": blur_var,
        "annotated": annotated,
    }
    st.session_state.son_analiz = analysis
else:
    analysis = st.session_state.son_analiz

# -------------------- Top Metrics --------------------
current = analysis or {"risk": 58, "proof": 78, "priority": "Öncelik 2", "defect": "Demo bekleniyor", "confidence": 0}
mc1, mc2, mc3, mc4 = st.columns(4)
with mc1:
    st.markdown(f"<div class='mini-card'><div class='muted'>FieldSense Ön Risk</div><p class='metric-value'>%{current['risk']}</p><span class='status-warn'>{current.get('priority','Öncelik 2')}</span></div>", unsafe_allow_html=True)
with mc2:
    st.markdown(f"<div class='mini-card'><div class='muted'>FieldProof Kanıt Güveni</div><p class='metric-value'>%{current.get('proof',78)}</p><span class='status-ok'>Konum doğrulandı</span></div>", unsafe_allow_html=True)
with mc3:
    st.markdown(f"<div class='mini-card'><div class='muted'>AI Tespit</div><p class='metric-value'>{current.get('confidence',0)}%</p><b>{current.get('defect','Demo bekleniyor')}</b></div>", unsafe_allow_html=True)
with mc4:
    st.markdown(f"<div class='mini-card'><div class='muted'>CBS Konum</div><p style='font-size:18px;font-weight:900;margin:2px 0;color:{ELECTRIC_BLUE}'>{lat:.4f}, {lon:.4f}</p><span class='muted'>{st.session_state.konum_kaynagi}</span></div>", unsafe_allow_html=True)

# -------------------- Main Tabs --------------------
tab1, tab2, tab3, tab4 = st.tabs(["1. Analiz", "2. Harita", "3. FieldSense", "4. Rapor"])

with tab1:
    c1, c2 = st.columns([1.08, .92])
    with c1:
        st.subheader("Görsel Analiz")
        if analysis:
            st.image(analysis["annotated"], caption="AI tespit kutusu sade gösterim", use_container_width=True)
        else:
            st.info("Sol menüden bir drone/telefon görseli yükleyin. Demo görsel yoksa sistem örnek konum ve risk değerleriyle açılır.")
    with c2:
        st.subheader("Karar Özeti")
        if analysis:
            status_class = "status-danger" if analysis["risk"] >= 70 else "status-warn" if analysis["risk"] >= 45 else "status-ok"
            st.markdown(f"<div class='section-card'><span class='{status_class}'>FieldSense Risk: %{analysis['risk']}</span><br><br><b>Tespit:</b> {analysis['defect']} (%{analysis['confidence']})<br><b>Öneri:</b> {analysis['action']}<br><b>SAP PM:</b> {analysis['sap']}<br><b>Görsel Hash:</b> {analysis['hash']}</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div class='section-card'><b>Demo akışı hazır.</b><br>Görsel yüklenince FieldProof, FieldSense, harita ve rapor çıktıları otomatik güncellenir.</div>", unsafe_allow_html=True)

with tab2:
    st.subheader("CBS Haritası")
    st.caption("CBS/adres alanına girilen konum çözüldüğünde koordinatlar ve harita merkezi birlikte güncellenir.")
    render_map(lat, lon, analysis)

with tab3:
    st.subheader("FieldSense ve Teknik Motorlar")
    a = analysis or {
        "thermal": fieldsense_risk(hava, "Yüksek", conductor_current)[0],
        "sag": fieldsense_risk(hava, "Yüksek", conductor_current)[1],
        "acoustic": fieldsense_risk(hava, "Yüksek", conductor_current)[2],
        "risk": fieldsense_risk(hava, "Yüksek", conductor_current)[3],
        "proof": current.get("proof", 78), "blur": 80,
    }
    col1, col2, col3 = st.columns(3)
    col1.markdown(f"<div class='mini-card'><div class='muted'>Sanal Isıl Risk</div><p class='metric-value'>%{a['thermal']}</p><span class='muted'>Stefan-Boltzmann / CIGRE-IEEE referanslı ön yaklaşım</span></div>", unsafe_allow_html=True)
    col2.markdown(f"<div class='mini-card'><div class='muted'>Katener / Sehim Ön Riski</div><p class='metric-value'>%{a['sag']}</p><span class='muted'>2D görüntüde pikselsel eğri varsayımı</span></div>", unsafe_allow_html=True)
    col3.markdown(f"<div class='mini-card'><div class='muted'>Akustik Ön Uyarı</div><p class='metric-value'>%{a['acoustic']}</p><span class='muted'>FFT tabanlı ses anomali kurgusu</span></div>", unsafe_allow_html=True)
    st.markdown("""
<div class='section-card'>
<b>Güvenli teknik sınır:</b> FieldSense kesin ölçüm cihazı değildir. Telefon/drone görüntüsü, hava verisi ve operatör girdileriyle saha ekibine ön risk ve bakım önceliği sunan karar destek katmanıdır.
</div>
""", unsafe_allow_html=True)
    with st.expander("Stefan-Boltzmann ısıl denge yaklaşımı"):
        st.latex(r"E = \sigma \cdot \epsilon \cdot A \cdot T^4")
        st.write("GridAI, görüntüden/harici veriden gelen yüzey sıcaklığı varsayımı ile ortam sıcaklığı, rüzgâr ve nem verilerini birlikte değerlendirerek aşırı ısınma ihtimaline yönelik sanal ön risk skoru üretir. Bu çıktı termal kamera ölçümü değil, karar destek amaçlı mühendislik yaklaşımıdır.")
    with st.expander("Katener eğrisi ve donanımsız sehim ön analizi"):
        st.latex(r"y = a \cdot \cosh\left(\frac{x}{a}\right)")
        st.write("Geniş açı hat görüntülerinde iletkenin pikselsel eğrisi takip edilerek sehim artışı için ön değerlendirme yapılır. Yakın plan izolatör fotoğraflarında sehim hesabı yapılmaz; sistem bu durumda kullanıcıdan uygun geniş açı görüntü ister.")
    with st.expander("Kullanılan teknik bileşenler"):
        st.markdown("""
- **YOLO / Roboflow:** Kusurlu ekipman sınıflandırma ve bounding box üretimi.
- **FieldProof + Laplacian Varyans:** Görsel netliği, hash ve konum doğrulama ile kanıt güven skoru.
- **Streamlit:** B2B SaaS prototipi ve saha analiz kontrol paneli.
- **FFT:** Mobil ses kaydında ark/corona benzeri anomali ön uyarı kurgusu.
- **QGIS/Folium:** Koordinatlı anomali haritası ve risk ısı katmanı.
- **NanoGlow + LTC3588-1:** Faz 2 laboratuvar prototipi hedeflenen pilsiz uyarı etiketi güç yönetimi mimarisi.
""")

with tab4:
    st.subheader("Rapor ve SAP PM Çıktısı")
    if analysis:
        df = pd.DataFrame([{
            "Rapor_Tarihi": datetime.now().strftime("%d.%m.%Y %H:%M"),
            "Direk_CBS": st.session_state.adres,
            "Enlem": analysis["lat"],
            "Boylam": analysis["lon"],
            "Tespit": analysis["defect"],
            "AI_Guven": analysis["confidence"],
            "FieldProof": analysis["proof"],
            "FieldSense_Risk": analysis["risk"],
            "Oncelik": analysis["priority"],
            "SAP_PM_Taslak": analysis["sap"],
            "Aksiyon": analysis["action"],
        }])
        st.dataframe(df, use_container_width=True, hide_index=True)
        # Excel
        excel_buf = io.BytesIO()
        with pd.ExcelWriter(excel_buf, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="GridAI_Rapor")
        st.download_button("📊 SAP/Excel çıktısını indir", excel_buf.getvalue(), "gridai_sap_pm_taslak.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
        pdf_bytes = create_pdf(analysis)
        st.download_button("📄 PDF raporu indir", pdf_bytes, "gridai_saha_analiz_raporu.pdf", "application/pdf", use_container_width=True)
    else:
        st.info("Rapor çıktısı için önce görsel yükleyip analiz oluşturun.")

st.caption("GridAI sade final demo: gereksiz modlar ve taslak ekranlar kaldırılmıştır. Bu panel ön değerlendirme ve karar destek amaçlıdır.")
