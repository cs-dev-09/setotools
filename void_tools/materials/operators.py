# SPDX-License-Identifier: GPL-3.0-or-later
"""
operators.py -- uretim, materyal kurulumu ve export.

regenerate() operator disindan da cagrilabilir; auto-update timer'i
bunu dogrudan kullanir (update callback'inden bpy.ops cagirmak guvenli degil).
"""

import os
import time

import bpy
from bpy.app.handlers import persistent
from bpy.props import EnumProperty
from bpy.types import Operator

from . import generators
from . import imageio
from . import properties
from . import sollumz_link


# Uretilen doku bu alanlarin hepsinde gorunebilir; hepsini yeniden cizdir.
_REDRAW_AREA_TYPES = frozenset(("IMAGE_EDITOR", "VIEW_3D", "NODE_EDITOR", "PROPERTIES"))


def tag_redraw_all():
    """
    Piksel verisini degistirmek Blender'i kendiliginden yeniden cizdirmez.
    Hem operator hem de auto-update timer bu fonksiyondan geciyor.
    """
    try:
        windows = bpy.context.window_manager.windows
    except AttributeError:
        return
    for window in windows:
        screen = window.screen
        if screen is None:
            continue
        for area in screen.areas:
            if area.type in _REDRAW_AREA_TYPES:
                area.tag_redraw()


# Onizleme alaninin pencere genisligine orani
PREVIEW_FACTOR = 0.28


def _window_region(area):
    for region in area.regions:
        if region.type == "WINDOW":
            return region
    return None


def _local_image_editors(window):
    """Yalnizca BU penceredeki Image Editor alanlari."""
    if window is None or window.screen is None:
        return []
    return [a for a in window.screen.areas if a.type == "IMAGE_EDITOR"]


def _split_preview_area(context, image):
    """
    Aktif 3D Viewport'u dikey bolup SOL parcayi Image Editor yap.

    Yeni pencere acmak yerine mevcut yerlesimi boluyoruz -- kullanici
    onizlemeyi sahnenin yaninda gormek istiyor.
    -> olusan Image Editor alani, ya da None
    """
    win = context.window
    if win is None or win.screen is None:
        return None
    screen = win.screen

    host = context.area
    if host is None or host.type != "VIEW_3D":
        viewports = [a for a in screen.areas if a.type == "VIEW_3D"]
        if not viewports:
            return None
        host = max(viewports, key=lambda a: a.width * a.height)

    before = list(screen.areas)
    override = {"window": win, "screen": screen, "area": host}
    region = _window_region(host)
    if region is not None:
        override["region"] = region

    try:
        with context.temp_override(**override):
            bpy.ops.screen.area_split(direction="VERTICAL", factor=PREVIEW_FACTOR)
    except RuntimeError as exc:
        print("[Velxor Materialize] area split failed:", exc)
        return None

    fresh = [a for a in screen.areas if a not in before]
    if not fresh:
        return None

    # Bolme sonrasi iki parcadan SOLDAKINI Image Editor yapiyoruz; hangisinin
    # "yeni" oldugu Blender'in isine kalmis, konum ise kesin.
    left = min([host, fresh[0]], key=lambda a: a.x)
    left.type = "IMAGE_EDITOR"
    left.spaces.active.image = image
    left.tag_redraw()
    return left


def _close_preview_area(context, area):
    override = {"window": context.window, "screen": context.window.screen, "area": area}
    region = _window_region(area)
    if region is not None:
        override["region"] = region
    try:
        with context.temp_override(**override):
            bpy.ops.screen.area_close()
        return True
    except RuntimeError as exc:
        print("[Velxor Materialize] area close failed:", exc)
        return False


def _image_editors(context):
    """Acik tum pencerelerdeki Image Editor alanlari. Panel artik 3D
    Viewport'ta oldugu icin editor baska bir pencerede/workspace'te olabilir."""
    found = []
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "IMAGE_EDITOR":
                found.append(area)
    return found


def _suffix(image, kind):
    base = image.name
    for ext in (".png", ".jpg", ".jpeg", ".tga", ".tif", ".tiff", ".exr", ".dds"):
        if base.lower().endswith(ext):
            base = base[: -len(ext)]
            break
    return f"{base}_{kind}"


