# HomePod Agent — Makefile
#
# Targets:
#   make install  - install Python deps (uv), node deps (npm), create runtime dirs
#   make pair     - run the HomeKit pairing helper (scan code with iPhone)
#   make run      - boot all services in foreground
#   make dev      - boot all services with hot-reload
#   make test     - run pytest
#   make lint     - ruff + mypy + eslint
#   make smoke    - end-to-end smoke test (requires paired home)
#   make unpair   - remove the agent from the home
#   make clean    - remove build artifacts and caches
#   make logs     - tail all service logs

# ---- config ---------------------------------------------------------------

PYTHON    ?= python3
PIP       ?= uv
NODE      ?= node
NPM       ?= npm
AGENT_DIR := agent
DASH_DIR  := dashboard
IPAD_DIR  := ipad-listen

STATE_DIR ?= $(HOME)/.homepod-agent
RUN_DIR   := .run
LOG_DIR   := $(STATE_DIR)/logs
PID_DIR   := $(STATE_DIR)/pid

AGENT_PORT      ?= 8000
HOMEKIT_PORT    ?= 51826
VOICE_OUT_PORT  ?= 8765
CAMERAS_PORT    ?= 8001
DASHBOARD_PORT  ?= 3000

# ---- helpers ------------------------------------------------------------- ----

.PHONY: help install pair run dev test lint smoke unpair clean logs \
        agent-install homekit-install voice-install cameras-install \
        dashboard-install ipad-install state-dirs

help:
	@echo "homepod-agent targets:"
	@echo "  install  - install all dependencies"
	@echo "  pair     - run the HomeKit pairing helper"
	@echo "  run      - boot all services in foreground"
	@echo "  dev      - boot all services with hot-reload"
	@echo "  test     - run pytest"
	@echo "  lint     - ruff + mypy + eslint"
	@echo "  smoke    - end-to-end smoke test"
	@echo "  unpair   - remove the agent from the home"
	@echo "  clean    - remove build artifacts"
	@echo "  logs     - tail all service logs"

state-dirs:
	@mkdir -p $(STATE_DIR) $(LOG_DIR) $(PID_DIR)

# ---- install ---------------------------------------------------------------

install: state-dirs agent-install homekit-install voice-install cameras-install dashboard-install ipad-install
	@echo ""
	@echo "✅ All components installed."
	@echo ""
	@echo "Next steps:"
	@echo "  1. make pair     # scan the code with your iPhone Home app"
	@echo "  2. make run      # boot all services"

agent-install:
	@echo "Installing agent deps..."
	cd $(AGENT_DIR) && $(PIP) sync

homekit-install: agent-install

voice-install: agent-install

cameras-install: agent-install

dashboard-install:
	@echo "Installing dashboard deps..."
	cd $(DASH_DIR) && $(NPM) install

ipad-install:
	@echo "Building iPad client (requires Xcode toolchain on macOS)..."
	@if command -v xcrun >/dev/null 2>&1; then \
		cd $(IPAD_DIR) && xcrun swift build -c release; \
	else \
		echo "xcrun not found — skipping iPad build (you can build it manually later)"; \
	fi

# ---- pair / unpair ---------------------------------------------------------

pair: state-dirs
	@echo "Starting HomeKit pairing helper..."
	@echo ""
	@echo "You will see a setup code below. Scan it with the iPhone Home app:"
	@echo "  Home → + → Add Accessory → scan QR / enter code"
	@echo ""
	cd $(AGENT_DIR) && $(PIP) run python -m homekit.pair \
		--port $(HOMEKIT_PORT) \
		--state-dir $(STATE_DIR)

unpair:
	@echo "Removing agent from paired home..."
	cd $(AGENT_DIR) && $(PIP) run python -m homekit.unpair \
		--state-dir $(STATE_DIR)

# ---- run --------------------------------------------------------------------

