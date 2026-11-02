import sys
from os.path import exists, join

import sh
from pythonforandroid.logger import shprint
from pythonforandroid.recipe import Recipe


class CharsetNormalizerRecipe(Recipe):
    """
    Pure wheel, p4a fails on the Android one
    """
    version = "3.5.2"
    url = None
    depends = ["python3"]

    def should_build(self, arch):
        return not exists(join(self.ctx.get_site_packages_dir(arch), "charset_normalizer"))

    def build_arch(self, arch):
        shprint(
            sh.Command(sys.executable), "-m", "pip", "install",
            "--target", self.ctx.get_site_packages_dir(arch),
            "--no-deps",
            "--only-binary=:all:",
            "--platform", "any",
            "--implementation", "py",
            "--abi", "none",
            "--python-version", "3.13",
            f"charset-normalizer=={self.version}",
        )


recipe = CharsetNormalizerRecipe()
