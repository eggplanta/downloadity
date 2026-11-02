from multiprocessing import cpu_count
from os.path import realpath

import sh
from pythonforandroid.logger import shprint
from pythonforandroid.recipe import Recipe
from pythonforandroid.util import current_directory


class X264Recipe(Recipe):
    """
    Static x264 with NEON asm
    The p4a libx264 disables asm
    """
    version = "b35605ace3ddf7c1a5d67a2eb553f034aef41d55"
    url = "https://code.videolan.org/videolan/x264/-/archive/{version}/x264-{version}.tar.gz"
    built_libraries = {"libx264.a": "lib"}

    def build_arch(self, arch):
        with current_directory(self.get_build_dir(arch.arch)):
            env = self.get_recipe_env(arch)
            # Clang assembles the NEON files
            env["AS"] = env["CC"]
            shprint(
                sh.Command("./configure"),
                f"--host={arch.command_prefix}",
                f"--prefix={realpath('.')}",
                "--enable-static",
                "--enable-pic",
                "--disable-cli",
                "--disable-opencl",
                "--bit-depth=8",
                _env=env,
            )
            shprint(sh.make, "-j", str(cpu_count()), _env=env)
            shprint(sh.make, "install", _env=env)


recipe = X264Recipe()
