#!/usr/bin/env python3
"""
SwitchUK - автоперемикач розкладки EN <-> UA (аналог Punto Switcher).

* Стежить за набраним словом; після пробілу, якщо слово набране не в тій
  розкладці ("ghbdsn" -> "привіт"), стирає його, друкує правильний варіант
  і перемикає розкладку.
* Ctrl+Alt+Space (або Pause на Windows) - конвертувати останнє слово.
* Ctrl+Alt+Enter (або Shift+Pause на Windows) - конвертувати виділений текст.
* Іконка в треї: увімкнути/вимкнути автозаміну, вийти.

Нічого не пишеться на диск і не надсилається в мережу.
"""
import re
import sys
import threading
import time
from pathlib import Path

import pyperclip
import pystray
from PIL import Image, ImageDraw
from pynput import keyboard, mouse
from pynput.keyboard import Key, KeyCode

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform.startswith("win")

# --------------------------------------------------------------------------
# Розкладки: англійська (QWERTY) <-> українська (ЙЦУКЕН, стандарт Windows/ПК)
# --------------------------------------------------------------------------
EN_LOW = "qwertyuiop[]\\asdfghjkl;'zxcvbnm,./`"
UK_LOW = "йцукенгшщзхїґфівапролджєячсмитьбю.'"
EN_UP = 'QWERTYUIOP{}|ASDFGHJKL:"ZXCVBNM<>?~'
UK_UP = "ЙЦУКЕНГШЩЗХЇҐФІВАПРОЛДЖЄЯЧСМИТЬБЮ,₴"
assert len(EN_LOW) == len(UK_LOW) and len(EN_UP) == len(UK_UP)

EN_TO_UK = dict(zip(EN_LOW + EN_UP, UK_LOW + UK_UP))
UK_TO_EN = {v: k for k, v in EN_TO_UK.items()}
UK_TO_EN["ʼ"] = "`"
WORD_CHARS = set(EN_TO_UK) | set(UK_TO_EN)


def convert(text, src):
    table = EN_TO_UK if src == "en" else UK_TO_EN
    return "".join(table.get(c, c) for c in text)


def detect(word):
    lat = sum(c.isascii() and c.isalpha() for c in word)
    cyr = sum("\u0400" <= c <= "\u04ff" for c in word)
    if lat and not cyr:
        return "en"
    if cyr and not lat:
        return "uk"
    return None


# --------------------------------------------------------------------------
# Визначення "чи слово схоже на мову": словники (за наявності) + біграми
# --------------------------------------------------------------------------
EN_BG = set(
    "th he in er an re on at en nd ti es or te of ed is it al ar st to nt ng se "
    "ha as ou io le ve co me de hi ri ro ic ne ea ra ce li ch ll be ma si om ur "
    "el lo ow wo rl ld ll ta ho ot ut ke ly ay ee ss ba ad ab ac ag ai am ap av "
    "bo br ca cl cr da di do dr ef ex fa fi fo fr ge gi go gr gu hu id ig il im "
    "ir ke la lu mi mo mu na no nu ob oc of ol op os ow pa pe ph pl po pr pu qu "
    "rs sa sc sh sp su tr tu un up us ut wa we wh wi yo".split()
)
UK_BG = set(
    "на ст по ен ко ра ні но ов пр то ть не ал ро ан ли ка ти ри ер ва ор ми ві "
    "ий ля ою ня ол от ог ом ід ле ла ат ус ск зв ив іт ан ба бі бо бу ви во ві "
    "га го гр да де ди до др ді ем ес жи за зн зо ий ик ил ин ир ис ит ій ін іс "
    "іт ія ка кл кр ку ла лі лю ма ме мі мо му на нь нн об ов од ож ок он оп ос "
    "па пе пи пі пл по пу ре рі ри ро ру ря са се си сі сл сп су та те ти тр ту "
    "ть ує ун уп ур ут фо хо ці це ча че чи чо шн ще юч ює ює як яв ям ят ях".split()
)
CORE_RE = re.compile(r"^[\W_]+|[\W_]+$")


