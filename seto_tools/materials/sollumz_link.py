# SPDX-License-Identifier: GPL-3.0-or-later
"""
sollumz_link.py -- Sollumz shader materyali kurulumu.

Sollumz zorunlu bagimlilik DEGIL. Bu modul icindeki her sey kurulu degilse
sessizce devre disi kalir; add-on'un geri kalani Sollumz'suz calisir.

Sollumz tarafinda kullandigimiz API:
    ydr.shader_materials.create_shader(filename, in_place_material=None)
    ydr.shader_materials.shadermats_by_filename   -> {"normal_spec.sps": ...}
    ydr.shader_materials.ShaderManager.find_shader(filename).parameter_map

Olusan node agacinda her sampler, parametre adiyla adlandirilmis bir
ShaderNodeTexImage'dir: node_tree.nodes["DiffuseSampler"] gibi.
"""

import importlib

import bpy

# Bizim uc haritamizin hangi Sollumz sampler'ina gittigi.
# (sampler adi, harita anahtari, non-color mu)
SAMPLER_MAP = (
    ("DiffuseSampler", "diffuse", False),
    ("BumpSampler", "normal", True),
    ("SpecSampler", "specular", True),
    # Sadece pxm/parallax varyantlarinda bulunur -- kucuk h ile yazilir.
    ("heightSampler", "height", True),
)

# Bir shader'i "uyumlu" saymak icin bulunmasi gereken sampler'lar
REQUIRED_SAMPLERS = frozenset(("DiffuseSampler", "BumpSampler", "SpecSampler"))

DEFAULT_SHADER = "normal_spec.sps"

# EnumProperty item'lari: Blender string referanslarini tutmadigi icin
# modul seviyesinde saklamak ZORUNDAYIZ, yoksa cop toplayici sonrasi
# bozuk metin/cokme olur.
_shader_items_cache = []

# Sollumz yokken donen liste. Bunu _shader_items_cache'e YAZMIYORUZ --
# yazsaydik kullanici Sollumz'u sonradan actiginda liste bayat kalirdi.
# Yine de sabit bir nesne olmali (yukaridaki referans kurali).
_FALLBACK_ITEMS = [(DEFAULT_SHADER, "normal_spec", "Sollumz is not installed")]

_UNSET = object()
_module_cache = _UNSET


def shader_module():
    """
    Sollumz'un ydr.shader_materials modulunu bul. Extension olarak da
    (bl_ext.*), klasik add-on olarak da (sollumz) kurulu olabilir.
    Bulamazsa None.

    Sonuc cache'lenir: panel her cizimde is_available() cagiriyor, basarisiz
    import denemesini her karede tekrarlamak istemeyiz.
    """
    global _module_cache
    if _module_cache is not _UNSET:
        return _module_cache
    _module_cache = _find_module()
    return _module_cache


def _find_module():
    bases = []
    try:
        for key in bpy.context.preferences.addons.keys():
            if key.split(".")[-1].lower() == "sollumz":
                bases.append(key)
    except AttributeError:
        pass
    bases += ["bl_ext.user_default.sollumz", "bl_ext.blender_org.sollumz", "sollumz"]

    seen = set()
    for base in bases:
        if base in seen:
            continue
        seen.add(base)
        try:
            return importlib.import_module(base + ".ydr.shader_materials")
        except Exception:
            continue
    return None


def is_available():
    return shader_module() is not None


def compatible_shaders():
    """
    Diffuse + Bump + Spec sampler'i olan tum shader'lar.
    normal_spec.sps basa alinir -- dinamik EnumProperty'de ilk item
    varsayilan secim olur.
    """
    global _shader_items_cache
    if _shader_items_cache:
        return _shader_items_cache

    mod = shader_module()
    if mod is None:
        return _FALLBACK_ITEMS

    found = []
    try:
        manager = mod.ShaderManager
        for filename in sorted(mod.shadermats_by_filename.keys()):
            shader = manager.find_shader(filename)
            if shader is None:
                continue
            if REQUIRED_SAMPLERS <= set(shader.parameter_map.keys()):
                found.append(filename)
    except Exception as exc:
        print("[Velxor Materialize] could not read Sollumz shader list:", exc)

    if not found:
        found = [DEFAULT_SHADER]
    if DEFAULT_SHADER in found:
        found.remove(DEFAULT_SHADER)
        found.insert(0, DEFAULT_SHADER)

    _shader_items_cache = [
        (fn, fn.replace(".sps", ""), f"GTA V shader '{fn}'") for fn in found
    ]
    return _shader_items_cache


