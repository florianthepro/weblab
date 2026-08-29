"""Symbol fuer den Windows-Build erzeugen."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "software", "weblab"))
import icon  # noqa: E402

target = os.path.join(HERE, "weblab.ico")
with open(target, "wb") as fh:
    fh.write(icon.ico_bytes())
print(target)
