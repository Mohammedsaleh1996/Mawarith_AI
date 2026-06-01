تشغيل ngrok تلقائيًا مع الداشبورد
===================================

في هذه النسخة، عند تشغيل run_dashboard.bat أو run_dashboard_auto_ngrok.bat يقوم الداشبورد تلقائيًا بـ:

1) تشغيل Dashboard/API على البورت 8088.
2) البحث عن ngrok.exe في PATH أو C:\ngrok\ngrok.exe أو المسار المحفوظ في Settings/Registry.
3) تشغيل ngrok على http://127.0.0.1:8088.
4) قراءة رابط HTTPS من ngrok المحلي 127.0.0.1:4040.
5) حفظ رابط الداشبورد العام في الإعدادات.
6) تحديث WAPILOT_PUBLIC_WEBHOOK_URL تلقائيًا إلى:
   https://.../webhook/wapilot

شروط التشغيل:
- لازم يكون ngrok.exe موجودًا. لا يتم تضمينه داخل الحزمة.
- ضع ngrok.exe في C:\ngrok أو أضفه إلى PATH أو اكتب مساره من Settings.
- لو عندك دومين ngrok ثابت مثل favorable-erased-hatbox.ngrok-free.dev، ضعه في خانة "دومين ngrok اختياري".

اختبار سريع:
- افتح الداشبورد: http://127.0.0.1:8088
- من Settings اضغط: تشغيل ngrok الآن
- راجع صفحة الأحداث للتأكد من ظهور حدث ngrok_started.
