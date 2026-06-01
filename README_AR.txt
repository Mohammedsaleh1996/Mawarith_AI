# نسخة v23 UI/Telegram/Concept Fix

هذه النسخة تبني على v22 وتضيف إصلاحات واجهة وتشخيص تليجرام ودعم صيغة العامرية.

# Mawareth AI Production Acceptance Pack v1

هذه الحزمة تحوّل `Runtime Final v8` إلى أساس إنتاجي مضبوط بدون تعديل الكود الأصلي.

## المحتويات

- `baseline_v8_locked/mawarith_ai_runtime_final_v8.zip` نسخة v8 المقفلة.
- `baseline_v8_locked/BASELINE_SHA256.txt` بصمة النسخة المقفلة.
- `runtime_v8/` نسخة مفكوكة للتشغيل والاختبار.
- `acceptance_tests_public_v1.jsonl` اختبار قبول جماهيري من 300 حالة:
  - 100 مسألة حسابية.
  - 100 سؤال فقهي.
  - 50 اختبار لهجات.
  - 50 سؤال غامض/متقدم للتأكد من عدم التخمين.
- `acceptance_test_runner.py` مشغّل اختبار القبول.
- `mawarith_api_production.py` API إنتاجي مع logging.
- `telegram_bot_production.py` بوت تيليجرام مع logging.
- `v9-dev/` مساحة تطوير لاحقة بدون لمس v8.

## تشغيل اختبار القبول

```bat
run_acceptance_test.bat
```

أو:

```bat
python acceptance_test_runner.py --tests acceptance_tests_public_v1.jsonl --report acceptance_report_public_v1.json
```

## تشغيل API

```bat
pip install -r requirements_production.txt
run_api_production.bat
```

ثم أرسل POST إلى:

```text
http://127.0.0.1:8000/ask
```

مثال JSON:

```json
{"question":"واحد مات وساب مراته وبنته واخوه الشقيق","user_id":"test","channel":"api"}
```

## تشغيل Telegram

```bat
pip install -r requirements_production.txt
set TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN
run_telegram_bot.bat
```

## سياسة التطوير

- لا تعديل مباشر على v8.
- أي إضافة تتم داخل `v9-dev` أو نسخة جديدة.
- أي باب جديد يلزمه test gate مستقل.
- النظام يسأل توضيحًا عند الغموض بدل التخمين.

SHA256 للنسخة المقفلة:

```text
bbab290b6b58dab1f505a9fbb35471b7d0bc185f0079e50994859ba5aec8768d
```

## نتيجة التنفيذ الحالية

تم تشغيل اختبار القبول العام على الحزمة الحالية، والنتيجة:

```text
PASSED: 300/300
- calculation: 100/100
- fiqh: 100/100
- dialect_egyptian: 10/10
- dialect_saudi: 10/10
- dialect_shami: 10/10
- dialect_extra: 10/10
- dialect_fiqh_general: 10/10
- ambiguous_or_advanced: 50/50
All public acceptance tests passed.
```

## ملاحظة هندسية

تم الحفاظ على `baseline_v8_locked` كما هو، وأضيفت طبقة `mawarith_ai_runtime_v9.py` كـ NLU/Intent wrapper فوق v8 دون تعديل النسخة المقفلة. هذا يلتزم بمنع الترقيع داخل خط الأساس، ويجعل أي تحسين لاحق قابلًا للعزل والاختبار.

تحديث v3:
أضيف محرك مفاهيم فقهي ديناميكي يغطي مفاهيم المواريث ويستجيب للمتابعات مثل: مش فاهم، بسط، مثال بالأرقام، دون الاعتماد على ردود محفوظة لسؤال بعينه.

تحديث v6 - حساب القيم النقدية للتركة
-----------------------------------
إذا كتب المستخدم قيمة التركة والعملة، يقوم النظام الآن بإضافة قسم "القسمة النقدية" بعد النتيجة الشرعية.
مثال: "مات شخص وترك 3 بنات وأم وعم ومبلغ 100000 ريال".

للاختبار:
run_monetary_tests.bat

الطبقة لا تغيّر حكم المواريث، ولا تحفظ إجابات مسائل، بل تضرب الأنصبة المحسوبة في قيمة التركة المذكورة فقط.


## v25 UI Safe Repair
- إصلاح كسر تخطيط الداشبورد الناتج عن تثبيت القائمة الجانبية بطريقة خاطئة.
- إرجاع التخطيط إلى Flex آمن مع Sidebar sticky وScroll داخلي.
- منع الصفحة من التمدد عرضيًا أو تغطية المحتوى.
- تثبيت عرض الرسوم والجداول بدون التأثير على محرك المواريث.

---
تحديث v42:
تمت إضافة طبقة Full Scholarly Intelligence:
- v42_full_intelligence.py للمحادثة البشرية وفهم اللهجات والمتابعات.
- v42_munasakhat_engine.py للإيقاف الآمن في الوفاة المتتابعة غير المكتملة.
- v42_scholarly_corpus_builder.py لبناء فهرس علمي غير RAG من المراجع المحلية.
- run_v42_full_intelligence_tests.bat لاختبار الطبقة الجديدة.
- run_v42_build_corpus.bat لإعادة بناء فهرس المراجع.

هذه الطبقة لا تغيّر محرك الحساب الأساسي ولا تضيف ردودًا ثابتة لمسائل بعينها.
