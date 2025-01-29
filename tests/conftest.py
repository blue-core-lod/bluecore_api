# needed to import packages in the plugin

import pathlib
import sys


root_directory = pathlib.Path(__file__).parent.parent
dir = root_directory / "src/"

sys.path.append(str(dir))