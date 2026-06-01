@echo off
chcp 65001 >nul
python acceptance_test_runner.py --tests monetary_hardening_tests_v2.jsonl --report monetary_hardening_report_v2.json
pause
