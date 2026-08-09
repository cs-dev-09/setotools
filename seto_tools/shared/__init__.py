# Code shared by every Seto tool.
#
# These are plain modules the tools import. Keeping the Sollumz integration in
# one place is the main reason this package exists: the three tools used to
# carry an identical copy each.
#
# The one exception is groups.py, which registers the two section panels every
# tool parents itself to. It has to register before any tool does.
