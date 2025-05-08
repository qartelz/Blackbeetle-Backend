
PYTHON = python3
VENV = venv
MANAGE = $(PYTHON) manage.py

venv:
	$(PYTHON) -m venv $(VENV)

activate:
	. $(VENV)/bin/activate

install:
	pip install -r requirements/development.txt

update:
	pip install --upgrade -r requirements/development.txt

migrations:
	$(MANAGE) makemigrations

migrate:
	$(MANAGE) migrate

runserver:
	$(MANAGE) runserver

shell:
	$(MANAGE) shell

test:
	$(MANAGE) test

lint:
	flake8 .
	black --check .

format:
	black .

collectstatic:
	$(MANAGE) collectstatic --noinput

clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete

help:
	@echo "Available commands: venv, install, migrations, migrate, runserver, shell, test, lint, format, collectstatic, clean"

.PHONY: venv activate install update migrations migrate runserver shell test lint format collectstatic clean help