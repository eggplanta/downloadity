from multiprocessing import cpu_count
from os.path import realpath

import sh
from pythonforandroid.logger import shprint
from pythonforandroid.recipe import Recipe
from pythonforandroid.util import current_directory


class LameRecipe(Recipe):
    """
    Static libmp3lame for the MP3 encoder
    """
    version = "3.100"
    url = "https://downloads.sourceforge.net/project/lame/lame/{version}/lame-{version}.tar.gz"
    built_libraries = {"libmp3lame.a": "lib"}

    def build_arch(self, arch):
        with current_directory(self.get_build_dir(arch.arch)):
            env = self.get_recipe_env(arch)
            shprint(
                sh.Command("./configure"),
                f"--host={arch.command_prefix}",
                f"--prefix={realpath('.')}",
                "--enable-static",
                "--disable-shared",
                "--with-pic",
                "--disable-frontend",
                "--disable-decoder",
                "--disable-gtktest",
                _env=env,
            )
            shprint(sh.make, "-j", str(cpu_count()), _env=env)
            shprint(sh.make, "install", _env=env)


recipe = LameRecipe()
