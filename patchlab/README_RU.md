# MiFitness PatchLab — изолированный этап анализа

Пакет добавляется автоматическим Termux-скриптом в отдельную ветку `mifitness-patchlab` репозитория `drsidius14/Mihealthreserch`. Основная ветка `v17.03-build` не изменяется.

Workflow собирает диагностический отчёт по Mi Fitness 3.59.1. На этом этапе это НЕ пропатченный APK: конкретная инструкция DEX должна быть подтверждена отчётом, прежде чем применять изменение.

## Входные APK

Оригинальный Mi Fitness и Xiaomi Health Research V17.03 нужно поместить в `patchlab/input/` в приватной ветке, но APK исключены из Git через `.gitignore`. Не добавляйте их в публичный репозиторий. Workflow ожидает файлы:
- `patchlab/input/com.mi.health_3.59.1.apk`
- `patchlab/input/XiaomiHealthResearch_1.4.6_RU_V17_03.apk`

## Запуск

GitHub → Actions → `PatchLab: inspect Mi Fitness integration` → Run workflow. Скачайте artifact `MiFitness-PatchLab-Forensic-Report`.