def shader_samplers(filename):
    """
    Secili shader'da GERCEKTEN bulunan sampler adlari. Panel yalnizca
    bunlari listelesin diye var -- normal_spec'te heightSampler yok,
    varmis gibi gostermek yaniltici olurdu.
    """
    mod = shader_module()
    if mod is None:
        return set()
    try:
        shader = mod.ShaderManager.find_shader(filename)
    except Exception:
        return set()
    if shader is None:
        return set()
    return set(shader.parameter_map.keys())


def invalidate_cache():
    """Sollumz sonradan etkinlestirilmis olabilir; aramayi bastan yaptir.
    material_mode SOLLUMZ'a cevrildiginde cagrilir."""
    global _shader_items_cache, _module_cache
    _shader_items_cache = []
    _module_cache = _UNSET


def set_spec_channel_mask(mat, mask=(1.0, 0.0, 0.0)):
    """
    specMapIntMask'i ayarla: shader'a specular yogunlugunu hangi kanaldan
    okuyacagini soyler. Paketli harita urettigimizde R'yi (1,0,0) isaret
    ederiz, cunku yogunlugu oraya yaziyoruz.

    -> ayarlandiysa True
    """
    node = mat.node_tree.nodes.get("specMapIntMask")
    if node is None:
        return False
    try:
        for axis, value in zip(("X", "Y", "Z"), mask):
            node.set(axis, float(value))
        return True
    except Exception as exc:
        print("[Velxor Materialize] specMapIntMask ayarlanamadi:", exc)
        return False


def build_material(mat_name, shader_filename, images):
    """
    Sollumz shader materyalini kur ve sampler'lara haritalari yerlestir.

    images : {"diffuse": Image|None, "normal": ..., "specular": ..., "height": ...}
    -> (material, assigned_list, skipped_list)

    Ayni isimde materyal varsa yerinde guncellenir; boylece nesnelerin
    materyal slotlari ve atamalari bozulmaz.
    """
    mod = shader_module()
    if mod is None:
        raise ValueError(
            "Sollumz not found. Install and enable Sollumz, or switch "
            "Material Type back to Principled BSDF"
        )

    existing = bpy.data.materials.get(mat_name)
    try:
        if existing is not None:
            mat = mod.create_shader(shader_filename, in_place_material=existing)
        else:
            mat = mod.create_shader(shader_filename)
            mat.name = mat_name
    except AttributeError as exc:
        # create_shader bilinmeyen shader adinda AttributeError firlatiyor
        raise ValueError(f"Sollumz rejected shader '{shader_filename}': {exc}") from exc

    nodes = mat.node_tree.nodes
    assigned, skipped = [], []

    for sampler, key, is_data in SAMPLER_MAP:
        node = nodes.get(sampler)
        image = images.get(key)

        if node is None:
            # Bu shader'da o sampler yok (orn. normal_spec'te heightSampler).
            if image is not None and key == "height":
                skipped.append(f"{key} (no heightSampler in this shader)")
            continue
        if image is None:
            skipped.append(f"{sampler} (map not generated)")
            continue

        node.image = image
        # Sollumz non-color dokularini is_data ile isaretliyor; ayni yolu izle.
        # Ancak GEREKMEDIKCE dokunma: colorspace atamasi goruntunun tamponunu
        # gecersiz kilar ve paketlenmemis bir goruntude piksel verisini siler.
        if image.colorspace_settings.is_data != is_data:
            image.colorspace_settings.is_data = is_data
        if not is_data and image.colorspace_settings.name != "sRGB":
            image.colorspace_settings.name = "sRGB"
        assigned.append(sampler)

    return mat, assigned, skipped
