@echo off
chcp 65001 >nul
python acceptance_test_runner.py --tests monetary_distribution_tests_v1.jsonl --report monetary_distribution_report_v1.json
pause
