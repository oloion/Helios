# Helios

Лаборатория готовности к **Windows 11**. Духовный наследник заброшенного [Win11Checker 1.1](https://github.com/oloion/Win11Checker1.1) — только теперь это не три проверки в `tkinter`, а настоящий диагностический стенд.

Helios не обходит TPM и не ломает установщик. Он говорит правду.

## Что умеет

- TPM 2.0, Secure Boot, UEFI / Legacy
- CPU по каталогу поколений Microsoft (Intel 8+, Ryzen 3000 Zen 2 и новее)
- RAM, ёмкость диска, GPU / разрешение / DirectX
- Defender, брандмауэр, BitLocker, VBS / isolation
- Живые датчики CPU / RAM / диск
- Оценка 0–100, экспорт JSON + Markdown
- Окно как продукт, не как лабораторная поделка 2022 года

`Get-WindowsUpdateLog` больше нет. Он вешал старый чекер.

## Запуск из исходников

Нужны Windows 10/11, Python 3.12+, WebView2 (в Windows 11 уже есть).

```bat
python -m pip install -r requirements.txt
python -m helios
```

или `run.bat`.

## Сборка .exe

```bat
python -m pip install -r requirements.txt
python -m PyInstaller Helios.spec --noconfirm
```

Готовый файл: `dist\Helios.exe`.

## Почему Helios, а не Win11Checker

Старое имя описывало утилиту. Новое — сцену: тёмная лаборатория, солнце в углу, золотая дуга оценки, карточки с вердиктом Microsoft. Тот же вопрос («пустит ли меня Windows 11?»), другой уровень ответа.
