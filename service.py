"""
Foreground service while downloading
Keeps Android from cutting the network
Binds the app process to share its priority
"""
import time

from jnius import PythonJavaClass, autoclass, java_method


class Connection(PythonJavaClass):
    __javainterfaces__ = ["android/content/ServiceConnection"]
    __javacontext__ = "app"

    @java_method("(Landroid/content/ComponentName;Landroid/os/IBinder;)V")
    def onServiceConnected(self, name, binder):
        pass

    @java_method("(Landroid/content/ComponentName;)V")
    def onServiceDisconnected(self, name):
        pass


service = autoclass("org.kivy.android.PythonService").mService
Context = autoclass("android.content.Context")
anchor = autoclass("io.github.eggplanta.downloadity.DownloadAnchor")
connection = Connection()
service.bindService(
    autoclass("android.content.Intent")(service, anchor),
    connection,
    Context.BIND_AUTO_CREATE | Context.BIND_IMPORTANT,
)

while True:
    time.sleep(3600)
