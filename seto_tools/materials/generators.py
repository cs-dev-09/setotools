# SPDX-License-Identifier: GPL-3.0-or-later
"""
generators.py -- Materialize'in uc donusumu, saf NumPy olarak.

Kaynak referanslari (BoundingBoxSoftware/Materialize, GPL-3):
    Assets/Shaders/Resources/Blit_Height_From_Diffuse.shader
    Assets/Shaders/Resources/Blit_Normal_From_Height.shader
    Assets/Scripts/HeightFromDiffuseGui.cs
    Assets/Scripts/NormalFromHeightGui.cs
    Assets/Scripts/SpecularGui.cs

Fonksiyonlarin hicbiri bpy bilmez; girdi ve cikti numpy dizisidir.
"""

import math

import numpy as np

from . import imageops as iops


# ------------------------------------------------------------------- height

def _final_gain(height, gain):
    """
    fragCombineHeight'in S-egrisi.

    GUI'deki -0.5..0.5 degeri once shader ussune cevrilir:
        gain < 0 -> |1 / (gain - 1)|      (0'a yaklasir, kontrasti SERTLESTIRIR)
        gain >= 0 -> gain + 1             (1'den buyur, YUMUSATIR)
    0'da us 1.0 olur, yani notrdur.
    """
    if abs(gain) < 1e-6:
        return height
    exponent = abs(1.0 / (gain - 1.0)) if gain < 0.0 else gain + 1.0

    upper = height > 0.5
    out = np.empty_like(height)
    t = np.clip(height * 2.0 - 1.0, 0.0, 1.0)
    out[upper] = (t[upper] ** exponent) * 0.5 + 0.5
    t = np.clip((1.0 - height) * 2.0 - 1.0, 0.0, 1.0)
    out[~upper] = 1.0 - ((t[~upper] ** exponent) * 0.5 + 0.5)
    return out.astype(np.float32)


# _AvgMap: BlurMap6'nin cok genis bir blur'u.
# Materialize'da _BlurSamples=32, _BlurSpread=64*extraSpread, yani Hann
# yaricapi 32*64*extraSpread piksel. Hann sigma'si yaricapin 0.3615 kati.
_AVG_SIGMA = 0.3615 * 32.0 * 64.0


def _apply_samples(lum, rgb, p, tile):
    """
    Blit_Sample.shader / fragSample.

    Ornek 2 once, ornek 1 sonra karistirilir (shader'daki sira). 'isolate'
    Materialize'da bir ONIZLEME kipidir: yukseklik yerine MASKENIN KENDISI
    gosterilir, boylece maskeyi ayarlarken ne sectigini gorursun.
    """
    samples = p["samples"]
    masks = []
    for s in samples:
        if not s["use"]:
            masks.append(None)
            continue
        m = iops.color_mask(
            rgb, s["color"],
            s["hue_weight"], s["sat_weight"], s["lum_weight"],
            s["mask_low"], s["mask_high"],
        )
        # Materialize'da yok; maskeyi yumusatmak icin ek. 0'da devre disi.
        if s["spread"] > 0.0:
            m = np.clip(iops.blur(m, s["spread"], tile) * s["spread_boost"], 0.0, 1.0)
        masks.append(m)

    if all(m is None for m in masks):
        return lum

    blend = p["sample_blend"]
    out = lum
    for idx in (1, 0):  # shader once ornek 2'yi, sonra ornek 1'i karistirir
        if masks[idx] is None:
            continue
        t = masks[idx] * blend
        out = out + (samples[idx]["height"] - out) * t
    out = np.clip(out, 0.0, 1.0)

    for idx in (0, 1):
        if masks[idx] is not None and samples[idx]["isolate"]:
            out = masks[idx]
    return out.astype(np.float32)


