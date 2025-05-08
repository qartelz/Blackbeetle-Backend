@echo off

set VENV_PATH=venv\Scripts\activate

@REM :: Check if the virtual environment exists
@REM if not exist %VENV_PATH% (
@REM     echo Virtual environment "env" not found! Ensure it is created using 'python -m venv env'.
@REM     exit /b 1
@REM )

@REM :: Activate the virtual environment
@REM call %VENV_PATH%
@REM echo Virtual environment "env" activated.

:: Handle commands
if "%1" == "install" (
    pip install -r requirements.txt
) else if "%1" == "run" (
    python manage.py runserver
) else if "%1" == "migrate" (
    python manage.py makemigrations
    python manage.py migrate
) else if "%1" == "createsuperuser" (
    python manage.py createsuperuser
) else if "%1" == "test" (
    python manage.py test
) else if "%1" == "clean" (
    for /r %%i in (*.pyc) do del "%%i"
    for /d /r %%i in (__pycache__) do rmdir /s /q "%%i"
) else if "%1" == "startapp" (
    if "%2" == "" (
        echo "You need to provide an app name. Usage: startapp <app_name>"
    ) else (
        python manage.py startapp %2
    )
) else (
    echo "Available commands:"
    echo "  install          - Install dependencies"
    echo "  run              - Run the Django development server"
    echo "  migrate          - Apply database migrations"
    echo "  createsuperuser  - Create a superuser for the admin site"
    echo "  test             - Run tests for the Django app"
    echo "  clean            - Clean temporary files"
    echo "  startapp <app_name> - Create a new Django app"
)
