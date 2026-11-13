# Python 3.12 from Homebrew: brew install python@3.12
PYTHON = /opt/homebrew/bin/python3.12
VENV = .venv

venv:
	${PYTHON} -m venv ${VENV}
	${VENV}/bin/pip install -r requirements.txt

# Downloads the default model, so the first start doesn't look like a hang.
prepare:
	PYTHONDONTWRITEBYTECODE=1 ${VENV}/bin/python ../extension/daemon/faceguard_daemon.py --prepare

run:
	${VENV}/bin/python faceguard.py

test:
	${VENV}/bin/python -m unittest discover -s ../tests

clean:
	rm -rf build dist
