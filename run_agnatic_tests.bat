@echo off
chcp 65001 >nul
python acceptance_test_runner.py --tests agnatic_residuary_tests_v1.jsonl --report agnatic_residuary_report_v1.json
pause