def height_from_diffuse(diffuse, p, tile=True):
    """
    Blit_Shader.shader / fragCombineHeight portu -- Materialize'in Height
    sekmesinin gercekte kullandigi yol.

    Seviyeler dogrudan ortalanmaz: her biri ortak bir GENIS ORTALAMADAN
    cikarilip yuksek gecirgen banda cevrilir, kontrast o bandi olcekler.
    Kontrastin negatif olabilmesinin sebebi budur -- o frekans bandini
    ters cevirir.

    Not: shader her seviyeye pow(x, 0.45) uygular; bu linear->sRGB
    donusumunun ta kendisidir ve biz zaten goruntuyu sRGB uzayinda
    okuyoruz (imageio.image_to_array), dolayisiyla burada tekrarlanmaz.

    diffuse : (h, w, 3+) float32, 0..1
    -> (h, w) float32 height
    """
    h, w = diffuse.shape[:2]
    rgb = diffuse[..., :3]

    lum = iops.luminance(rgb)

    # --- renk ornekleri: blur zincirinden ONCE uygulanir ---
    # Materialize'da Blit_Sample bir on gecistir ve ciktisi BlurMap0'dir,
    # yani ornekler butun frekans merdiveninin GIRDISINI degistirir.
    # (Onceden piramitten sonra uyguluyordum; bu yapisal bir sapmaydi.)
    lum = _apply_samples(lum, rgb, p, tile)

    if p["pre_contrast"] != 1.0:
        lum = iops.contrast_bias(lum, p["pre_contrast"], 0.0)

    spreads = [s * p["blur_spread"] for s in iops.spread_schedule(w, h)]

    # Seviye zinciri + genis ortalama
    levels = [lum]
    cur = lum
    for sigma in spreads:
        cur = iops.blur(cur, sigma, tile)
        levels.append(cur)

    extra = ((w + h) * 0.5) / 1024.0
    avg_sigma = min(_AVG_SIGMA * extra, min(h, w) * 0.5)
    avg = iops.blur(levels[-1], avg_sigma, tile)

    weights = p["blur_weight"]
    contrasts = p["blur_contrast"]
    total = float(sum(weights))
    if total <= 1e-6:
        height = np.full_like(lum, 0.5)
    else:
        acc = None
        for lvl, wgt, con in zip(levels, weights, contrasts):
            if wgt == 0.0:
                continue
            band = (lvl - avg) * con + 0.5
            acc = band * wgt if acc is None else acc + band * wgt
        height = (acc / total).astype(np.float32)

    height = np.clip(height, 0.0, 1.0)

    # SIRA: normalize once. Aralik duzenleme adimi oldugu icin sanatsal
    # ayarlardan ONCE gelmeli -- sonda calisirsa kullanicinin verdigi
    # Final Bias / Gain'i birebir geri alir ve o slider'lar olu gorunur.
    if p["normalize"]:
        # Ham min/max DEGIL: tek bir aykiri piksel butun araligi yutup
        # haritayi duzlestiriyor (bkz. imageops.robust_range).
        lo, hi = iops.robust_range(height)
        if hi - lo > 1e-5:
            height = np.clip((height - lo) / (hi - lo), 0.0, 1.0)

    height = iops.contrast_bias(height, p["final_contrast"], p["final_bias"])
    height = _final_gain(height, p["final_gain"])

    if p["invert"]:
        height = 1.0 - height

    return height.astype(np.float32)


# ------------------------------------------------------------------- normal

def _unit(v):
    """Son eksende birim uzunluga getir."""
    length = np.sqrt((v * v).sum(axis=-1, keepdims=True))
    return v / np.maximum(length, 1e-6)


def _height_to_normal(height, strength, tile=True):
    """
    Blit_Shader.shader / fragNormal'in turev kismi.
    -> (h, w, 3) float32, -1..1 birim vektor.

    Egim KOMSU PIKSEL farkindan hesaplanir, dolayisiyla ham haliyle
    cozunurluge bagimlidir. Olcekleme cagiran tarafta yapilir.
    """
    if tile:
        dx = np.roll(height, -1, axis=1) - height
        dy = np.roll(height, -1, axis=0) - height
    else:
        dx = np.empty_like(height)
        dx[:, :-1] = height[:, 1:] - height[:, :-1]
        dx[:, -1] = 0.0
        dy = np.empty_like(height)
        dy[:-1, :] = height[1:, :] - height[:-1, :]
        dy[-1, :] = 0.0

    # cross(normalize([1,0,dx*s]), normalize([0,1,dy*s])) yonu = [-dx*s, -dy*s, 1]
    n = np.stack((-dx * strength, -dy * strength, np.ones_like(height)), axis=-1)
    return _unit(n).astype(np.float32)


# Hann (yukseltilmis kosinus) penceresinin standart sapmasi yaricapin
# ~0.3615 kati. Materialize egim blur'unu 3 zincirli Hann gecisiyle yapiyor
# (spread 1, 3, 3), yani toplam sigma = 0.3615 * sqrt(1+9+9) * SlopeBlur.
_SLOPE_BLUR_SIGMA = 0.3615 * np.sqrt(19.0)


