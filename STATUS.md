# STATUS — X Comment Counter

**Created:** 2026-06-22

## v6 (2026-06-24) — 🟢 LIVE on Vercel
**Public URL: https://x-comment-counter.vercel.app** (no login, public).
- Vercel project `x-comment-counter` (team annas-projects-4b7957a4).
- **Upstash for Redis** подключён (resource `upstash-kv-pink-xylophone`, Free) →
  env `KV_REST_API_URL/TOKEN` авто-инжектятся. `TWITTERAPI_KEY` в env (Production).
- **Архитектура под новый Vercel Python-билдер (uv, single entrypoint):**
  - вся логика в `api/_core.py`; `pyproject.toml` → `[tool.vercel] entrypoint="api._core:Handler"`.
    `_core.Handler` роутит `/`, `/api/lookup`, `/img` и отдаёт index.html.
  - корневой `app.py` — тонкий шим для локалки (`.vercelignore` его прячет).
  - `pyproject.toml` с `[project]` (deps=[], stdlib) + `[tool.uv] package=false`. requirements.txt удалён.
- **Deployment Protection снят** через API (`PATCH ssoProtection:null`) — иначе редирект на SSO.
- Деплой: `npx vercel deploy --prod --yes`. Залогинен annzrva108-9221.
- **Проверено на проде**: /, lookup (levelsio streak 9 / burninganna), кэш-хит (cached:true),
  img-прокси (200). ✅
- Прод-кэш стартовал с нуля (KV пустой) — у burninganna на проде 14-дн история, не 79.
  Локальные 79 дней лежат в `data/burninganna.json` (на прод не заливались).
- **Идеи дальше**: кастомный домен (streak.* в Vercel→Domains); залить полную историю
  burninganna в KV; авто-рефреш/напоминание.

## v5 (2026-06-24) — VERCEL-READY (serverless + Redis)
Подготовлено к деплою на Vercel. Гайд: **DEPLOY.md**.
- **Хранилище KV-aware** (`app.py`): Redis (Upstash/Vercel KV) в проде, локальные
  файлы в деве — переключается по env-переменным. Redis-клиент на чистом urllib
  (без зависимостей): `kv_cmd()` через Upstash REST. `load_data/save_data` →
  `cc:data:<handle>`; дневной кап → `INCR cc:usage:<date>` + EXPIRE 2д.
- **Serverless-функции**: `api/lookup.py` (/api/lookup), `api/img.py` (/img→/api/img).
  Импортируют общий `app.py`. `vercel.json` бандлит app.py + rewrite для /img.
- **config.json теперь опционален**: DEFAULT_CONFIG = боевые значения (goal 20),
  load_config не падает на read-only FS Vercel.
- `requirements.txt` пустой (только stdlib), `.vercelignore` прячет .env/data/usage.
- **Протестировано локально**: file-fallback (owner lookup ок), KV-путь замокан
  (round-trip data + кап через INCR работают). ✅
- **Осталось (нужен браузер/аккаунт Anna)**: `npx vercel login` → link →
  подключить Upstash Redis (free) → env TWITTERAPI_KEY → `vercel deploy --prod`.
  Дальше CLI-шаги могу прогнать сам, как залогинишься.

## v4 (2026-06-24) — MULTI-HANDLE ✅ working
Из личного трекера → продукт: любой вводит @хендл (свой или чужой) и видит
комменты/посты/стрик/график этого аккаунта.
- **Поле ввода** в шапке (`#search`): принимает `@name`, `name` или ссылку x.com/...
  Хендл читается из URL `?h=name` (расшаренные ссылки работают) + last-used в localStorage.
- **Данные per-handle**: `data/<handle>.json` (вместо одного `data.json`).
  Старая история перенесена → `data/burninganna.json` (79 дней).
- **Оркестратор `lookup()`** с кэшем: запрашивает API только если кэш протух/пуст.
  Эндпоинт `/api/lookup?handle=H&force=0/1` (заменил /api/state + /api/refresh).
- **Контроль расходов twitterapi.io** (для публичного доступа):
  - `cache_ttl_minutes` 360 — повтор/расшаренные ссылки = бесплатно
  - `new_handle_backfill_days` 14 — короткая история для нового ника (совпадает с 14-дн хитмапом)
  - `daily_call_cap` 1500 — жёсткий потолок вызовов/день, учёт в `usage.json`; при превышении
    отдаёт кэш (note=budget), а не жжёт баланс
  - `rate_per_ip_per_min` 8 — лимит новых лукапов на IP
  - валидация ника: несуществующий → чистая ошибка `invalid_handle`
