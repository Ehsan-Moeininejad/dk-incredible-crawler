# کراولر شگفت‌انگیزهای دیجی‌کالا — حالت Overwrite

جمع‌آوری خودکار لیست کامل محصولات شگفت‌انگیز دیجی‌کالا در سه نوبت روزانه
(00:00، 08:00، 12:00 به وقت تهران). هر ران محتوای شیت را کامل جایگزین می‌کند؛
تاریخچه نگه داشته نمی‌شود و شیت همیشه لیست فعال لحظه‌ی آخرین ران است.

---

## 1. منبع داده

صفحه‌ی `digikala.com/incredible-offers/` یک اپلیکیشن React است؛ محتوای آن در HTML اولیه وجود
ندارد و مرورگر آن را از یک API داخلی می‌گیرد. کراولر مستقیماً با همان API کار می‌کند:

```
GET https://api.digikala.com/v1/incredible-offers/?page=N
```

ساختار پاسخ (تأیید شده روی داده‌ی واقعی در تاریخ 2026-09-21):

| مسیر | توضیح |
|---|---|
| `data.incredible_products_list.products[]` | لیست اصلی، 20 محصول در هر صفحه |
| `data.incredible_products_list.pager` | `current_page`, `total_pages`, `total_items` |
| `products[].id` | همان DKP |
| `products[].title_fa` | عنوان فارسی |
| `products[].data_layer.item_category2/3/4` | دسته‌بندی سه‌سطحی |
| `products[].data_layer.brand` | برند |
| `products[].default_variant.price.selling_price` | قیمت فروش (ریال) |
| `products[].default_variant.price.rrp_price` | قیمت قبل از تخفیف (ریال) |
| `products[].default_variant.price.discount_percent` | درصد تخفیف |
| `products[].default_variant.price.time` | زمان پایان آفر |

در زمان نگارش: `total_items = 1245` در `total_pages = 63` صفحه.
قیمت‌ها در API به **ریال** است و کراولر آن‌ها را به **تومان** تبدیل می‌کند.

سایر بلاک‌های موجود در پاسخ — `running_out_incredible_products`,
`lightening_deal_products`, `deal_of_the_day_products`, `fresh_incredible_products`,
`teasing_incredible_products` — زیرمجموعه‌های نمایشی همان لیست اصلی هستند و
برای جلوگیری از رکورد تکراری استفاده نمی‌شوند.

---

## 2. ساختار خروجی

هر ران دو جا می‌نویسد و هر دو کامل بازنویسی می‌شوند:

| مقصد | رفتار |
|---|---|
| تب اول اسپردشیت (gid=0) | `clear()` سپس نوشتن کامل لیست فعلی |
| `data/latest.csv` | بازنویسی با همان داده، به‌عنوان نسخه‌ی پشتیبان محلی |

ستون‌ها:

```
updated_at | rank | dkp | title_fa | brand |
category_l1 | category_l2 | category_l3 |
selling_price_toman | rrp_price_toman | discount_percent | discount_amount_toman |
status | seller | rating_rate | rating_count | deal_end_time | is_lightening_deal | url
```

`updated_at` در تمام ردیف‌ها یکسان است و زمان آخرین ران را نشان می‌دهد —
با نگاه به سلول `A2` مشخص می‌شود داده چقدر تازه است.
`rank` جایگاه محصول در لیست شگفت‌انگیز است؛ `1` یعنی ابتدای لیست.

برای نوشتن روی تبی غیر از تب اول، مقدار `TARGET_TAB` در بالای `crawler.py`
از `None` به نام آن تب تغییر کند.

---

## 3. محافظ بازنویسی

در حالت overwrite یک ران ناقص می‌تواند داده‌ی سالم را با داده‌ی نصفه جایگزین کند.
سه لایه محافظت وجود دارد:

1. شیت فقط زمانی `clear` می‌شود که **کل** کراول تمام شده و نتیجه در حافظه باشد.
2. اگر هیچ محصولی جمع نشود، شیت اصلاً لمس نمی‌شود (exit code = 1).
3. اگر تعداد رکوردهای جمع‌شده کمتر از `70%` مقدار اعلام‌شده در `pager.total_items` باشد،
   شیت دست‌نخورده می‌ماند و نتیجه‌ی ناقص فقط در CSV محلی ذخیره می‌شود (exit code = 4).

