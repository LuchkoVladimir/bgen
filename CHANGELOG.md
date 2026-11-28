# Changelog

Все заметные изменения в этом проекте документируются в этом файле.

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
проект придерживается [Semantic Versioning](https://semver.org/lang/ru/).

## Используемые секции

### Fixed
### Removed
### Deprecated
### Security
### Changed
### Added

## [Unreleased]

### Changed
- Рефакторинг.
    - Более чёткая граница в архитектуре между доверенной частью и периметра с
        валидацией пользовательских данных.
    - Перестройка файловой структуры библиотеки.

### Added
- CONTRIBUTING.md
- CHANGELOG.md


## [2.6.2] - 27.11.2026

### Fixed
- Дата в document-info обязательна. Если пользователь не выставил в config.yaml, будет выставлена текущая.


## [2.6.1] - 26.11.2026

### Fixed
- (check) замена некорректного правила с дефисами на знаки в конце предложения

## [2.6.0] - 26.11.2026

### Added
- проверка исходников книги по задаваемым паттернам (rules.txt)
    - `bgen check <path> --only 1,2 --list`


## [2.5.0] - 26.11.2026

### Changed
- единообразно оформлен вывод конфигурации проекта книги


## [2.4.0] - 25.11.2026

### Changed
- расширен вывод статистики - общая и по каждому md-файлу отдельно


## [2.3.0] - 24.11.2026

### Added
- стили inline-выделения текста для TXT
    - config.yaml: txt.inline-mode: auto / none / md / tags / gutenberg

## [2.2.0] - 24.11.2026

### Added
- отображение версии программы: `bgen --version / -v`


## [2.1.0] - 23.11.2026

### Added
- вывод конфигурации проекта книги: `bgen cfg <path>`


## [2.0.0] - 23.11.2026

### Removed
- BREAKING CHANGE: config.yaml - настройка `annotation-lang`

### Changed
- pandoc lua-filter переписан на python с использованием panflute

### Added
- поддержка тегов через fenced-div tags для fb2 <annotation>, <epigraph>, <text-author>, <subtitle>


## [1.0.0] - 22.11.2026

### Changed
- Переход на semver: https://semver.org/lang/ru/
- Поддержка соглашения о коммитах https://www.conventionalcommits.org/ru/v1.0.0/


## [1.0] - 19.11.2026

### Added
- Первый публичный релиз.
- Лицензия GPLv3.
- Базовая поддержка конвертации markdown в fb2/epub/docx.
- Постобработка результирующего fb2-файла и валидация его по схеме.
- Документация.