- **Стоимость на новый ник**: ~зависит от активности (levelsio 14д ≈ 40 вызовов,
  обычный юзер сильно меньше). Кэш-хиты бесплатны.
- **Tested (2026-06-24):** levelsio first-fetch (streak 12, 31 день), кэш-хит,
  невалидный ник, owner — всё ✅. Сервер на :8765.
- **TODO:** деплой на Render/Railway → публичный URL (домен varg.ai или отдельный).

---

## What it is
Duolingo-style дашборд для дневной активности на X (@burninganna): считает
комментарии (реплаи) и посты, ведёт стрик, празднует выполнение цели конфетти.

**Цель дня:** 50 комментариев + 1 пост.

## State: ✅ working
- Backend `app.py` (stdlib, без зависимостей) — локальный сервер + подсчёт через
  twitterapi.io (`from:burninganna filter:replies` / `-filter:replies`) + стрик.
  Тянет профиль (`/twitter/user/info`): аватар, обложка, имя, галочка, био,
  followers/following — кэшируется в `data.json` при каждом refresh.
- Dashboard `index.html` — дизайн в стиле X-профиля (по референсу Comment Counter v6):
  тёмная карточка, sticky-хедер, реальные обложка+аватар, био, прогресс-бары,
  столбчатый график за 14 дней, конфетти при цели.
- Ключ twitterapi.io переиспользован из `../X growth/.env`.

## Tested (2026-06-22)
- `python3 app.py --refresh` → 16 комментов / 3 поста за сегодня. ✅
- Сервер + `/api/state`, `/api/refresh`, `/` отдают корректно. ✅

## v3 (2026-06-22) — kawaii редизайн (по референсу Comment Counter v4)
- **Новая эстетика Y2K/kawaii:** пастельный градиент (#7be3ff→#a8c0ff→#e6b3ff),
  шрифт Fredoka, голо-CD (крутится), звёздочки, стикеры 🦋😎🌈, радужная полоса.
- **Приоритет:** 1) Comments (hero, цифра 120px) 2) Posts (бабл) 3) Streak (мелкий бабл).
- **Цель 20** комментов (была 50/15), stretch 30 оставлен.
- **GitHub-сетку убрали** → простой 14-дневный хитмап (зелёная интенсивность, сегодня розовый).
- **Анимации на тап:** 🦋 порхает + 💿 крутится-взрыв, оба сыпят конфетти/эмодзи.
- **Шеринг-карточка** переделана под ту же эстетику (1200×675 PNG).

## v2 (2026-06-22) — graph + share
- **Лидерборд убран** (по решению 2026-06-22): был псевдо-соц — друзья в нём не
  «играют», просто скрейп публичных цифр. Настоящая соц-механика = шеринг-карточка
  (наружу, в ленту → вирусность). Код/эндпоинт/конфиг/кэш удалены.
- **GitHub-граф** контрибуций: квартал/год, уровни 0 пусто · 1 активность ·
  2 цель · 3 перевыполнение. Backfill истории: `python3 app.py --backfill 90`
  или кнопка «Sync history». Сейчас 79 дней истории.
- **Шеринг-карточка** (1200×628 PNG): аватар, стрик, сегодня, мини-граф, CTA.
  Кнопки Download / Copy image / Post on X. Картинки идут через `/img` прокси
  (pbs.twimg.com) — чтобы canvas не «портился» и PNG экспортировался.

## Цель: двухуровневая (решено 2026-06-22)
Анализ 79 дней: медиана 2 комм/день, среднее 3.8, макс 32 — цель 50 была анрил.
Перешли на Duolingo-механику:
- **floor 15** (`comments_goal`) + 1 пост → держит стрик, день = зелёный (level 2)
- **stretch 30** (`comments_stretch`) → самый яркий квадрат (level 3)
- На баре комментов золотой маркер floor; заливка тянется до stretch.
Результат: сегодня цель закрыта, streak 1, 3 зачётных дня за квартал, граф ожил.
Лидерборд (12 чел): nestymee/levelsio ~33-35💬, Anna 23💬.

## Run
`cd ~/developer/"X comment counter" && python3 app.py` (или двойной клик start.command)

## TODO / ideas
- Авто-рефреш + вечернее напоминание, если цель не закрыта.
- Виджет в menu bar.