def regenerate(scene, target="ALL"):
    """
    target: HEIGHT | NORMAL | SPECULAR | ALL | AUTO
    AUTO -> aktif sekmeye gore, bagimliliklariyla birlikte.
    Donen deger: (uretilen_harita_adlari, gecen_sure_sn)
    """
    props = scene.vmat
    src = props.source_image
    if src is None:
        raise ValueError("No source diffuse image selected")

    if target == "AUTO":
        target = props.tab

    t0 = time.perf_counter()
    props.is_running = True
    try:
        diffuse = imageio.image_to_array(src)
        diffuse = imageio.resize_divide(diffuse, int(props.preview_size))
        tile = props.tileable
        made = []

        need_normal = target in {"NORMAL", "ALL"}
        need_spec = target in {"SPECULAR", "ALL"}

        # Normal egimini diffuse'tan okuyorsa height'a hic ihtiyaci yok;
        # sadece Normal uretiliyorken bosuna hesaplamayalim.
        normal_needs_height = props.normal.source == "HEIGHT"
        need_height = target in {"HEIGHT", "ALL"} or (need_normal and normal_needs_height)

        height = None
        if need_height:
            height = generators.height_from_diffuse(diffuse, props.height.as_dict(), tile)
            props.height_image = imageio.array_to_image(
                height, _suffix(src, "height"), non_color=True
            )
            made.append("height")

        if need_normal:
            normal = generators.normal_map(
                height, props.normal.as_dict(), tile, diffuse=diffuse
            )
            props.normal_image = imageio.array_to_image(
                normal, _suffix(src, "normal"), non_color=True
            )
            made.append("normal")

        if need_spec:
            spec = generators.specular_from_diffuse(diffuse, props.specular.as_dict(), tile)
            props.specular_image = imageio.array_to_image(
                spec, _suffix(src, "spec"), non_color=True
            )
            made.append("specular")
    finally:
        props.is_running = False

    tag_redraw_all()
    return made, time.perf_counter() - t0


