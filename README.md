# SwitchUK

Автоперемикач розкладки EN ↔ UA (аналог Punto Switcher) для Windows і macOS (Intel та Apple Silicon).

## Можливості
- Автозаміна слова, набраного не в тій розкладці (`ghbdsn` → `привіт`, `руддщ` → `hello`) після пробілу, з перемиканням розкладки ОС.
- `Ctrl+Alt+Space` (Windows також `Pause`) — конвертувати останнє слово (повторне натискання повертає назад).
- `Ctrl+Alt+Enter` (Windows також `Shift+Pause`) — конвертувати виділений текст.
- Іконка в треї: вмикання/вимкнення автозаміни, вихід.
- Усе локально: нічого не логується й не надсилається в мережу.

## Запуск з коду
```bash
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python ukrswitcher.py
```

## Словники (рекомендовано, підвищують точність)
Покладіть у `~/.ukrswitcher/` (Windows: `C:\Users\<ви>\.ukrswitcher\`) файли `uk.txt` і `en.txt`
(одне слово в рядок) або hunspell-словники, перейменовані в `uk.dic` та `en.dic`
(наприклад `uk_UA.dic` і `en_US.dic` з LibreOffice dictionaries). Без словників працює евристика за біграмами.

## Збірка
- **Windows:** `pyinstaller --onefile --noconsole --name UkrSwitcher ukrswitcher.py`
- **macOS:** збирайте на відповідній архітектурі (Intel / ARM) —
  `pyinstaller --windowed --name UkrSwitcher ukrswitcher.py`, потім
  `plutil -insert LSUIElement -bool true dist/UkrSwitcher.app/Contents/Info.plist`
  (щоб не було іконки в Dock) і `codesign --force --deep --sign - dist/UkrSwitcher.app`.
- Або залийте проєкт на GitHub — workflow `.github/workflows/build.yml` збере всі три версії.

## macOS: дозволи
Системні налаштування → Конфіденційність і безпека → **Універсальний доступ** та **Моніторинг введення** → додайте UkrSwitcher.
Для непідписаного додатка при першому запуску: ПКМ → Відкрити.
У розкладках має бути додано **Українська (ПК)** (або «Українська») та **ABC/U.S.**

## Windows
Додайте розкладки Українська та English (US). Програми, запущені від адміністратора, не бачать UkrSwitcher,
якщо його запущено без прав адміністратора.

## Обмеження
- Автозаміна спрацьовує лише на пробілі (не на Enter/Tab).
- Розкладка Українська — стандартна ЙЦУКЕН.
- Слова з цифрами та спецсимволами не чіпаються.