def _apply_shape_recognition(n, source, p, res_scale, tile):
    """
    fragNormal'in sekil tanima katmani.

    Yukseklik haritasinin yuksek gecirgen bandini bir 'isik yonu' boyunca
    egim olarak yorumlar. Turev tabanli normal yalnizca komsu piksel farkini
    gorur; bu katman daha genis sekilleri (tugla yuzu, tas yuvarlagi) yakalar
    ve normal'e gercek hacim kazandirir.
    """
    sigma = max(p["slope_blur"] * _SLOPE_BLUR_SIGMA * res_scale, 0.5)
    blurred = iops.blur(source, sigma, tile)

    hp = (source - blurred) + p["shape_bias"]
    hp = hp * 2.0 - 1.0

    rot = float(p["light_rotation"])
    ldx, ldy = math.sin(rot), math.cos(rot)
    # cross([ldx, ldy, 0], [0, 0, 1]) = (ldy, -ldx, 0)
    lcx, lcy = ldy, -ldx

    dot_nlc = n[..., 0] * lcx + n[..., 1] * lcy      # lightCross.z = 0
    sx = hp * ldx + dot_nlc * lcx
    sy = hp * ldy + dot_nlc * lcy
    sz = np.sqrt(np.clip(1.0 - np.clip(sx * sx + sy * sy, 0.0, 1.0), 0.0, 1.0))

    shape = _unit(np.stack((sx, sy, sz), axis=-1))
    return _unit(n + (shape - n) * p["shape_recognition"]).astype(np.float32)


def _apply_angularity(v, angularity, intensity):
    """
    fragCombineNormal'in acisallik katmani.

    Egimleri sabit bir dikklige 'kilitler': yumusak gecisler yerine
    fasetli, kesin acili bir yuzey verir. Tas duvar, metal panel gibi
    sert kirilimli yuzeylerde ise yarar.
    """
    xy = v[..., :2]
    denom = np.sqrt(xy[..., 0] ** 2 + xy[..., 1] ** 2 + 1e-6)
    ang = np.empty_like(v)
    ang[..., 0] = xy[..., 0] / denom * intensity
    ang[..., 1] = xy[..., 1] / denom * intensity
    ang[..., 2] = max(1.0 - intensity, 0.001)
    ang = _unit(ang)
    return v + (ang - v) * angularity


