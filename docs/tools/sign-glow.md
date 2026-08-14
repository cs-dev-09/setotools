# Sign Glow

**Materials → Sign Glow**

The halo behind lit 3D lettering. Select the letters, press **Create Sign
Glow**, and the tool traces their own silhouette onto a plane just behind
them — a tight glow hugging the letterforms and a wide bloom spreading out
past them, on one quad and one texture.

That is how a lit sign reads at night in GTA. Not with lights: a real light per
sign is a budget nobody has, it will not survive the interior's light cap, and
it does not look like neon anyway. What the game does — and what vanilla signage
does — is exactly this: an emissive plane carrying a picture of the glow.

!!! info "Contributed by [Molo Modding](https://github.com/molossen)"

    Written as a standalone add-on and folded in here. The maths is theirs;
    what changed on the way in was the packaging — this add-on's namespace,
    module layout and panel, and English throughout. The `.dds` writer it
    brought is now shared by the whole project.

## Watch it work

<video controls muted playsinline preload="none"
       poster="../../images/sign-glow-poster.jpg"
       style="width:100%;border-radius:.2rem">
  <source src="https://github.com/seto3d/void-tools/releases/download/v1.3.1/sign-glow.mp4" type="video/mp4">
  <a href="https://github.com/seto3d/void-tools/releases/download/v1.3.1/sign-glow.mp4">Download the video</a>
</video>

*The halo appearing behind a bar's neon and being tuned in place — Molo
Modding's own capture, cropped to the viewport.*

## How to use it

1. Model or import your lettering as a mesh. Several objects are fine — select
   them all and they are traced together, as one silhouette.
2. In **Materials → Sign Glow**, set the **Resolution** and the **Colour** you
   want to start from. Both stay changeable afterwards.
3. Press **Create Sign Glow**. A plane appears behind the letters, already
   glowing in the viewport.
4. Everything else is on the **Selected Glow** panel, and everything there is
   live.

## The settings

### Halo

| Setting | What it does |
| --- | --- |
| **Colour** | What the halo glows. Its **alpha** scales the whole thing — pull it down for a sign that is meant to be dim rather than off. |
| **Core Size** | The tight glow hugging the letters, as a fraction of the texture's longer side. Small values keep the letterforms readable. |
| **Core Intensity** | How bright that inner glow is. |
| **Halo Size** | The wide bloom behind the letters — the part that reads from across the street. |
| **Halo Intensity** | How bright the bloom is. Turn it to 0 for a hard neon outline with no atmosphere around it. |

The two layers are the whole idea. One blur is either a tight outline or a soft
cloud; a real sign is both at once, and the two sizes are what let you say how
much of each.

### Plane

| Setting | What it does |
| --- | --- |
| **Resolution** | Pixels along the longer side. The short side follows your sign's aspect ratio, so pixels stay square whatever shape it is. |
| **Auto Fit** | Sizes the plane from the halo itself, so a wider bloom grows the plane to hold it rather than being clipped by it. On by default. |
| **Padding** | The manual version of the same margin, when Auto Fit is off. |
| **Offset Behind** | How far behind the frontmost letter the plane sits. Big enough that it does not z-fight, small enough that it does not detach. |
| **Edge Fade** | How far in from the border the plane's `Color 1` alpha climbs from 0 to 1, as a fraction of its shorter side. |

The plane is not a bare quad: it is a bordered grid whose outer ring of
vertices carries **alpha 0**. `Color 1`'s alpha is what the emissive shader
blends by, so without that ring the surface would stop at a hard rectangle
even though the halo on it had already faded to nothing — which in game reads
as a faintly lit box of air around the sign. Edge Fade is how wide that fading
band is.

### Viewport

**Preview Strength** is the emission of the viewport material only. It is not
exported and the game never sees it — it exists so you can see what you are
doing under Blender's own lighting, which is not GTA's.

## Getting it into the game

**The new glow already wears the shader**, if Sollumz is available: a
**`emissive_additive_alpha.sps`** material pointing at the generated halo.
Additive is the right shader here — a glow is light *added* to what is behind
it, and the halo's own alpha is its shape.

**Nothing is written to your drive until you ask.** Create leaves the texture
**packed** in the .blend, which is all the viewport and the material need. Two
buttons put it on disk, and only when pressed:

- **Export for Sollumz** writes the halo as an uncompressed `.dds` into a
  `textures/` folder beside your `.blend`, repoints the image at that file, and
  rebuilds the material around it. Sollumz embeds whatever the image *points
  at*, so this is the step that makes the sign exportable — a material built
  around a packed image exports carrying nothing.
- **Save DDS** writes the texture wherever you choose and leaves the material
  alone, for when you are assembling a `.ytd` by hand.

**After Export, the `.dds` follows your sliders.** Once the image is a file
reference every rebuild rewrites it, so what is on disk stays the halo you are
looking at rather than the one it was exported as.

Export is also the answer when the shader could not be built or the answer has
changed: a glow made on a machine with no Sollumz, a different shader typed
into the field above, or a `.blend` you have since saved somewhere else and
want the texture beside.

!!! tip "If your Sollumz does not have that shader"

    Shader tables differ between Sollumz versions. Rather than failing, the
    tool falls back to the next emissive shader that exists and tells you which
    one it used. The magnifier button beside Export lists every emissive shader
    your installation actually carries.

!!! info "Everything except Export works without Sollumz"

    Tracing the silhouette, generating the halo and previewing it are plain
    Blender. Only the last step needs Sollumz, and that is the only place this
    tool mentions it.

## Notes

- **Your lettering is never modified.** It is read — evaluated, so modifiers
  and scale count — and nothing else.
- **The plane inherits the sign's rotation.** Its own axes are the sign's, so
  dragging it along Z moves it up the sign rather than up the map.
- **A hand-moved glow stays where you put it.** Use **Pin Position** after
  nudging it, and rebuilds stop snapping it back onto the lettering. This is
  the same Position section every generated object in the add-on has.
- **The texture is uncompressed A8R8G8B8.** That is the variant everything in
  the GTA pipeline reads without argument, and a halo is a smooth gradient —
  exactly what block compression ruins. A 512×512 halo is about 1 MB; compress
  it in a texture tool afterwards if the budget needs it.
