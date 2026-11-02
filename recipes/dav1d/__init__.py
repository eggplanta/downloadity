from os.path import join, realpath

import sh
from pythonforandroid.logger import shprint
from pythonforandroid.recipe import Recipe
from pythonforandroid.util import current_directory


class Dav1dRecipe(Recipe):
    """
    Static dav1d, AV1 decoder for ffmpeg
    """
    version = "1.5.4"
    url = "https://code.videolan.org/videolan/dav1d/-/archive/{version}/dav1d-{version}.tar.gz"
    built_libraries = {"libdav1d.a": "install/lib"}

    def cross_file(self, arch, env):
        def quoted(flags):
            return ", ".join(f"'{flag}'" for flag in flags.split())

        return "\n".join([
            "[binaries]",
            f"c = '{env['CC']}'",
            f"ar = '{env['AR']}'",
            f"strip = '{self.ctx.ndk.llvm_strip}'",
            "[built-in options]",
            f"c_args = [{quoted(env['CFLAGS'])}]",
            f"c_link_args = [{quoted(env['LDFLAGS'])}]",
            "[host_machine]",
            "system = 'android'",
            "cpu_family = 'aarch64'" if "arm64" in arch.arch else "cpu_family = 'x86_64'",
            "cpu = 'aarch64'" if "arm64" in arch.arch else "cpu = 'x86_64'",
            "endian = 'little'",
        ])

    def build_arch(self, arch):
        with current_directory(self.get_build_dir(arch.arch)):
            env = self.get_recipe_env(arch, with_flags_in_cc=False)
            with open("android.cross", "w") as f:
                f.write(self.cross_file(arch, env))

            shprint(
                sh.meson, "setup", "build",
                "--cross-file", "android.cross",
                f"--prefix={realpath('install')}",
                "--libdir=lib",
                "--buildtype=release",
                "--default-library=static",
                "-Denable_tools=false",
                "-Denable_tests=false",
                "-Denable_examples=false",
                _env=env,
            )
            shprint(sh.ninja, "-C", "build", "install", _env=env)

    def pkgconfig_dir(self, arch):
        return join(self.get_build_dir(arch.arch), "install", "lib", "pkgconfig")


recipe = Dav1dRecipe()
