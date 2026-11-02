from multiprocessing import cpu_count
from os.path import dirname, join

import sh
from pythonforandroid.logger import shprint
from pythonforandroid.recipe import Recipe
from pythonforandroid.util import current_directory


def component_flags(path):
    """
    components.txt lines to configure flags
    """
    flags = []
    with open(path) as f:
        for line in f:
            line = line.split("#")[0].strip()
            if not line:
                continue
            kind, names = line.split(":")
            flags += [f"--enable-{kind.strip()}={name}" for name in names.split()]
    return flags


class FFmpegCliRecipe(Recipe):
    """
    Trimmed static ffmpeg executable
    Shipped as libffmpeg.so, Android allows exec
    """
    version = "9.0.2"
    url = "https://ffmpeg.org/releases/ffmpeg-{version}.tar.xz"
    depends = ["mp3lame", "x264", "dav1d"]
    built_libraries = {"libffmpeg.so": "."}

    def build_arch(self, arch):
        lame = self.get_recipe("mp3lame", self.ctx).get_build_dir(arch.arch)
        x264 = self.get_recipe("x264", self.ctx).get_build_dir(arch.arch)
        dav1d = self.get_recipe("dav1d", self.ctx)

        with current_directory(self.get_build_dir(arch.arch)):
            env = self.get_recipe_env(arch, with_flags_in_cc=False)
            env["PKG_CONFIG_LIBDIR"] = ":".join([
                join(x264, "lib", "pkgconfig"),
                dav1d.pkgconfig_dir(arch),
            ])

            cflags = f"{env['CFLAGS']} -I{lame}/include -I{x264}/include"
            # p4a LDFLAGS lack the target
            ldflags = f"-target {arch.target} {env['LDFLAGS']} -L{lame}/lib -L{x264}/lib"

            flags = [
                "--target-os=android",
                "--arch=aarch64" if "arm64" in arch.arch else "--arch=x86_64",
                "--enable-cross-compile",
                f"--cc={env['CC']}",
                f"--ar={env['AR']}",
                f"--ranlib={env['RANLIB']}",
                f"--nm={self.ctx.ndk.llvm_nm}",
                f"--strip={self.ctx.ndk.llvm_strip}",
                f"--sysroot={self.ctx.ndk.sysroot}",
                f"--extra-cflags={cflags}",
                f"--extra-ldflags={ldflags}",
                "--extra-libs=-lm",
                "--pkg-config=pkg-config",
                "--pkg-config-flags=--static",

                # Only the ffmpeg program
                "--disable-everything",
                "--disable-autodetect",
                "--disable-doc",
                "--disable-debug",
                "--disable-ffplay",
                "--disable-ffprobe",
                "--disable-avdevice",
                "--disable-network",
                "--enable-ffmpeg",
                "--enable-static",
                "--disable-shared",
                "--enable-pic",

                # External codecs
                "--enable-gpl",
                "--enable-libmp3lame",
                "--enable-libx264",
                "--enable-libdav1d",
                "--enable-zlib",
            ]
            flags += component_flags(join(dirname(__file__), "components.txt"))

            shprint(sh.Command("./configure"), *flags, _env=env)
            shprint(sh.make, "-j", str(cpu_count()), _env=env)
            shprint(sh.cp, "ffmpeg", "libffmpeg.so")


recipe = FFmpegCliRecipe()