آستانه‌ی `70%` با تغییر `MIN_COMPLETENESS` قابل تنظیم است.

---

## 4. نصب

### 4.1. فایل‌ها و وابستگی‌ها

```bash
# مسیر فعلی پروژه:
#   ~/Documents/digikalAmazingcrowler/digikala-incredible-crawler

cd ~/Documents/digikalAmazingcrowler/digikala-incredible-crawler
pip3 install -r requirements.txt
chmod +x run.sh
```

### 4.2. دسترسی Google Sheets (Service Account)

روش Service Account انتخاب شده چون بدون مرورگر و بدون تمدید دستی توکن کار می‌کند —
یعنی برای اجرای زمان‌بندی‌شده مناسب است.

1. ورود به <https://console.cloud.google.com> و ساخت یک پروژه (مثلاً `dk-incredible-crawler`).
2. در **APIs & Services → Library**: فعال‌سازی **Google Sheets API** و **Google Drive API**.
3. در **APIs & Services → Credentials → Create Credentials → Service account**:
   نام دلخواه، سپس **Done**.
4. روی سرویس‌اکانت ساخته‌شده → تب **Keys** → **Add Key → Create new key → JSON**.
5. فایل دانلودشده را با نام `credentials.json` کنار `crawler.py` قرار دهید.
6. مقدار `client_email` داخل همان فایل را کپی کنید و
   [اسپردشیت](https://docs.google.com/spreadsheets/d/1V62qJ4IYNKa-gSdrzwjNF5XsSYMUb6L0NpoyhQ1bLU8/edit)
   را با دسترسی **Editor** با آن ایمیل share کنید.

> `credentials.json` کلید خصوصی است — نباید در گیت یا جای اشتراکی قرار بگیرد.

### 4.3. تست اولیه

```bash
cd ~/Documents/digikalAmazingcrowler/digikala-incredible-crawler
python3 crawler.py
```

خروجی مورد انتظار: حدود 63 خط لاگ صفحه‌به‌صفحه، سپس
`CSV overwritten: latest.csv` و `sheet '...' replaced with NNNN rows`.
زمان تقریبی: 60 تا 90 ثانیه.

---

## 5. زمان‌بندی روی macOS

روی لپ‌تاپ، `launchd` به `cron` ترجیح دارد: اگر سیستم در ساعت 00:00 خواب باشد،
`cron` آن ران را برای همیشه از دست می‌دهد ولی `launchd` بلافاصله پس از بیدار شدن
اجرایش می‌کند — که دقیقاً رفتار مورد نیاز برای ران نیمه‌شب است.

```bash
# مسیرهای داخل plist از قبل روی محل واقعی پروژه تنظیم شده‌اند
cp com.ehsan.digikala-incredible.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.ehsan.digikala-incredible.plist

launchctl list | grep digikala                      # بررسی وضعیت
launchctl start com.ehsan.digikala-incredible       # اجرای دستی برای تست
launchctl unload ~/Library/LaunchAgents/com.ehsan.digikala-incredible.plist  # حذف
```

در **System Settings → Battery → Options**، گزینه‌ی
«Wake for network access» فعال باشد تا ران نیمه‌شب مطمئن‌تر اجرا شود.

لاگ‌ها: `logs/crawler.log` (لاگ برنامه) و `logs/launchd.err` (خطاهای سطح سیستم).

---

## 6. رفتار در خطا

| وضعیت | رفتار | Exit code |
|---|---|---|
| ران موفق | شیت و CSV بازنویسی شدند | `0` |
| خطای شبکه روی یک صفحه | چهار بار retry با backoff نمایی (2، 4، 8، 16 ثانیه) | — |
| پاسخ 429 | مکث 5 تا 20 ثانیه‌ای و تلاش مجدد | — |
| هیچ محصولی جمع نشد | شیت دست‌نخورده | `1` |
| نبود `credentials.json` | CSV نوشته شد، شیت آپدیت نشد | `2` |
| خطای نوشتن در شیت | CSV سالم است | `3` |
| کراول ناقص (زیر 70%) | شیت دست‌نخورده، CSV ناقص برای بررسی | `4` |

فاصله‌ی 0.7 ثانیه بین صفحات و User-Agent واقعی، بار وارد بر API را در حد یک
کاربر عادی نگه می‌دارد: حدود 65 درخواست در هر ران، 195 درخواست در روز.

---

## 7. مسیر مهاجرت به Airflow

کد طوری نوشته شده که انتقال آن نیازی به بازنویسی نداشته باشد:
`crawl()` داده را برمی‌گرداند، `push_to_sheet()` مصرف‌کننده است.

```python
# dags/digikala_incredible.py
from airflow.decorators import dag, task
from datetime import datetime
import pendulum

@dag(
    schedule="0 0,8,12 * * *",
    start_date=datetime(2026, 9, 21),
    timezone=pendulum.timezone("Asia/Tehran"),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 2},
)
def digikala_incredible():
    @task
    def extract():
        from crawler import crawl
        from datetime import datetime as dt
        from zoneinfo import ZoneInfo
        ts = dt.now(ZoneInfo("Asia/Tehran")).strftime("%Y-%m-%d %H:%M:%S")
        rows, expected = crawl(ts)
        if expected and len(rows) < expected * 0.7:
            raise ValueError(f"partial crawl: {len(rows)}/{expected}")
        return rows

    @task
    def load(rows):
        from crawler import push_to_sheet
        push_to_sheet(rows)

    load(extract())

digikala_incredible()
```

در محیط Airflow، `credentials.json` به‌جای فایل کنار کد از طریق
Airflow Connection یا Secret Backend تأمین می‌شود.

> نکته: اگر بعداً تاریخچه لازم شد، ایرفلو جای درست آن است — نه شیت.
> در آن حالت هر ران در یک جدول partition شده بر اساس تاریخ نوشته می‌شود
> و شیت همچنان فقط ویترین وضعیت فعلی می‌ماند.

---

## 8. اجرای ابری رایگان با GitHub Actions

فایل‌های ورک‌فلو در `.github/workflows/` آماده‌اند. این مسیر کراولر را از لپ‌تاپ
مستقل می‌کند و هزینه‌ای ندارد: ریپوی public نامحدود رایگان است و پلن رایگان برای
ریپوی private ماهانه 2,000 دقیقه می‌دهد — مصرف این کراولر حدود 180 دقیقه در ماه است.

| فایل | نقش |
|---|---|
| `.github/workflows/reachability-test.yml` | تست دستی: آیا ماشین‌های GitHub به API دیجی‌کالا می‌رسند؟ |
| `.github/workflows/crawler.yml` | زمان‌بندی اصلی، روزی سه بار |

### راه‌اندازی

```bash
cd ~/Documents/digikalAmazingcrowler/digikala-incredible-crawler
git init && git add .
git status --short          # نباید credentials.json را ببینید
git commit -m "digikala incredible offers crawler"
gh repo create dk-incredible-crawler --private --source=. --push
```

سپس در ریپو:

1. تب **Actions** → ورک‌فلوی «00 - Can GitHub reach the Digikala API?» → **Run workflow**.
   اگر رد شد، این مسیر بسته است و باید روی launchd بمانید.
2. **Settings → Secrets and variables → Actions → New repository secret**
   با نام دقیق `GOOGLE_CREDENTIALS` و مقدار کل محتوای `credentials.json`.
3. تب Actions → ورک‌فلوی «Digikala Incredible Offers» → **Run workflow** برای اولین اجرای واقعی.

### زمان‌بندی

GitHub فقط UTC می‌فهمد. الگوی `30 20,4,8 * * *` معادل 00:00، 08:00 و 12:00 تهران است.
ایران از 2022 ساعت تابستانی ندارد، پس این اختلاف سه‌ونیم ساعته تمام سال ثابت می‌ماند.

### دو نکته

- ران‌های زمان‌بندی‌شده چند دقیقه تأخیر دارند. برای این کراولر بی‌اهمیت است.
- ورک‌فلوی زمان‌بندی‌شده بعد از 60 روز بی‌فعالیتی در ریپو غیرفعال می‌شود؛ GitHub
  ایمیل اطلاع می‌دهد و با یک کلیک برمی‌گردد.

### بعد از فعال شدن

زمان‌بندی لوکال دیگر لازم نیست. برای خاموش کردنش:

```bash
launchctl unload ~/Library/LaunchAgents/com.ehsan.digikala-incredible.plist
```

اگر نگه دارید، شیت روزی شش بار به‌جای سه بار بازنویسی می‌شود — ضرری ندارد ولی لاگ‌ها شلوغ می‌شوند.