run: state-dirs
	@echo "Booting homepod-agent..."
	@echo "  Agent:       http://localhost:$(AGENT_PORT)"
	@echo "  HomeKit:     HAP socket on :$(HOMEKIT_PORT)"
	@echo "  Cameras:     http://localhost:$(CAMERAS_PORT)"
	@echo "  Voice:       ws://localhost:$(VOICE_OUT_PORT)"
	@echo "  Dashboard:   http://localhost:$(DASHBOARD_PORT)"
	@echo ""
	@echo "Logs: $(LOG_DIR)"
	@echo "Press Ctrl-C to stop all services."
	@echo ""
	mkdir -p $(LOG_DIR)
	cd $(AGENT_DIR) && $(PIP) run python -m llm.main > $(LOG_DIR)/llm.log 2>&1 & echo $$! > $(PID_DIR)/llm.pid
	cd $(AGENT_DIR) && $(PIP) run python -m homekit.daemon > $(LOG_DIR)/homekit.log 2>&1 & echo $$! > $(PID_DIR)/homekit.pid
	cd $(AGENT_DIR) && $(PIP) run python -m voice.main > $(LOG_DIR)/voice.log 2>&1 & echo $$! > $(PID_DIR)/voice.pid
	cd $(AGENT_DIR) && $(PIP) run python -m cameras.proxy > $(LOG_DIR)/cameras.log 2>&1 & echo $$! > $(PID_DIR)/cameras.pid
	cd $(DASH_DIR) && $(NPM) run dev > $(LOG_DIR)/dashboard.log 2>&1 & echo $$! > $(PID_DIR)/dashboard.pid
	@echo "Services started. Tailing logs (Ctrl-C to detach, services keep running)..."
	@trap 'make stop' INT; \
	tail -F $(LOG_DIR)/*.log

dev: state-dirs
	@echo "Booting in dev mode with hot-reload..."
	@echo ""
	mkdir -p $(LOG_DIR)
	cd $(AGENT_DIR) && $(PIP) run uvicorn llm.main:app --reload --port $(AGENT_PORT) > $(LOG_DIR)/llm.log 2>&1 & echo $$! > $(PID_DIR)/llm.pid
	cd $(DASH_DIR) && $(NPM) run dev > $(LOG_DIR)/dashboard.log 2>&1 & echo $$! > $(PID_DIR)/dashboard.pid
	@echo "Dev mode running. Press Ctrl-C to stop."
	@trap 'make stop' INT; tail -F $(LOG_DIR)/*.log

stop:
	@echo "Stopping all services..."
	@for pidfile in $(PID_DIR)/*.pid; do \
		if [ -f $$pidfile ]; then \
			pid=$$(cat $$pidfile); \
			if kill -0 $$pid 2>/dev/null; then \
				echo "  Killing PID $$pid ($$(basename $$pidfile .pid))"; \
				kill $$pid 2>/dev/null; \
			fi; \
			rm -f $$pidfile; \
		fi; \
	done
	@pkill -f "homepod-agent" 2>/dev/null || true

# ---- test ------------------------------------------------------------------

test:
	cd $(AGENT_DIR) && $(PIP) run pytest tests/ -v

smoke:
	@echo "Running end-to-end smoke test..."
	cd $(AGENT_DIR) && $(PIP) run pytest tests/smoke/ -v -s

lint:
	cd $(AGENT_DIR) && $(PIP) run ruff check .
	cd $(AGENT_DIR) && $(PIP) run mypy .
	cd $(DASH_DIR) && $(NPM) run lint

# ---- logs ------------------------------------------------------------------

logs:
	@mkdir -p $(LOG_DIR)
	@ls -la $(LOG_DIR)
	@echo ""
	@echo "Tailing (Ctrl-C to detach)..."
	tail -F $(LOG_DIR)/*.log

# ---- clean -----------------------------------------------------------------

clean:
	@echo "Removing build artifacts..."
	cd $(AGENT_DIR) && rm -rf .pytest_cache .mypy_cache .ruff_cache __pycache__ */__pycache__ *.egg-info
	cd $(DASH_DIR) && rm -rf .next node_modules/.cache
	cd $(IPAD_DIR) && rm -rf .build
	@echo "✅ Clean."