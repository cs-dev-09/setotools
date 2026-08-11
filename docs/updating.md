# Updating

The **Updates** panel at the top of the tab updates the add-on from inside
Blender. When a new release exists, its version appears on the panel header,
and **Install Update** downloads it and installs it over the current one with
your settings intact.

## The startup check

One version check runs per Blender start: once, off the main thread, and silent
if it fails. That is what lets the panel header carry the news without you
having to go and ask.

What it does:

- asks GitHub for the latest release of this repository
- compares the version number with the installed one

What it does **not** do: it carries nothing about you, your scene, or your
machine. It is the only network traffic in the entire add-on, and the test
suite enforces that — the updater package is the only code that can reach the
network at all.

**Check for updates on startup** in the add-on preferences turns it off. With
it off, **Check for Updates** in the panel still works when you press it.

## Installing manually

Nothing stops you doing it the ordinary way: download `seto_tools.zip` from the
[releases page](https://github.com/seto3d/setotools/releases) and install from
disk over the top. Restart Blender afterwards.

## After an update

**Restart Blender.** Python keeps the old modules loaded until you do, so a
freshly installed version can otherwise behave exactly like the one it
replaced — which looks like the update having done nothing.
