@echo off
chcp 65001 >nul
python v45_test_factory.py
python v45_full_test_runner.py
pause
