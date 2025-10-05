import os
import sys

repo_root = os.path.dirname(__file__)
extra = os.path.join(repo_root, "hw2", "hw")
if os.path.isdir(extra) and extra not in sys.path:
    sys.path.insert(0, extra)