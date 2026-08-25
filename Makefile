# One local endpoint, one engine at a time.
#
# vLLM, mlx-lm and Ollama each want the whole accelerator, so they all serve on the SAME
# port and only one runs at a time. The benchmark harness probes LOCAL_API_BASE and asks
# the server which engine it is, so nothing needs reconfiguring when you swap.
#
#   make serve-vllm      # terminal 1 — then, in terminal 2:
#   make probe           # what is live, what model, timed completion
#   make bench ENGINE=vllm
#   make stop            # before starting the next engine
#
# Setup for all three: examples/07_inference/00_running_engines.md

.PHONY: help ui probe bench config serve-vllm serve-mlx serve-ollama install-mlx pull-ollama stop

# Models and tuning parameters live in deploy/engines.yaml, shared with serve.sh. Make
# cannot read YAML, so engines.py renders it to a KEY=VALUE file make can include -
# regenerated whenever the YAML changes. Command-line overrides still win:
#   make serve-vllm VLLM_MODEL=mlx-community/Qwen3-4B-4bit
ENGINES_YAML ?= deploy/engines.yaml
ENGINES_MK := .engines.mk

$(ENGINES_MK): $(ENGINES_YAML) deploy/engines.py
	@.venv/bin/python deploy/engines.py --make > $@

-include $(ENGINES_MK)

# Fallbacks if the YAML is missing or predates a setting.
LOCAL_PORT ?= 8000
LOCAL_API_KEY ?= cookbook-local
VLLM_MODEL ?= mlx-community/Qwen3-0.6B-4bit
MLX_MODEL ?= mlx-community/Qwen3-0.6B-4bit
OLLAMA_MODEL ?= qwen3:0.6b
OLLAMA_NUM_PARALLEL ?= 32
OLLAMA_CONTEXT_LENGTH ?= 8192

MLX_VENV ?= $(HOME)/.venv-mlx-lm
ENGINE ?= vllm
# Ollama lists its whole model store, so when several are pulled and none is resident the
# harness cannot tell which one you mean. Set this (or LOCAL_MODEL in .env) to settle it.
LOCAL_MODEL ?=

help:
	@echo "Inference engines (all serve on :$(LOCAL_PORT), run one at a time)"
	@echo "  make serve-vllm            vllm-metal on Apple Silicon, plain vLLM on CUDA"
	@echo "  make serve-mlx             mlx_lm.server — the single-request control"
	@echo "  make serve-ollama          ollama serve with OLLAMA_NUM_PARALLEL=$(OLLAMA_NUM_PARALLEL)"
	@echo "  make stop                  kill whichever engine is running"
	@echo ""
	@echo "Measuring"
	@echo "  make probe                 identify the live endpoint + one timed completion"
	@echo "  make bench ENGINE=vllm     single-stream + concurrency sweep -> results/"
	@echo "  make ui                    Streamlit app (run sweeps from the browser)"
	@echo "  make config                show the active serving config"
	@echo ""
	@echo "One-time installs:  make install-mlx   make pull-ollama"
	@echo ""
	@echo "Ollama with several models pulled: make probe LOCAL_MODEL=$(OLLAMA_MODEL)"

ui:
	.venv/bin/streamlit run ui/app.py

# --- Engines ----------------------------------------------------------------
serve-vllm:
	ENGINES_YAML=$(ENGINES_YAML) VLLM_MODEL=$(VLLM_MODEL) VLLM_PORT=$(LOCAL_PORT) \
		VLLM_API_KEY=$(LOCAL_API_KEY) ./deploy/vllm/local/serve.sh

serve-mlx:
	@test -x "$(MLX_VENV)/bin/mlx_lm.server" || { echo "mlx-lm not installed — run: make install-mlx"; exit 1; }
	"$(MLX_VENV)/bin/mlx_lm.server" --model $(MLX_MODEL) --port $(LOCAL_PORT)

# OLLAMA_HOST moves Ollama off its default 11434 onto the shared port. Its OpenAI-compatible
# API is then at http://localhost:$(LOCAL_PORT)/v1, same as the others.
serve-ollama:
	OLLAMA_HOST=127.0.0.1:$(LOCAL_PORT) OLLAMA_NUM_PARALLEL=$(OLLAMA_NUM_PARALLEL) \
		OLLAMA_CONTEXT_LENGTH=$(OLLAMA_CONTEXT_LENGTH) ollama serve

install-mlx:
	uv venv --python 3.12 "$(MLX_VENV)"
	VIRTUAL_ENV="$(MLX_VENV)" uv pip install mlx-lm

# Talks to the server started by `make serve-ollama`, so run that first (in another
# terminal). Weights land in the shared store either way.
pull-ollama:
	OLLAMA_HOST=127.0.0.1:$(LOCAL_PORT) ollama pull $(OLLAMA_MODEL)

stop:
	-@pkill -f "vllm serve" 2>/dev/null || true
	-@pkill -f "mlx_lm.server" 2>/dev/null || true
	-@pkill -f "ollama serve" 2>/dev/null || true
	@echo "Stopped any local engine on :$(LOCAL_PORT)."

# --- Measuring --------------------------------------------------------------
# These two are passed through because no endpoint reports them — the only serving
# parameters the harness has to be told rather than ask about. They land in the record
# starred, so a reader can tell declared from measured.
BENCH_ENV = LOCAL_MODEL=$(LOCAL_MODEL) OLLAMA_NUM_PARALLEL=$(OLLAMA_NUM_PARALLEL) \
	VLLM_MAX_NUM_SEQS=$(VLLM_MAX_NUM_SEQS)

probe:
	$(BENCH_ENV) .venv/bin/python examples/07_inference/01_backends.py

bench:
	$(BENCH_ENV) BENCH_SAVE_AS=$(ENGINE)_single.json \
		.venv/bin/python examples/07_inference/02_benchmark.py
	$(BENCH_ENV) BENCH_SAVE_AS=$(ENGINE)_sweep.json \
		.venv/bin/python examples/07_inference/03_load_sweep.py

config: $(ENGINES_MK)
	@echo "$(ENGINES_YAML)"
	@sed 's/^/  /' $(ENGINES_MK)
