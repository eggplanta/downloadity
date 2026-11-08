"""
App texts in each language
English is the source and fallback
Plural entries are (one, other)
"""
LANGUAGES = ("en", "pt", "es", "zh")

# Each name in its own language
NAMES = {
    "en": "english",
    "pt": "português",
    "es": "español",
    "zh": "中文（繁體）",
}

STRINGS = {
    # Home
    "checking": {"en": "checking", "pt": "verificando", "es": "comprobando", "zh": "檢查中"},
    "paste_link": {"en": "paste the link:", "pt": "cole o link:", "es": "pega el link:", "zh": "貼上連結："},
    "download_button": {"en": "DOWNLOAD", "pt": "BAIXAR", "es": "DESCARGAR", "zh": "下載"},
    "blocked": {
        "en": "YouTube is blocking this network\ntry again later or use mobile data",
        "pt": "o YouTube está bloqueando esta rede\ntente mais tarde ou use dados móveis",
        "es": "YouTube está bloqueando esta red\ninténtalo más tarde o usa datos móviles",
        "zh": "YouTube 正在封鎖此網路\n請稍後再試或改用行動數據",
    },
    "unexpected_error": {"en": "unexpected error", "pt": "erro inesperado", "es": "error inesperado", "zh": "發生未預期的錯誤"},

    # Qualities
    "audio_header": {"en": "♪ AUDIO", "pt": "♪ ÁUDIO", "es": "♪ AUDIO", "zh": "♪ 音訊"},
    "video_header": {"en": "▶ VIDEO", "pt": "▶ VÍDEO", "es": "▶ VÍDEO", "zh": "▶ 影片"},
    "no_options": {"en": "no options found", "pt": "nenhuma opção encontrada", "es": "no se encontraron opciones", "zh": "找不到可用的選項"},

    # Known playlist
    "downloaded_before": {
        "en": "this playlist was\ndownloaded before\n({count})\n\ndownload:",
        "pt": "esta playlist já\nfoi baixada antes\n({count})\n\nbaixar:",
        "es": "esta lista ya se\ndescargó antes\n({count})\n\ndescargar:",
        "zh": "這個播放清單\n之前已經下載過\n（{count}）\n\n下載：",
    },
    "new_items": {
        "en": ("{n} new item", "{n} new items"),
        "pt": ("{n} item novo", "{n} itens novos"),
        "es": ("{n} elemento nuevo", "{n} elementos nuevos"),
        "zh": ("{n} 個新項目", "{n} 個新項目"),
    },
    "no_new_items": {"en": "no new items", "pt": "nenhum item novo", "es": "ningún elemento nuevo", "zh": "沒有新項目"},
    "all": {"en": "all", "pt": "todos", "es": "todos", "zh": "全部"},
    "new": {"en": "new", "pt": "novos", "es": "nuevos", "zh": "新項目"},

    # Download questions
    "storage_use": {
        "en": "this will use {size}\nof your storage",
        "pt": "isso vai usar {size}\ndo seu armazenamento",
        "es": "esto usará {size}\nde tu almacenamiento",
        "zh": "這將使用 {size}\n的儲存空間",
    },
    "full_or_cut": {
        "en": "download the full\nvideo or cut it?",
        "pt": "baixar o vídeo\ninteiro ou cortar?",
        "es": "¿descargar el video\ncompleto o recortarlo?",
        "zh": "要下載完整影片\n還是剪輯片段？",
    },
    "cut_video": {"en": "cut video", "pt": "cortar", "es": "recortar", "zh": "剪輯"},
    "full_video": {"en": "full video", "pt": "inteiro", "es": "completo", "zh": "完整影片"},
    "download_in": {"en": "download in {quality}?", "pt": "baixar em {quality}?", "es": "¿descargar en {quality}?", "zh": "以 {quality} 下載？"},
    "cancel": {"en": "cancel", "pt": "cancelar", "es": "cancelar", "zh": "取消"},
    "confirm": {"en": "confirm", "pt": "confirmar", "es": "confirmar", "zh": "確認"},
    "cut_the_video": {"en": "cut the video:", "pt": "corte o vídeo:", "es": "recorta el video:", "zh": "剪輯影片："},
    "start": {"en": "start", "pt": "início", "es": "inicio", "zh": "開始"},
    "end": {"en": "end", "pt": "fim", "es": "fin", "zh": "結束"},
    "video_length": {"en": "video length: {time}", "pt": "duração do vídeo: {time}", "es": "duración del video: {time}", "zh": "影片長度：{time}"},
    "download": {"en": "download", "pt": "baixar", "es": "descargar", "zh": "下載"},
    "invalid_items": {
        "en": "these items are invalid\nand won't be downloaded:",
        "pt": "estes itens são inválidos\ne não serão baixados:",
        "es": "estos elementos no\nson válidos y no\nse descargarán:",
        "zh": "以下項目無效，\n將不會下載：",
    },
    "unknown_title": {"en": "unknown title", "pt": "título desconhecido", "es": "título desconocido", "zh": "未知標題"},
    "ok": {"en": "OK", "pt": "OK", "es": "OK", "zh": "確定"},

    # Download end
    "download_failed": {
        "en": "download failed\n\n{error}",
        "pt": "o download falhou\n\n{error}",
        "es": "la descarga falló\n\n{error}",
        "zh": "下載失敗\n\n{error}",
    },
    "download_finished": {
        "en": "download finished!\n\nyour files are in:\n{path}",
        "pt": "download concluído!\n\nseus arquivos estão em:\n{path}",
        "es": "¡descarga completa!\n\ntus archivos están en:\n{path}",
        "zh": "下載完成！\n\n檔案位於：\n{path}",
    },
    "share": {"en": "share", "pt": "compartilhar", "es": "compartir", "zh": "分享"},
    "share_failed": {
        "en": "could not share\nthis file",
        "pt": "não foi possível\ncompartilhar o arquivo",
        "es": "no se pudo\ncompartir el archivo",
        "zh": "無法分享\n此檔案",
    },
    "items_failed": {
        "en": ("{n} item(s) failed:", "{n} item(s) failed:"),
        "pt": ("{n} item falhou:", "{n} itens falharam:"),
        "es": ("{n} elemento falló:", "{n} elementos fallaron:"),
        "zh": ("{n} 個項目失敗：", "{n} 個項目失敗："),
    },

    # Notification
    "downloading": {"en": "downloading", "pt": "baixando", "es": "descargando", "zh": "下載中"},
    "downloading_name": {"en": 'downloading "{name}"', "pt": 'baixando "{name}"', "es": 'descargando "{name}"', "zh": "正在下載「{name}」"},
    "downloads_channel": {"en": "downloads", "pt": "downloads", "es": "descargas", "zh": "下載"},

    # Settings
    "settings": {"en": "settings", "pt": "configurações", "es": "ajustes", "zh": "設定"},
    "language": {"en": "language", "pt": "idioma", "es": "idioma", "zh": "語言"},
    "donate": {"en": "donate ♥", "pt": "doar ♥", "es": "donar ♥", "zh": "贊助 ♥"},

    # App updates
    "new_version": {
        "en": "new version v{version}\n\nupdate now?",
        "pt": "nova versão v{version}\n\natualizar agora?",
        "es": "nueva versión v{version}\n\n¿actualizar ahora?",
        "zh": "新版本 v{version}\n\n要立即更新嗎？",
    },
    "yes": {"en": "yes", "pt": "sim", "es": "sí", "zh": "是"},
    "no": {"en": "no", "pt": "não", "es": "no", "zh": "否"},
    "allow_install": {
        "en": "to update, allow your\nphone to install apps\nfrom this source\n\nthen come back here",
        "pt": "para atualizar, permita\nque o celular instale\napps desta fonte\n\ndepois volte aqui",
        "es": "para actualizar, permite\nque el teléfono instale\napps de esta fuente\n\nluego vuelve aquí",
        "zh": "若要更新，請允許\n手機安裝來自\n此來源的應用程式\n\n然後回到這裡",
    },
    "open_settings": {"en": "settings", "pt": "ajustes", "es": "ajustes", "zh": "設定"},
    "later": {"en": "later", "pt": "depois", "es": "luego", "zh": "稍後"},
    "downloading_version": {"en": "downloading v{version}", "pt": "baixando v{version}", "es": "descargando v{version}", "zh": "正在下載 v{version}"},
    "update_failed": {
        "en": "update failed\n\ntry again later",
        "pt": "a atualização falhou\n\ntente mais tarde",
        "es": "la actualización falló\n\ninténtalo más tarde",
        "zh": "更新失敗\n\n請稍後再試",
    },
}

