# SPDX-License-Identifier: GPL-3.0-or-later
"""
imageio.py -- bpy.types.Image <-> numpy kopruleri.

Blender'in pixel buffer'i her zaman scene-linear float'tur. Kaynak goruntu
sRGB olarak isaretliyse buradan okurken sRGB'ye geri cevirir, yani islem
hattina her zaman "goruntunun gercek 0..1 texel degerleri" girer.
Materialize da islemi bu uzayda yapar; bu yuzden sonuclar orada gordugun
gibi cikar.
"""

import math

import numpy as np
import bpy

from . import imageops as iops


def image_to_array(image):
    """-> (h, w, 4) float32, sRGB/display uzayinda 0..1"""
    w, h = image.size
    if w == 0 or h == 0:
        raise ValueError(f"Image '{image.name}' has no pixel data")

    buf = np.empty(w * h * 4, dtype=np.float32)
    image.pixels.foreach_get(buf)
    arr = buf.reshape(h, w, 4)

    if image.colorspace_settings.name not in {"Non-Color", "Raw", "Linear", "Linear Rec.709"}:
        arr[..., :3] = iops.linear_to_srgb(arr[..., :3])
    return arr


def resize_max(arr, max_dim):
    """Uzun kenar max_dim'i asmayacak sekilde 2'nin katlariyla kucult."""
    if max_dim <= 0:
        return arr
    out = arr
    while max(out.shape[0], out.shape[1]) > max_dim and min(out.shape[0], out.shape[1]) > 8:
        out = iops._downsample2(out)
    return out


def resize_divide(arr, divisor):
    """
    Boyutu tam olarak 'divisor' kadar kucult (1 = dokunma, 2 = yarim,
    4 = ceyrek).

    Mutlak piksel siniri yerine bolen kullaniyoruz ki 'Half' etiketi her
    kaynak cozunurlukte DOGRU olsun -- 1024 piksel siniri 2K'da yarim,
    4K'da ceyrek anlamina geliyordu.
    """
    if divisor <= 1:
        return arr
    out = arr
    steps = int(round(math.log2(divisor)))
    for _ in range(steps):
        if min(out.shape[0], out.shape[1]) <= 8:
            break
        out = iops._downsample2(out)
    return out


def srgb_encoded_copy(image, name="_vmat_export_tmp"):
    """
    Gecici bir kopya: piksel degerleri sRGB KODLANMIS olarak saklanir.

    Neden gerekli: export dosyaya ham degerleri yazar (0.5 -> 0.5). Ama
    PNG/TGA'nin colorspace bilgisi yoktur ve Blender da, sıradan goruntu
    programlari da bu dosyalari sRGB varsayar. sRGB varsayilarak acilan
    ham bir dosya 0.5 yerine 0.214 verir -- harita farkli gorunur.

    Bu kopyada 0.5 -> 0.735 yazilir; dosya sRGB olarak acildiginda geri
    0.5 cikar. Karsiligi, dosyanin ham veri olarak okunmasinin artik
    yanlis olmasidir -- secim kullanicinin.
    """
    w, h = image.size
    buf = np.empty(w * h * 4, dtype=np.float32)
    image.pixels.foreach_get(buf)
    arr = buf.reshape(h, w, 4)
    arr[..., :3] = iops.linear_to_srgb(arr[..., :3])

    tmp = bpy.data.images.get(name)
    if tmp is not None:
        bpy.data.images.remove(tmp)
    tmp = bpy.data.images.new(name, w, h, alpha=False, float_buffer=True)
    tmp.colorspace_settings.name = "Non-Color"
    tmp.pixels.foreach_set(arr.ravel())
    tmp.update()
    return tmp


def array_to_image(arr, name, non_color=True):
    """
    arr : (h, w) veya (h, w, 3) float32, 0..1
    Ayni isimde datablock varsa yeniden kullanilir (node baglantilari kopmaz).
    """
    if arr.ndim == 2:
        arr = np.repeat(arr[..., None], 3, axis=-1)

    h, w = arr.shape[:2]
    rgba = np.ones((h, w, 4), dtype=np.float32)
    rgba[..., :3] = np.clip(arr[..., :3], 0.0, 1.0)

    if not non_color:
        # sRGB olarak isaretlenecek -> buffer'a linear yazmaliyiz
        rgba[..., :3] = iops.srgb_to_linear(rgba[..., :3])

    image = bpy.data.images.get(name)
    if image is None:
        image = bpy.data.images.new(name, w, h, alpha=False, float_buffer=True)

    # SIRA BURADA KRITIK.
    #
    # colorspace atamasi goruntunun tamponunu gecersiz kilar; tampon daha
    # sonra generated_width/height degerlerinden yeniden uretilir.
    # image.scale() ise bu iki degeri GUNCELLEMEZ. Dolayisiyla once scale
    # edip sonra colorspace atarsak goruntu sessizce eski boyutuna doner ve
    # foreach_set "expected sequence size ..." diye patlar.
    #
    # Cozum: once colorspace, sonra generated_* ile birlikte boyutlandirma.
    wanted_cs = "Non-Color" if non_color else "sRGB"
    if image.colorspace_settings.name != wanted_cs:
        image.colorspace_settings.name = wanted_cs

    if tuple(image.size) != (w, h):
        # Cozunurluk degismis (orn. Processing Size Full <-> 1024).
        image.use_generated_float = True
        image.generated_width = w
        image.generated_height = h
        image.scale(w, h)

    if tuple(image.size) != (w, h):
        raise ValueError(
            f"Could not resize '{image.name}' to {w}x{h} (still {tuple(image.size)}). "
            f"Delete that image datablock and generate again"
        )

    image.pixels.foreach_set(rgba.ravel())
    image.update()

    # KRITIK 1: materyal onizlemesi, rendered view ve Image Editor dokunun
    # GPU kopyasini onbellekliyor. Serbest birakmazsak piksel verisi
    # degisse bile ekranda ESKI doku gorunmeye devam eder.
    image.gl_free()

    # KRITIK 2: paketleme SART, sadece .blend kalicligi icin degil.
    #
    # GENERATED kaynakli bir goruntude colorspace'e dokunmak (ya da tamponu
    # gecersiz kilan baska herhangi bir islem) goruntuyu generated_* 'tan
    # BOS olarak yeniden urettirir, yani piksel verisi silinir. Materyal
    # kurarken node'lara colorspace atadigimiz icin bu tam olarak
    # "Create/Update Material haritalari siliyor" hatasini uretiyordu.
    #
    # Paketlenmis (FILE) goruntude ayni islem veriyi paketten geri cozer,
    # veri korunur. Maliyeti 4K'da harita basina ~0.19 sn -- uretimin
    # yaninda ihmal edilebilir.
    image.use_fake_user = True
    try:
        image.pack()
    except RuntimeError as exc:
        print(f"[Velxor Materialize] could not pack '{image.name}':", exc)
    return image