class VMAT_OT_generate(Operator):
    bl_idname = "vmat.generate"
    bl_label = "Generate"
    bl_description = "Generate the selected map(s) from the source diffuse"
    bl_options = {"REGISTER", "UNDO"}

    target: EnumProperty(
        items=(
            ("AUTO", "Active Tab", ""),
            ("HEIGHT", "Height", ""),
            ("NORMAL", "Normal", ""),
            ("SPECULAR", "Specular", ""),
            ("ALL", "All", ""),
        ),
        default="AUTO",
        options={"SKIP_SAVE"},
    )

    @classmethod
    def poll(cls, context):
        return context.scene.vmat.source_image is not None

    def execute(self, context):
        props = context.scene.vmat
        try:
            made, elapsed = regenerate(context.scene, self.target)
        except (ValueError, MemoryError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        self.report({"INFO"}, f"Generated {', '.join(made)} in {elapsed:.2f}s")

        # Acik bir Image Editor varsa sonucu oraya bas -- ama kullanici
        # kaynak goruntuye bakiyorsa onu elinden alma.
        # AUTO ve ALL'da hangi haritanin gosterilecegi aktif sekmeden gelir;
        # "ALL" sozlukte bir anahtar DEGIL.
        which = props.tab if self.target in {"AUTO", "ALL"} else self.target
        img = {
            "HEIGHT": props.height_image,
            "NORMAL": props.normal_image,
            "SPECULAR": props.specular_image,
        }.get(which)
        if img is not None:
            for area in _image_editors(context):
                if area.spaces.active.image != props.source_image:
                    area.spaces.active.image = img
                    area.tag_redraw()
        return {"FINISHED"}


class VMAT_OT_preset(Operator):
    bl_idname = "vmat.preset"
    bl_label = "Preset"
    bl_description = "Apply one of Materialize's equalizer presets"
    bl_options = {"REGISTER", "UNDO"}

    bank: EnumProperty(
        items=(
            ("HEIGHT_WEIGHT", "Height Weights", ""),
            ("HEIGHT_CONTRAST", "Height Contrasts", ""),
            ("NORMAL_WEIGHT", "Normal Weights", ""),
        ),
        options={"SKIP_SAVE"},
    )
    preset: bpy.props.StringProperty(options={"SKIP_SAVE"})

    def execute(self, context):
        p = context.scene.vmat
        table, target, field = {
            "HEIGHT_WEIGHT": (properties.PRESET_HEIGHT_WEIGHT, p.height, "blur_weight"),
            "HEIGHT_CONTRAST": (properties.PRESET_HEIGHT_CONTRAST, p.height, "blur_contrast"),
            "NORMAL_WEIGHT": (properties.PRESET_NORMAL_WEIGHT, p.normal, "blur_weight"),
        }[self.bank]

        values = table.get(self.preset)
        if values is None:
            self.report({"ERROR"}, f"Unknown preset '{self.preset}'")
            return {"CANCELLED"}

        setattr(target, field, values)
        self.report({"INFO"}, f"{self.preset.title()} preset applied")
        return {"FINISHED"}


def _reset_group(group):
    """
    Bir PropertyGroup'u varsayilanlarina dondur.

    property_unset her ozelligi tanimindaki default'a geri alir, yani
    burada hicbir deger elle yazilmaz -- uretim varsayilanlarina
    dokunmadan sifirlama garantisi bu.
    """
    for prop in group.bl_rna.properties:
        if prop.identifier == "rna_type":
            continue

        # POINTER kontrolu readonly kontrolunden ONCE gelmeli: Blender
        # PropertyGroup pointer'larini readonly isaretliyor, bu yuzden ters
        # sirada renk ornekleri hic sifirlanmiyordu.
        if prop.type == "POINTER":
            sub = getattr(group, prop.identifier, None)
            # Yalnizca gomulu PropertyGroup'lara in -- bir Image/Object
            # datablock'una inmek felaket olurdu.
            if isinstance(sub, bpy.types.PropertyGroup):
                _reset_group(sub)
            continue

        if prop.is_readonly:
            continue
        try:
            group.property_unset(prop.identifier)
        except Exception:
            pass


class VMAT_OT_reset(Operator):
    bl_idname = "vmat.reset"
    bl_label = "Reset All Settings"
    bl_description = ("Put every Height, Normal and Specular setting back to its "
                      "default and build the three maps again from the source image")
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.scene.vmat.source_image is not None

    def invoke(self, context, event):
        # Elle yapilan tum ayarlar gider -- once onay al.
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        props = context.scene.vmat
        for group in (props.height, props.normal, props.specular):
            _reset_group(group)

        try:
            made, elapsed = regenerate(context.scene, "ALL")
        except (ValueError, MemoryError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        self.report({"INFO"},
                    f"Settings reset, {', '.join(made)} rebuilt ({elapsed:.2f}s)")
        return {"FINISHED"}


class VMAT_OT_show_map(Operator):
    bl_idname = "vmat.show_map"
    bl_label = "Show"
    bl_description = ("Show this map beside the scene. Opens a preview on the "
                      "left if none is open; press again to close it")

    which: EnumProperty(
        items=(
            ("SOURCE", "Diffuse", ""),
            ("HEIGHT", "Height", ""),
            ("NORMAL", "Normal", ""),
            ("SPECULAR", "Specular", ""),
        ),
        options={"SKIP_SAVE"},
    )

    def execute(self, context):
        props = context.scene.vmat
        img = {
            "SOURCE": props.source_image,
            "HEIGHT": props.height_image,
            "NORMAL": props.normal_image,
            "SPECULAR": props.specular_image,
        }[self.which]
        if img is None:
            self.report({"WARNING"}, "That map has not been generated yet")
            return {"CANCELLED"}

        local = _local_image_editors(context.window)

        if local:
            # Bu harita zaten gorunuyorsa buton bir ANAHTAR gibi davransin
            # ve onizlemeyi kapatsin.
            showing = [a for a in local if a.spaces.active.image == img]
            if showing and any(_close_preview_area(context, a) for a in showing):
                self.report({"INFO"}, "Preview closed")
                return {"FINISHED"}

            # Baska bir harita gosteriyor -- kapatma, sadece degistir.
            for area in local:
                area.spaces.active.image = img
                area.tag_redraw()
            return {"FINISHED"}

        # Bu pencerede onizleme yok -- sahneyi bolup solda ac.
        if _split_preview_area(context, img) is not None:
            self.report({"INFO"}, f"'{img.name}' opened on the left")
            return {"FINISHED"}

        # Bolme calismadiysa baska penceredeki bir editoru kullanmayi dene.
        others = _image_editors(context)
        if others:
            for area in others:
                area.spaces.active.image = img
                area.tag_redraw()
            return {"FINISHED"}

        self.report({"ERROR"},
                    "Could not open a preview. Switch an area to Image Editor "
                    "manually, then press this again")
        return {"CANCELLED"}


# --------------------------------------------------------------- materyal

class VMAT_OT_to_material(Operator):
    bl_idname = "vmat.to_material"
    bl_label = "Create / Update Material"
    bl_description = ("Wire the generated maps into a Principled BSDF node tree. "
                      "Assigned to the active object when there is one")
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.scene.vmat.source_image is not None

    def execute(self, context):
        props = context.scene.vmat
        src = props.source_image
        mat_name = f"{_suffix(src, 'MAT')}"

        if props.material_mode == "SOLLUMZ":
            try:
                mat, assigned, skipped = sollumz_link.build_material(
                    mat_name,
                    props.sollumz_shader or sollumz_link.DEFAULT_SHADER,
                    {
                        "diffuse": src,
                        "normal": props.normal_image,
                        "specular": props.specular_image,
                        "height": props.height_image,
                    },
                )
            except ValueError as exc:
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}

            # Paketli spec urettiysek shader'a yogunlugun R'de oldugunu soyle
            if props.specular.channel_mode == "PACKED":
                if sollumz_link.set_spec_channel_mask(mat, (1.0, 0.0, 0.0)):
                    assigned.append("specMapIntMask=R")

            detail = f"{mat.shader_properties.filename}: {', '.join(assigned)}" \
                if assigned else f"{mat.shader_properties.filename}: no maps assigned"
            if skipped:
                detail += f" (skipped {'; '.join(skipped)})"
            self._assign(context, mat, detail)
            return {"FINISHED"}

        mat = self._build_principled(props, mat_name)
        self._assign(context, mat, "Principled BSDF")
        return {"FINISHED"}

    # ------------------------------------------------------------------
    def _assign(self, context, mat, detail):
        obj = context.active_object
        if obj is not None and obj.type in {"MESH", "CURVE", "SURFACE", "FONT", "META"}:
            if mat.name not in [m.name for m in obj.data.materials if m]:
                obj.data.materials.append(mat)
            self.report({"INFO"}, f"'{mat.name}' -> '{obj.name}'  [{detail}]")
        else:
            self.report({"INFO"}, f"'{mat.name}' created, no active object  [{detail}]")

    def _build_principled(self, props, mat_name):
        src = props.source_image

        mat = bpy.data.materials.get(mat_name)
        if mat is None:
            mat = bpy.data.materials.new(mat_name)
        mat.use_nodes = True

        nt = mat.node_tree
        nt.nodes.clear()

        out = nt.nodes.new("ShaderNodeOutputMaterial")
        out.location = (600, 0)
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
        bsdf.location = (280, 0)
        nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

        uv = nt.nodes.new("ShaderNodeTexCoord")
        uv.location = (-900, -200)

        def tex(image, y, non_color):
            node = nt.nodes.new("ShaderNodeTexImage")
            node.image = image
            node.location = (-620, y)
            node.label = image.name
            # Colorspace'e gereksiz yere DOKUNMA: atama goruntunun tamponunu
            # gecersiz kiliyor ve paketlenmemis bir goruntude veriyi siliyor.
            wanted = "Non-Color" if non_color else "sRGB"
            if image.colorspace_settings.name != wanted:
                image.colorspace_settings.name = wanted
            nt.links.new(uv.outputs["UV"], node.inputs["Vector"])
            return node

        # diffuse
        d = tex(src, 300, non_color=False)
        nt.links.new(d.outputs["Color"], bsdf.inputs["Base Color"])

        # specular -> roughness (spec yuksek = puruzsuz)
        if props.specular_image is not None:
            s = tex(props.specular_image, 40, non_color=True)
            inv = nt.nodes.new("ShaderNodeInvert")
            inv.location = (-300, 40)
            nt.links.new(s.outputs["Color"], inv.inputs["Color"])
            rough = bsdf.inputs.get("Roughness")
            if rough is not None:
                nt.links.new(inv.outputs["Color"], rough)

        # normal
        if props.normal_image is not None:
            n = tex(props.normal_image, -220, non_color=True)
            nmap = nt.nodes.new("ShaderNodeNormalMap")
            nmap.location = (-300, -220)
            nt.links.new(n.outputs["Color"], nmap.inputs["Color"])
            nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])

        # height -> displacement
        if props.height_image is not None:
            hgt = tex(props.height_image, -520, non_color=True)
            disp = nt.nodes.new("ShaderNodeDisplacement")
            disp.location = (280, -420)
            disp.inputs["Scale"].default_value = 0.05
            nt.links.new(hgt.outputs["Color"], disp.inputs["Height"])
            nt.links.new(disp.outputs["Displacement"], out.inputs["Displacement"])

        return mat


