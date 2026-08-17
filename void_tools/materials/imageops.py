# SPDX-License-Identifier: GPL-3.0-or-later
"""
imageops.py -- saf NumPy goruntu islemleri.

Burada bpy'ye bagimlilik SADECE image_to_array / array_to_image
fonksiyonlarindadir. Geri kalan her sey saf numpy, yani test edilebilir.

Dizi konvansiyonu
-----------------
Tum diziler (h, w, c) float32, deger araligi 0..1 (display/sRGB uzayi).
Blender pixel buffer'i alt satirdan baslar; biz onu oldugu gibi birakiyoruz.
Unity de ayni (UV origin sol-alt), dolayisiyla Materialize ile normal
map Y yonu tutarli olur.
"""

import numpy as np

# Materialize'in luminance agirliklari (Blit_Height_From_Diffuse.shader)
# Rec.709 degil -- bilerek boyle, kaynak kodda 0.3 / 0.5 / 0.2.
LUMA = np.array((0.3, 0.5, 0.2), dtype=np.float32)


# ---------------------------------------------------------------- renk uzayi

def srgb_to_linear(a):
    a = np.clip(a, 0.0, 1.0)
    return np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4).astype(np.float32)


def linear_to_srgb(a):
    a = np.clip(a, 0.0, 1.0)
    return np.where(a <= 0.0031308, a * 12.92, 1.055 * (a ** (1.0 / 2.4)) - 0.055).astype(np.float32)


# ---------------------------------------------------------------- temel islem

def luminance(rgb):
    """(h,w,3+) -> (h,w) float32"""
    return (rgb[..., :3] * LUMA).sum(axis=-1).astype(np.float32)