def normal_map(height, p, tile=True, diffuse=None):
    """
    Blit_Shader.shader'in fragNormal (pass 3) + fragCombineNormal (pass 4)
    zincirinin portu -- Materialize'in Normal sekmesinin gercekte kullandigi
    yol budur.

    Egimin okundugu alan p["source"] ile secilir:
      "DIFFUSE" -> dogrudan kaynak diffuse'un luminance'i. Height boru
                   hattinin frekans sekillendirmesinden BAGIMSIZ, dolayisiyla
                   diffuse'daki her detay normal'e gecer.
      "HEIGHT"  -> uretilen height haritasi (Materialize'in yaptigi).

    height  : (h, w) float32 -- source="HEIGHT" ise kullanilir
    diffuse : (h, w, 3+)     -- source="DIFFUSE" ya da use_diffuse icin
    -> (h, w, 3) float32, 0..1 tangent-space normal
    """
    diffuse_lum = None
    if diffuse is not None:
        diffuse_lum = iops.luminance(diffuse[..., :3])
        # Ham luminance genelde dar bir bantta durur (orn. 0.23-0.40); onu
        # dogrudan yukseklik alani gibi kullanmak height boru hattindan
        # gelen (normalize edilmis) alana gore cok zayif egim uretir ve
        # normal duz cikar. Aykiri piksellere dayanikli gerdirme ikisini
        # ayni olcege getirir.
        lo, hi = iops.robust_range(diffuse_lum)
        if hi - lo > 1e-5:
            diffuse_lum = np.clip((diffuse_lum - lo) / (hi - lo), 0.0, 1.0)

    slope_from_diffuse = p.get("source", "HEIGHT") == "DIFFUSE" and diffuse_lum is not None
    field = diffuse_lum if slope_from_diffuse else height
    if field is None:
        raise ValueError("Normal needs either a height map or a diffuse image")

    h, w = field.shape[:2]
    # Her sey 1024 referansina gore olceklenir; Processing Size'i degistirmek
    # sonucun gorunumunu degistirmemeli.
    res_scale = ((w + h) * 0.5) / 1024.0

    if slope_from_diffuse:
        # Ham diffuse'ta kenarlar her cozunurlukte 1 piksel keskin kalir,
        # yani piksel-basi egim 1/N ile olceklenmez ve res_scale duzeltmesi
        # yanlis calisir (512'de 1024'e gore ~1.6 kat guclu cikiyordu).
        # Cozunurlukle ORANTILI ince bir on bulaniklik kenar genisligini de
        # olcekler; height yolunda bunu frekans merdiveni zaten yapiyor.
        # AYNI diziyi sekil tanima da kullanmali, yoksa use_diffuse
        # source=DIFFUSE iken sessizce kucuk bir fark yaratirdi.
        diffuse_lum = iops.blur(diffuse_lum, max(res_scale, 0.35), tile)
        field = diffuse_lum

    n = _height_to_normal(field, p["strength"] * res_scale, tile)

    if p["shape_recognition"] > 0.0:
        source = field
        if p["use_diffuse"] and diffuse_lum is not None:
            source = diffuse_lum
        n = _apply_shape_recognition(n, source, p, res_scale, tile)

    base = (n * 0.5 + 0.5).astype(np.float32)

    spreads = [s * p["blur_spread"] for s in iops.spread_schedule(w, h)]
    combined = iops.pyramid_combine(base, spreads, [1.0] * 6, p["blur_weight"], tile=tile)

    v = _unit(combined * 2.0 - 1.0)

    if p["angularity"] > 0.0:
        v = _apply_angularity(v, p["angularity"], p["angular_intensity"])

    # Final kontrast normal'e 0.5 etrafinda DEGIL, XY'yi olcekleyip Z'yi
    # kuvvet alarak uygulanir -- shader boyle yapiyor ve dogrusu da bu:
    # kontrasti artirmak egimi diklestirir.
    fc = float(p["final_contrast"])
    if fc != 1.0:
        v = v.copy()
        v[..., :2] *= fc
        v[..., 2] = np.clip(v[..., 2], 0.0, 1.0) ** fc

    out = _unit(v) * 0.5 + 0.5

    if p["flip_y"]:
        out[..., 1] = 1.0 - out[..., 1]
    if p["flip_x"]:
        out[..., 0] = 1.0 - out[..., 0]

    return np.clip(out, 0.0, 1.0).astype(np.float32)


# Eski ad -- disaridan cagiran kod kirilmasin diye duruyor.
def normal_from_height(height, p, tile=True, diffuse=None):
    return normal_map(height, p, tile=tile, diffuse=diffuse)


# ----------------------------------------------------------------- specular