def core(s):
    return CORE_RE.sub("", s).lower()


def bigram_score(s, lang):
    s = core(s)
    if len(s) < 2:
        return 0.0
    bg = EN_BG if lang == "en" else UK_BG
    pairs = [s[i:i + 2] for i in range(len(s) - 1)]
    return sum(p in bg for p in pairs) / len(pairs)


def load_dict(lang):
    """Шукає uk.txt/uk.dic та en.txt/en.dic (hunspell теж підходить)."""
    dirs = [Path.home() / ".ukrswitcher", Path(__file__).resolve().parent]
    if getattr(sys, "_MEIPASS", None):
        dirs.append(Path(sys._MEIPASS))
    for d in dirs:
        for ext in ("txt", "dic"):
            p = d / f"{lang}.{ext}"
            if p.is_file():
                words = set()
                with open(p, encoding="utf-8", errors="ignore") as f:
                    for i, line in enumerate(f):
                        line = line.strip()
                        if not line or (i == 0 and line.isdigit()):
                            continue
                        words.add(line.split("/")[0].lower())
                return words
    return None


# --------------------------------------------------------------------------
# Перемикання розкладки ОС
# --------------------------------------------------------------------------
if IS_WIN:
    import ctypes
    from ctypes import wintypes

    _u32 = ctypes.WinDLL("user32", use_last_error=True)
    _u32.LoadKeyboardLayoutW.argtypes = [wintypes.LPCWSTR, wintypes.UINT]
    _u32.LoadKeyboardLayoutW.restype = ctypes.c_void_p
    _u32.GetForegroundWindow.restype = ctypes.c_void_p
    _u32.PostMessageW.argtypes = [ctypes.c_void_p, wintypes.UINT,
                                  wintypes.WPARAM, wintypes.LPARAM]

    def switch_layout(lang):
        klid = {"uk": "00000422", "en": "00000409"}[lang]
        hkl = _u32.LoadKeyboardLayoutW(klid, 1)  # KLF_ACTIVATE
        hwnd = _u32.GetForegroundWindow()
        if hwnd and hkl:
            _u32.PostMessageW(hwnd, 0x0050, 0, int(hkl))  # WM_INPUTLANGCHANGEREQUEST