def robust_range(a, low=0.5, high=99.5):
    """
    Aykiri degerlere dayanikli min/max.

    Ham a.min()/a.max() kullanmak tehlikeli: dokudaki TEK bir asiri parlak
    ya da simsiyah piksel butun araligi yutar, geri kalan her sey 0.5
    civarina sikisir ve harita duz cikar. Gercek dokularda (ozellikle
    GTA dokularinda) boyle pikseller cok yaygin.

    Buyuk dizilerde yuzdelik hesabi tam siralama gerektirdiginden orneklem
    alinir -- sonuc pratikte ayni, maliyet 4K'da saniyeler yerine ms.
    """
    flat = a.ravel()
    if flat.size > 1_000_000:
        flat = flat[:: max(1, flat.size // 1_000_000)]
    lo, hi = np.percentile(flat, (low, high))
    return float(lo), float(hi)


def contrast_bias(a, contrast=1.0, bias=0.0):
    """Materialize'in her yerde kullandigi remap: (x-0.5)*c + 0.5 + b, clamp."""
    return np.clip((a - 0.5) * contrast + 0.5 + bias, 0.0, 1.0).astype(np.float32)


def _gauss_kernel(sigma):
    # Yaricapi 4'te tutuyoruz: daha buyuk sigma'lar piramit yoluyla
    # cozuluyor, dolayisiyla tap sayisi cozunurlukten bagimsiz sabit kalir.
    radius = int(max(1, min(4, round(sigma * 2.5))))
    x = np.arange(-radius, radius + 1, dtype=np.float32)
    k = np.exp(-(x * x) / (2.0 * sigma * sigma)).astype(np.float32)
    return k / k.sum()


def _convolve1d(a, k, axis, tile):
    """
    np.pad + slice view ile ayrilabilir konvolusyon.
    np.take(fancy index) her tapta tam kopya uretiyordu; slice bir view
    oldugu icin bu yol belirgin sekilde daha hizli ve az bellek yer.
    """
    radius = len(k) // 2
    if radius == 0:
        return a.astype(np.float32, copy=True)

    n = a.shape[axis]
    pad_width = [(0, 0)] * a.ndim
    pad_width[axis] = (radius, radius)
    padded = np.pad(a, pad_width, mode="wrap" if tile else "edge")

    out = np.zeros_like(a)
    tmp = np.empty_like(a)
    sl = [slice(None)] * a.ndim
    for i, w in enumerate(k):
        if w == 0.0:
            continue
        sl[axis] = slice(i, i + n)
        np.multiply(padded[tuple(sl)], w, out=tmp)
        out += tmp
    return out


def _downsample2(a):
    """2x2 ortalama ile yariya indir. Tek sayili boyutlar icin kenar tekrarlanir."""
    h, w = a.shape[:2]
    if h % 2:
        a = np.concatenate([a, a[-1:]], axis=0)
    if w % 2:
        a = np.concatenate([a, a[:, -1:]], axis=1)
    h2, w2 = a.shape[0] // 2, a.shape[1] // 2
    a = a.reshape(h2, 2, w2, 2, -1) if a.ndim == 3 else a.reshape(h2, 2, w2, 2)
    return a.mean(axis=(1, 3)).astype(np.float32)


def _upsample2(a, shape, tile):
    """Bilinear'a yakin 2x buyutme: repeat + 1-2-1 yumusatma."""
    up = np.repeat(np.repeat(a, 2, axis=0), 2, axis=1)
    k = np.array((0.25, 0.5, 0.25), dtype=np.float32)
    up = _convolve1d(up, k, 0, tile)
    up = _convolve1d(up, k, 1, tile)
    return up[: shape[0], : shape[1]]


_MIN_DIM = 8    # bu boyutun altina inmeyiz (cok genis blur'lar icin gerekli)
_MAX_SIGMA = 2.0  # bu sigma'nin ustunde bir kademe kucultmek daha ucuz


def _gauss_at(a, sigma, tile):
    k = _gauss_kernel(sigma)
    a = _convolve1d(a, k, 0, tile)
    return _convolve1d(a, k, 1, tile)


def _upsample_stack(a, shapes, tile):
    """shapes: kucultme sirasinda kaydedilen sekiller (en dis en sonda degil,
    en icte)."""
    for shape in reversed(shapes):
        a = _upsample2(a, shape, tile)
    return a


def blur(a, sigma, tile=True):
    """
    Separable gaussian. Buyuk sigma'da piramit yolu kullanilir; boylece
    cekirdek yaricapi hep <= 4 kalir ve maliyet cozunurlukle dogrusal olur.
    """
    if sigma <= 0.05:
        return a.astype(np.float32, copy=True)

    shapes = []
    cur = a.astype(np.float32, copy=False)
    s = float(sigma)
    while s > _MAX_SIGMA and min(cur.shape[0], cur.shape[1]) > _MIN_DIM:
        shapes.append(cur.shape)
        cur = _downsample2(cur)
        s *= 0.5

    cur = _gauss_at(cur, s, tile)
    return _upsample_stack(cur, shapes, tile).astype(np.float32)


def pyramid_combine(base, spreads, contrasts, weights, tile=True):
    """
    Materialize'in blur zinciri + fragCombine agirlikli ortalamasi, tek
    geciste.

    Iki onemli fark var (sonuc ayni, maliyet cok dusuk):

    1. Zincir kucultulmus cozunurlukte tasinir. Seviye 6'nin sigma'si
       goruntu boyutuyla olcektigi icin tam cozunurlukte islemenin bir
       anlami yok; her kademede yariya inip birlestirmeden once geri
       buyutuyoruz.
    2. Seviyeler listede biriktirilmiyor, dogrudan toplama ekleniyor.
       7 seviyeyi 4K RGB'de saklamak ~1.4 GB tutuyordu.

    Seviyeler kendi cozunurluk kademesinde toplanir; her seviyeyi tek tek
    tam cozunurluge buyutmek yerine en sonda tek bir buyutme zinciri
    yurutulur. 3 kanalli normal map'te esas maliyet buydu.

    spreads / contrasts : 6 elemanli (seviye 1..6)
    weights             : 7 elemanli (seviye 0..6)
    """
    total = float(sum(weights))
    if total <= 1e-6:
        return base.astype(np.float32, copy=True)

    base = base.astype(np.float32, copy=False)

    # accs[d] = d kademesinde biriken agirlikli toplam
    accs = {}
    if weights[0]:
        accs[0] = base * weights[0]

    cur = base
    shapes = []  # shapes[d] = d kademesindeki sekil (d+1'e inmeden once)
    for i, (sigma, c) in enumerate(zip(spreads, contrasts), start=1):
        # cur zaten kucultulmusse hedef sigma da o oranda kuculur
        s = float(sigma) / (2 ** len(shapes))
        while s > _MAX_SIGMA and min(cur.shape[0], cur.shape[1]) > _MIN_DIM:
            shapes.append(cur.shape)
            cur = _downsample2(cur)
            s *= 0.5

        cur = _gauss_at(cur, s, tile)
        if c != 1.0:
            cur = contrast_bias(cur, c, 0.0)

        w = weights[i]
        if w:
            d = len(shapes)
            if d in accs:
                accs[d] += cur * w
            else:
                accs[d] = cur * w

    # En derinden yuzeye dogru katla. Aralik uzerinde donuyoruz cunku
    # katlama sirasinda ara kademeler olusabiliyor (orn. {0,3,5} -> 4).
    for d in range(max(accs), 0, -1):
        if d not in accs:
            continue
        up = _upsample2(accs.pop(d), shapes[d - 1], tile)
        if d - 1 in accs:
            accs[d - 1] += up
        else:
            accs[d - 1] = up

    acc = accs.get(0)
    if acc is None:  # tum agirliklar sifir disinda bir yerde tutuldu
        acc = np.zeros_like(base)
    return (acc / total).astype(np.float32)


# Materialize'in blur'u Hann (yukseltilmis kosinus) penceresi, _BlurSamples=4
# ile, yani yaricap = 4 * spread piksel. Hann penceresinin standart sapmasi
# yaricapin 0.3615 kati -> gercek sigma = 1.446 * spread.
# Bunu atlamak butun seviyeleri Materialize'dakinden ~%45 dar yapiyordu.
HANN_SIGMA_PER_SPREAD = 0.3615 * 4.0


def spread_schedule(width, height):
    """
    NormalFromHeightGui.cs'teki artis serisi:
        extra  = (w + h) / 2 / 1024
        spread = 1 ; +1e, +2e, +4e, +8e, +16e
    Cozunurlukle olceklenir, boylece 512 ile 4K ayni gorunumu verir.
    Donen degerler dogrudan gaussian sigma'sidir (Hann karsiligi uygulanmis).
    """
    extra = ((width + height) * 0.5) / 1024.0
    spread = 1.0
    out = []
    for mult in (1, 2, 4, 8, 16):
        out.append(spread * HANN_SIGMA_PER_SPREAD)
        spread += mult * extra
    out.append(spread * HANN_SIGMA_PER_SPREAD)
    return out  # 6 eleman


def cumulative_sigmas(width, height, scale=1.0):
    """
    Her seviyenin ETKIN blur yaricapi, piksel cinsinden.

    Seviyeler zincirleme oldugu icin (her biri bir oncekinin blur'u) tek
    tek sigma'lar dogrudan toplanmaz; art arda uygulanan iki gaussian'in
    bileskesi sqrt(s1^2 + s2^2) olur.

    -> 7 elemanli liste, [0] = 0.0 (seviye 0 blur'lanmaz)
    """
    out = [0.0]
    acc = 0.0
    for s in spread_schedule(width, height):
        s *= scale
        acc += s * s
        out.append(acc ** 0.5)
    return out


# ---------------------------------------------------------------- renk maskesi

def rgb_to_hsl(rgb):
    """(h,w,3) 0..1 -> h, s, l ayri diziler (hue 0..1)."""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    d = mx - mn
    l = (mx + mn) * 0.5

    s = np.zeros_like(l)
    nz = d > 1e-6
    denom = 1.0 - np.abs(2.0 * l - 1.0)
    s[nz] = d[nz] / np.maximum(denom[nz], 1e-6)

    h = np.zeros_like(l)
    m = nz & (mx == r)
    h[m] = ((g[m] - b[m]) / d[m]) % 6.0
    m = nz & (mx == g)
    h[m] = (b[m] - r[m]) / d[m] + 2.0
    m = nz & (mx == b)
    h[m] = (r[m] - g[m]) / d[m] + 4.0
    h = (h / 6.0) % 1.0
    return h.astype(np.float32), np.clip(s, 0, 1).astype(np.float32), l.astype(np.float32)


def color_mask(rgb, sample_rgb, hue_w, sat_w, lum_w, mask_low, mask_high):
    """
    Blit_Sample.shader / fragSample'in maske matematiginin birebir portu.

        hueDif = 1 - min(|h-sh|, |h+1-sh|, |h-1-sh|) * 2
        satDif = 1 - |s - ss|
        lumDif = 1 - |l - sl|
        mask   = (hueDif*hw + satDif*sw + lumDif*lw) / (hw + sw + lw)
        mask   = smoothstep(maskLow, maskHigh, mask)

    Dikkat: kanal basina YAKINLIK hesaplanip agirliklandiriliyor ve toplam
    agirliga BOLUNUYOR. Bolmeyi atlamak ya da hue'yu doygunlukla kismak
    (daha once yaptigim gibi) Materialize'dan sapmadir.
    """
    wsum = float(hue_w) + float(sat_w) + float(lum_w)
    if wsum <= 1e-6:
        return np.zeros(rgb.shape[:2], dtype=np.float32)

    h, s, l = rgb_to_hsl(rgb)
    sh, ss, sl = rgb_to_hsl(np.array(sample_rgb, dtype=np.float32).reshape(1, 1, 3))
    sh, ss, sl = float(sh[0, 0]), float(ss[0, 0]), float(sl[0, 0])

    hue_dif = 1.0 - np.minimum(np.minimum(np.abs(h - sh), np.abs((h + 1.0) - sh)),
                               np.abs((h - 1.0) - sh)) * 2.0
    sat_dif = 1.0 - np.abs(s - ss)
    lum_dif = 1.0 - np.abs(l - sl)

    mask = (hue_dif * hue_w + sat_dif * sat_w + lum_dif * lum_w) / wsum

    lo, hi = float(mask_low), float(mask_high)
    if abs(hi - lo) < 1e-6:
        return (mask >= hi).astype(np.float32)
    t = np.clip((mask - lo) / (hi - lo), 0.0, 1.0)
    return (t * t * (3.0 - 2.0 * t)).astype(np.float32)  # smoothstep
