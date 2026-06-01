@echo off
chcp 65001 >nul
python concept_test_runner.py --tests concept_tests_v1.jsonl --report concept_report_v1.json
pause