elif IS_MAC:
    import ctypes
    from ctypes import c_bool, c_char_p, c_int32, c_long, c_uint32, c_void_p

    _carbon = ctypes.cdll.LoadLibrary(
        "/System/Library/Frameworks/Carbon.framework/Carbon")
    _cf = ctypes.cdll.LoadLibrary(
        "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
    _sys = ctypes.cdll.LoadLibrary("/usr/lib/libSystem.B.dylib")

    _carbon.TISCreateInputSourceList.restype = c_void_p
    _carbon.TISCreateInputSourceList.argtypes = [c_void_p, c_bool]
    _carbon.TISGetInputSourceProperty.restype = c_void_p
    _carbon.TISGetInputSourceProperty.argtypes = [c_void_p, c_void_p]
    _carbon.TISSelectInputSource.restype = c_int32
    _carbon.TISSelectInputSource.argtypes = [c_void_p]
    _cf.CFArrayGetCount.restype = c_long
    _cf.CFArrayGetCount.argtypes = [c_void_p]
    _cf.CFArrayGetValueAtIndex.restype = c_void_p
    _cf.CFArrayGetValueAtIndex.argtypes = [c_void_p, c_long]
    _cf.CFStringGetCString.restype = c_bool
    _cf.CFStringGetCString.argtypes = [c_void_p, c_char_p, c_long, c_uint32]
    _cf.CFRelease.argtypes = [c_void_p]
    _KEY_ID = c_void_p.in_dll(_carbon, "kTISPropertyInputSourceID").value

    _WORK = ctypes.CFUNCTYPE(None, c_void_p)
    _sys.dispatch_async_f.argtypes = [c_void_p, c_void_p, _WORK]
    _MAIN_Q = ctypes.addressof(ctypes.c_char.in_dll(_sys, "_dispatch_main_q"))
    _callbacks = {}

    _PREFERRED = {
        "uk": ["Ukrainian-PC", "Ukrainian"],
        "en": ["ABC", "US", "USExtended"],
    }

    def _mac_select(lang):
        arr = _carbon.TISCreateInputSourceList(None, False)
        if not arr:
            return
        try:
            found = {}
            buf = ctypes.create_string_buffer(256)
            for i in range(_cf.CFArrayGetCount(arr)):
                src = _cf.CFArrayGetValueAtIndex(arr, i)
                sid = _carbon.TISGetInputSourceProperty(src, _KEY_ID)
                if sid and _cf.CFStringGetCString(sid, buf, 256, 0x08000100):
                    found[buf.value.decode().replace("com.apple.keylayout.", "")] = src
            for name in _PREFERRED[lang]:
                if name in found:
                    _carbon.TISSelectInputSource(found[name])
                    return
        finally:
            _cf.CFRelease(arr)

    def switch_layout(lang):
        # З macOS 14 виклики TIS дозволені лише з головного потоку.
        def work(_ctx):
            try:
                _mac_select(lang)
            finally:
                _callbacks.pop(id(cb), None)
        cb = _WORK(work)
        _callbacks[id(cb)] = cb
        _sys.dispatch_async_f(_MAIN_Q, None, cb)
else:
    def switch_layout(lang):
        pass


# --------------------------------------------------------------------------
# Рушій
# --------------------------------------------------------------------------
CTRL = {Key.ctrl, Key.ctrl_l, Key.ctrl_r}
ALT = {Key.alt, Key.alt_l, Key.alt_r, Key.alt_gr}
CMD = {Key.cmd, Key.cmd_l, Key.cmd_r}
SHIFT = {Key.shift, Key.shift_l, Key.shift_r}
MODS = CTRL | ALT | CMD | SHIFT

VK_C = 8 if IS_MAC else 0x43
VK_V = 9 if IS_MAC else 0x56


class Switcher:
    def __init__(self):
        self.kb = keyboard.Controller()
        self.dict_uk = load_dict("uk")
        self.dict_en = load_dict("en")
        self.buf = []
        self.poison = False
        self.last = None
        self.down = set()
        self.busy = False
        self.enabled = True
        self.lock = threading.Lock()

    # --- допоміжне ---
    def held(self, group):
        return any(k in group for k in self.down)

    def reset(self):
        self.buf.clear()
        self.poison = False
        self.last = None

    def spawn(self, fn):
        threading.Thread(target=fn, daemon=True).start()

    def wait_mods(self, timeout=2.0):
        end = time.time() + timeout
        while self.held(MODS) and time.time() < end:
            time.sleep(0.02)

    # --- рішення ---
    def should_convert(self, word, src):
        dst = "uk" if src == "en" else "en"
        alt = convert(word, src)
        d_src = self.dict_en if src == "en" else self.dict_uk
        d_dst = self.dict_uk if src == "en" else self.dict_en
        if d_src is not None and core(word) in d_src:
            return False
        if d_dst is not None and core(alt) in d_dst and len(core(alt)) >= 2:
            return True
        so, sa = bigram_score(word, src), bigram_score(alt, dst)
        return len(core(alt)) >= 3 and sa >= 0.5 and sa - so >= 0.3

    # --- заміна тексту ---
    def _replace(self, word, src, sep):
        dst = "uk" if src == "en" else "en"
        new = convert(word, src)
        self.busy = True
        try:
            time.sleep(0.04)
            for _ in range(len(word) + len(sep)):
                self.kb.tap(Key.backspace)
            switch_layout(dst)
            self.kb.type(new + sep)
            time.sleep(0.05)
        finally:
            time.sleep(0.12)
            self.busy = False
        return new

    def auto_replace(self, word, src):
        with self.lock:
            new = self._replace(word, src, " ")
            self.last = new

    def manual_last(self):
        self.wait_mods()
        with self.lock:
            word = "".join(self.buf)
            if word:
                sep = ""
            elif self.last:
                word, sep = self.last, " "
            else:
                return
            src = detect(word)
            if not src:
                return
            new = self._replace(word, src, sep)
            if sep:
                self.last = new
            else:
                self.buf = list(new)

    def manual_selection(self):
        self.wait_mods()
        with self.lock:
            mod = Key.cmd if IS_MAC else Key.ctrl
            try:
                old = pyperclip.paste()
            except Exception:
                old = ""
            pyperclip.copy("")
            self.busy = True
            try:
                with self.kb.pressed(mod):
                    self.kb.tap(KeyCode.from_vk(VK_C))
                time.sleep(0.15)
                text = pyperclip.paste()
                if text:
                    lat = sum(c.isascii() and c.isalpha() for c in text)
                    cyr = sum("\u0400" <= c <= "\u04ff" for c in text)
                    src = "uk" if cyr > lat else "en"
                    pyperclip.copy(convert(text, src))
                    time.sleep(0.05)
                    with self.kb.pressed(mod):
                        self.kb.tap(KeyCode.from_vk(VK_V))
                    time.sleep(0.25)
                    switch_layout("en" if src == "uk" else "uk")
                pyperclip.copy(old)
            finally:
                time.sleep(0.1)
                self.busy = False
            self.reset()

    # --- обробники подій ---
    def on_press(self, key):
        if key in MODS:
            self.down.add(key)
            return
        if self.busy:
            return

        pause = getattr(Key, "pause", None)
        if pause is not None and key == pause:
            self.spawn(self.manual_selection if self.held(SHIFT) else self.manual_last)
            return
        ctrl, alt, cmd = self.held(CTRL), self.held(ALT), self.held(CMD)
        if ctrl and alt and not cmd and key in (Key.space, Key.enter):
            self.spawn(self.manual_last if key == Key.space else self.manual_selection)
            return
        if ctrl or alt or cmd:
            self.reset()
            return

        if key == Key.space:
            self.on_space()
            return
        if key == Key.backspace:
            if self.buf:
                self.buf.pop()
            return
        ch = getattr(key, "char", None)
        if ch is None:          # Enter, Tab, стрілки, Esc ...
            self.reset()
            return
        self.last = None
        if ch in WORD_CHARS:
            self.buf.append(ch)
        else:                   # цифри та інші символи - слово не чіпаємо
            self.poison = True

    def on_release(self, key):
        self.down.discard(key)

    def on_space(self):
        word, poison = "".join(self.buf), self.poison
        self.reset()
        if not word or poison:
            return
        src = detect(word)
        if not src:
            return
        self.last = word
        if self.enabled and self.should_convert(word, src):
            self.spawn(lambda: self.auto_replace(word, src))


# --------------------------------------------------------------------------
# Трей
# --------------------------------------------------------------------------
def make_icon(enabled):
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    top, bottom = ((0, 87, 183), (255, 215, 0)) if enabled else ((120, 120, 120), (190, 190, 190))
    d.rectangle([4, 10, 60, 32], fill=top)
    d.rectangle([4, 32, 60, 54], fill=bottom)
    return img


def main():
    if not (IS_WIN or IS_MAC):
        print("Підтримуються лише Windows і macOS.")
        return
    sw = Switcher()
    kl = keyboard.Listener(on_press=sw.on_press, on_release=sw.on_release)
    ml = mouse.Listener(on_click=lambda *a: sw.reset())
    kl.start()
    ml.start()

    def toggle(icon, item):
        sw.enabled = not sw.enabled
        icon.icon = make_icon(sw.enabled)

    def quit_app(icon, item):
        kl.stop()
        ml.stop()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Автоперемикання", toggle, checked=lambda i: sw.enabled),
        pystray.MenuItem("Вийти", quit_app),
    )
    pystray.Icon("UkrSwitcher", make_icon(True), "UkrSwitcher", menu).run()


if __name__ == "__main__":
    main()
