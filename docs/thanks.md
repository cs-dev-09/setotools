# Thanks

Seto Tools is free, and it stays free. It is also built in the open, which
means it gets better when people turn up — with a pull request, with a bug
report carrying a .blend, or by funding the time it takes.

This page is where that is recorded.

## Contributors

People whose code is in the add-on you installed.

### [@cs-dev-09](https://github.com/cs-dev-09)

**The Vertex Colour picker** —
[#1](https://github.com/seto3d/setotools/pull/1)

Every tool used to write one fixed green into `Color 1`. Changing it meant
going into Vertex Paint and doing it by hand, which quietly destroyed the alpha
channel unless you remembered to untick **Affect Alpha** — and the alpha is the
part the decal shaders actually blend by, so the damage was invisible until you
looked for it.

It is a preset list on the finished object now — Green, Red, White, Blue,
Yellow, or Custom with a swatch — and picking a colour cannot touch the alpha.
See [choosing the colour](concepts.md#choosing-the-colour).

The PR arrived tested, followed the project's conventions closely, and passed
the whole suite on both supported Blender versions on the first run. That is
rarer than it should be, and it is why it went in the same day.

## Sponsors

### [@Zydrec](https://github.com/Zydrec)

The first person to fund this work through
[GitHub Sponsors](https://github.com/sponsors/seto3d).

A tool that is free either way is not owed that. It pays for the unglamorous
half — the day spent finding out that two tools' bevels were quietly rounding
each other's edges, the test suite that now catches it, this documentation.
Thank you.

## Being listed here

Sponsors are listed only if they are **public** on
[the sponsors page](https://github.com/sponsors/seto3d); a private sponsorship
stays private and is thanked privately.

Contributors are listed once their pull request is merged, since the commit is
public either way.

Either way: if you would rather not appear here, say so on
[the issues](https://github.com/seto3d/setotools/issues) and you will be
removed, no reason needed.

## Standing on

Seto Tools would not exist without [Sollumz](https://docs.sollumz.org), which
does the hard part — the shaders, the export, the whole GTA V pipeline inside
Blender. Everything here builds on top of it.
