تشخيص استقبال رسائل WaPilot / WhatsApp
=====================================

1) شغّل الداشبورد:
   run_dashboard.bat

2) تأكد أن السيرفر المحلي يعمل:
   افتح http://127.0.0.1:8088/webhook/wapilot
   يجب أن يظهر JSON فيه ok=true.

3) شغّل ngrok على بورت الداشبورد:
   ngrok http 8088

4) افتح رابط الويبهوك العام:
   https://favorable-erased-hatbox.ngrok-free.dev/webhook/wapilot
   يجب أن يرجع JSON فيه ok=true.
   لو الرابط لا يفتح، إذن WaPilot لن يستطيع إرسال الرسائل إلى مشروعك.

5) داخل WaPilot ضع رابط الويبهوك بالضبط:
   https://favorable-erased-hatbox.ngrok-free.dev/webhook/wapilot

6) من الداشبورد شغّل WhatsApp Service.
   لو الخدمة غير مفعلة، الويبهوك سيستقبل لكنه لن يرد.

7) اختبر محليًا بدون WaPilot:
   test_wapilot_local_webhook.bat

8) اختبر رابط ngrok العام:
   test_wapilot_public_webhook.bat

9) افتح صفحة التشخيص:
   http://127.0.0.1:8088/api/wapilot/diagnostics

10) آخر Payload وصل من WaPilot يتم حفظه في:
   logs/wapilot_last_payload.json

المعنى العملي:
- إذا لم تظهر أي POST /webhook/wapilot في نافذة السيرفر بعد إرسال رسالة واتساب، فالمشكلة خارج المشروع: WaPilot لم يرسل للويبهوك أو رابط ngrok غير مضبوط.
- إذا ظهرت POST /webhook/wapilot لكن لا يوجد رد، فافحص Settings: token, instance_id, WhatsApp Service enabled, last_error.