def _smoothstep(edge0, edge1, x):
    t = np.clip((x - edge0) / (edge1 - edge0 if abs(edge1 - edge0) > 1e-9 else 1e-9), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _vivid_light(base, alt):
    """
    Photoshop.cginc / BlendVividLightf.
        alt < 0.5 -> color burn ( 1 - (1-base)/(2*alt) )
        alt >= 0.5 -> color dodge ( base / (1 - 2*(alt-0.5)) )
    """
    a2 = 2.0 * alt
    with np.errstate(divide="ignore", invalid="ignore"):
        burn = np.where(a2 <= 1e-6, 0.0,
                        np.maximum(1.0 - (1.0 - base) / np.maximum(a2, 1e-6), 0.0))
        d2 = 2.0 * (alt - 0.5)
        dodge = np.where(d2 >= 1.0 - 1e-6, 1.0,
                         np.minimum(base / np.maximum(1.0 - d2, 1e-6), 1.0))
    return np.where(alt < 0.5, burn, dodge).astype(np.float32)


def _derive_channel(spec, base, amount, blur_px, invert, res_scale, tile):
    """
    Ana specular sinyalinden ikincil bir kanal turet.

    'base' sonucun ORTALAMASI olur (sinyal kendi ortalamasi etrafinda
    merkezlenir), 'amount' ne kadar degisim tasiyacagini, 'blur_px' ne
    kadar yumusak olacagini belirler. Olculen GTA hedefleri boyle
    dogrudan ayarlanabiliyor.
    """
    sig = spec
    if blur_px > 0:
        sig = iops.blur(spec, max(blur_px * 0.3615 * res_scale, 0.5), tile)
    if invert:
        sig = 1.0 - sig
    return np.clip(base + (sig - float(sig.mean())) * amount, 0.0, 1.0)


def _pack_spec_channels(spec, p, res_scale, tile):
    """
    GTA'nin RGB paketlemesi. Olculen gercek dokulardaki duzen:
        R = yogunluk  -- en detayli, en cok degisim
        G = falloff   -- daha yumusak, daha dar aralik
        B = fresnel   -- neredeyse duz, en parlak
    (bkz. tl_dlc_vw_casino_details_03_s.dds: std 0.136 / 0.027 / 0.013,
     ortalama 0.584 / 0.797 / 0.923)

    Hangi kanalin okunacagini shader tarafinda specMapIntMask secer;
    roller sabit degildir, o yuzden her kanal ayri ayarlanabilir.
    """
    out = np.empty(spec.shape + (3,), dtype=np.float32)

    r = spec
    if p["intensity_invert"]:
        r = 1.0 - r
    out[..., 0] = np.clip(r, 0.0, 1.0)

    out[..., 1] = _derive_channel(
        spec, p["falloff_base"], p["falloff_amount"], p["falloff_blur"],
        p["falloff_invert"], res_scale, tile)

    out[..., 2] = _derive_channel(
        spec, p["fresnel_base"], p["fresnel_amount"], p["fresnel_blur"],
        p["fresnel_invert"], res_scale, tile)

    return out


def specular_from_diffuse(diffuse, p, tile=True):
    """
    Blit_Shader.shader / fragCombineRoughSpec (pass 10) portu -- Materialize'in
    Specular sekmesinin gercekte kullandigi yol.

    Zincir:
      1. Diffuse'a contrast/bias
      2. Parlama ve golge maskeleri: maxLum uzerinde SMOOTHSTEP esikleri
         (kuvvet fonksiyonu degil). Maskeli bolgeler blur'a dogru karistirilir,
         yani parlama/golge duzlestirilir.
      3. Blur'a kendi kontrasti, sonra VIVID LIGHT karisimi -- asil yuksek
         gecirgen mekanizma budur, cikarma degil.
      4. Final contrast/bias
      5. Gri tona indirgeme (0.3/0.5/0.2)

    color_lerp / saturation Materialize'da bu pass'te OKUNMAZ (cikti her zaman
    gridir); bizde renkli GTA specular'i icin ek olarak duruyor, varsayilanlari
    notr oldugundan temel davranis birebir aynidir.

    -> (h, w, 3) float32
    """
    h, w = diffuse.shape[:2]
    res_scale = ((w + h) * 0.5) / 1024.0
    rgb = np.clip(diffuse[..., :3], 0.0, 1.0)

    main = iops.contrast_bias(rgb, p["diffuse_contrast"], p["diffuse_bias"])

    # Hann yaricapi = BlurSize piksel (cozunurluge gore olceklendi)
    sigma = max(p["blur_size"] * 0.3615 * res_scale, 0.5)
    blur = iops.blur(rgb, sigma, tile)

    # --- parlama / golge duzlestirme ---
    max_lum = main.max(axis=-1)
    light_mask = _smoothstep(p["light_mask_pow"], 1.001, max_lum)
    dark_mask = 1.0 - _smoothstep(-0.001, p["dark_mask_pow"], max_lum)
    blend = 1.0 - (1.0 - light_mask * p["light_pow"]) * (1.0 - dark_mask * p["dark_pow"])
    main = main + (blur - main) * blend[..., None]

    # --- yuksek gecirgen: vivid light ---
    blur_c = iops.contrast_bias(blur, p["blur_contrast"], 0.0)
    main = _vivid_light(main, blur_c)

    main = iops.contrast_bias(main, p["final_contrast"], p["final_bias"])

    spec = iops.luminance(main)

    # --- GTA kanal paketlemesi ---
    if p.get("channel_mode") == "PACKED":
        return _pack_spec_channels(spec, p, res_scale, tile)

    # --- bizim eklerimiz (varsayilanlari notr) ---
    if p["color_lerp"] > 0.0:
        tinted = np.clip(rgb * spec[..., None] * 2.0, 0.0, 1.0)
        out = spec[..., None] * (1.0 - p["color_lerp"]) + tinted * p["color_lerp"]
    else:
        out = np.repeat(spec[..., None], 3, axis=-1)

    if p["saturation"] != 1.0:
        g = iops.luminance(out)[..., None]
        out = np.clip(g + (out - g) * p["saturation"], 0.0, 1.0)

    if p["invert"]:
        out = 1.0 - out

    return np.clip(out, 0.0, 1.0).astype(np.float32)