# ----------------------------------------------------------------- export

_IMAGE_SETTINGS_KEYS = ("file_format", "color_mode", "color_depth", "quality")


def _snapshot(settings):
    return {k: getattr(settings, k) for k in _IMAGE_SETTINGS_KEYS}


def _restore(settings, snap):
    for k, v in snap.items():
        try:
            setattr(settings, k, v)
        except (TypeError, AttributeError):
            pass


class VMAT_OT_export(Operator):
    bl_idname = "vmat.export"
    bl_label = "Export Images"
    bl_description = "Save the checked maps into the chosen folder and format"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        p = context.scene.vmat
        return any((p.height_image, p.normal_image, p.specular_image))

    def execute(self, context):
        scene = context.scene
        props = scene.vmat

        directory = bpy.path.abspath(props.export_dir)
        if not directory:
            self.report({"ERROR"}, "Output directory is empty")
            return {"CANCELLED"}
        try:
            os.makedirs(directory, exist_ok=True)
        except OSError as exc:
            self.report({"ERROR"}, f"Could not create directory: {exc}")
            return {"CANCELLED"}

        base = props.export_basename.strip()
        if not base and props.source_image is not None:
            base = _suffix(props.source_image, "").rstrip("_")
        if not base:
            base = "material"

        jobs = []
        if props.export_height and props.height_image:
            jobs.append(("height", props.height_image))
        if props.export_normal and props.normal_image:
            jobs.append(("normal", props.normal_image))
        if props.export_specular and props.specular_image:
            jobs.append(("spec", props.specular_image))

        if not jobs:
            self.report({"WARNING"}, "No maps selected for export")
            return {"CANCELLED"}

        ext = {"PNG": ".png", "JPEG": ".jpg", "TARGA": ".tga", "OPEN_EXR": ".exr"}[props.export_format]

        img_settings = scene.render.image_settings
        snap = _snapshot(img_settings)
        view = scene.view_settings
        view_snap = (view.view_transform, view.look, view.exposure, view.gamma)

        written = []
        try:
            # Renk yonetimi haritalari bozmasin: duz yazim.
            view.view_transform = "Standard"
            view.look = "None"
            view.exposure = 0.0
            view.gamma = 1.0

            img_settings.file_format = props.export_format
            img_settings.color_mode = "RGB"
            if props.export_format == "OPEN_EXR":
                img_settings.color_depth = "32"
            elif props.export_format == "PNG":
                img_settings.color_depth = props.export_depth
            else:
                img_settings.color_depth = "8"
            if props.export_format == "JPEG":
                img_settings.quality = props.export_quality

            # EXR float ve zaten veri formati; sRGB kodlamak anlamsiz olur.
            encode_srgb = (props.export_colorspace == "SRGB"
                           and props.export_format != "OPEN_EXR")

            for kind, image in jobs:
                path = os.path.join(directory, f"{base}_{kind}{ext}")
                if encode_srgb:
                    tmp = imageio.srgb_encoded_copy(image)
                    try:
                        tmp.save_render(filepath=path, scene=scene)
                    finally:
                        bpy.data.images.remove(tmp)
                else:
                    image.save_render(filepath=path, scene=scene)
                written.append(os.path.basename(path))
        except (RuntimeError, OSError) as exc:
            self.report({"ERROR"}, f"Save failed: {exc}")
            return {"CANCELLED"}
        finally:
            _restore(img_settings, snap)
            view.view_transform, view.look, view.exposure, view.gamma = view_snap

        self.report({"INFO"}, f"Saved {len(written)} file(s): {', '.join(written)}")
        return {"FINISHED"}


# ------------------------------------------------------- kalicilik

@persistent
def _pack_generated_on_save(_dummy):
    """
    Emniyet agi. Haritalar zaten uretim aninda paketleniyor
    (imageio.array_to_image); bu handler yalnizca bir sekilde paketsiz
    kalmis olanlari yakalar, yoksa .blend'i acinca bos gelirler.
    """
    for scene in bpy.data.scenes:
        props = getattr(scene, "vmat", None)
        if props is None:
            continue
        for image in (props.height_image, props.normal_image, props.specular_image):
            if image is None or image.packed_file:
                continue
            try:
                image.pack()
            except RuntimeError as exc:
                print(f"[Velxor Materialize] could not pack '{image.name}':", exc)


_CLASSES = (
    VMAT_OT_generate,
    VMAT_OT_preset,
    VMAT_OT_reset,
    VMAT_OT_show_map,
    VMAT_OT_to_material,
    VMAT_OT_export,
)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    if _pack_generated_on_save not in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.append(_pack_generated_on_save)


def unregister():
    if _pack_generated_on_save in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.remove(_pack_generated_on_save)
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