# Library errors, English text -> translations
ERRORS = {
    "this is not a link": {"pt": "isto não é um link", "es": "esto no es un link", "zh": "這不是連結"},
    "this site is not supported": {"pt": "este site não é suportado", "es": "este sitio no es compatible", "zh": "不支援此網站"},
    "this video is private": {"pt": "este vídeo é privado", "es": "este video es privado", "zh": "這是私人影片"},
    "playlist is private or doesn't exist": {
        "pt": "a playlist é privada ou não existe",
        "es": "la lista es privada o no existe",
        "zh": "播放清單為私人或不存在",
    },
    "age-restricted, needs a login": {
        "pt": "restrito por idade, precisa de login",
        "es": "restringido por edad, requiere iniciar sesión",
        "zh": "有年齡限制，需要登入",
    },
    "members-only content": {"pt": "conteúdo só para membros", "es": "contenido solo para miembros", "zh": "僅限會員的內容"},
    "not available in your country": {"pt": "indisponível no seu país", "es": "no disponible en tu país", "zh": "在你的國家／地區無法觀看"},
    "this live hasn't started yet": {"pt": "esta live ainda não começou", "es": "este directo aún no ha empezado", "zh": "這場直播尚未開始"},
    "this premiere hasn't started yet": {"pt": "esta estreia ainda não começou", "es": "este estreno aún no ha empezado", "zh": "這場首播尚未開始"},
    "this video is unavailable": {"pt": "este vídeo está indisponível", "es": "este video no está disponible", "zh": "無法觀看這部影片"},
    "page not found": {"pt": "página não encontrada", "es": "página no encontrada", "zh": "找不到頁面"},
    "no internet connection": {"pt": "sem conexão com a internet", "es": "sin conexión a internet", "zh": "沒有網路連線"},
    "connection timed out": {"pt": "a conexão expirou", "es": "se agotó el tiempo de conexión", "zh": "連線逾時"},
    "no match found on YouTube": {"pt": "nada encontrado no YouTube", "es": "no se encontró en YouTube", "zh": "在 YouTube 上找不到相符項目"},
    "couldn't read this link": {"pt": "não foi possível ler este link", "es": "no se pudo leer este link", "zh": "無法讀取此連結"},
    "this playlist is empty": {"pt": "esta playlist está vazia", "es": "esta lista está vacía", "zh": "這個播放清單是空的"},
    "no playable items found": {
        "pt": "nenhum item disponível encontrado",
        "es": "no se encontraron elementos disponibles",
        "zh": "找不到可播放的項目",
    },
    "spotify: private or unavailable": {
        "pt": "spotify: privado ou indisponível",
        "es": "spotify: privado o no disponible",
        "zh": "spotify：私人或無法使用",
    },
    "spotify: only tracks, albums\nand playlists": {
        "pt": "spotify: só músicas, álbuns\ne playlists",
        "es": "spotify: solo canciones, álbumes\ny listas",
        "zh": "spotify：僅支援歌曲、\n專輯和播放清單",
    },
    "spotify: couldn't read this link": {
        "pt": "spotify: não foi possível ler este link",
        "es": "spotify: no se pudo leer este link",
        "zh": "spotify：無法讀取此連結",
    },
}

current = "en"


def system_language(code):
    """
    Locale code -> supported language
    Any Chinese gets traditional
    """
    language = (code or "").replace("-", "_").split("_")[0].lower()
    return language if language in LANGUAGES else "en"


def set_language(language):
    global current
    current = language if language in LANGUAGES else "en"


def t(key, n=None, **values):
    texts = STRINGS[key]
    text = texts.get(current, texts["en"])
    if isinstance(text, tuple):
        text = text[0] if n == 1 else text[1]
    return text.format(n=n, **values)


def error(text):
    """
    Translates library errors
    Unknown first lines stay as they are
    """
    if current == "en" or not text:
        return text
    if text in ERRORS:
        return ERRORS[text][current]
    first, newline, rest = text.partition("\n")
    if first in ERRORS:
        return ERRORS[first][current] + newline + rest
    return text


def all_texts():
    # Every string, for the font subset
    for texts in STRINGS.values():
        for text in texts.values():
            yield from text if isinstance(text, tuple) else (text,)
    for texts in ERRORS.values():
        yield from texts.values()
    yield from NAMES.values()
