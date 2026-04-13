#!/bin/bash
# =============================================================================
# Harmonia Experiment SBATCH Template - GPU with Local LLM (Ollama)
# =============================================================================
# This template is used by generate_jobs.py to create GPU job scripts.
# Variables in {{double_braces}} are replaced by the generator.
#
# Usage:
#   sbatch jobs/experiment_ollama.sh
#
# Or generate jobs first:
#   python generate_jobs.py --config experiments/configs/dou_harmonization_nemotron.yaml --gpu
#
# Note: Ollama server is automatically started by exec_apptainer_harmonia.sh
#       when a local LLM provider is detected (ollama, anyllm:ollama, etc.)
# =============================================================================

#SBATCH --job-name=harmonia_{{experiment_name}}
#SBATCH --output=/dev/null
#SBATCH --error=/dev/null
#SBATCH --time={{time_limit}}
#SBATCH --mem={{memory}}
#SBATCH --cpus-per-task={{cpus}}
#SBATCH --gres=gpu:quadro_rtx_6000:1,tmpspace:{{tmpspace}}G
#SBATCH --partition=gpu

# =============================================================================
# Environment Setup
# =============================================================================

set -e

# Generate unique run ID for linking logs to results
RUN_ID=$(python3 -c "import secrets; print(secrets.token_hex(4))")
export RUN_ID
TIMESTAMP=$(date -u +%Y%m%d_%H%M%S)

# Create deterministic per-run results directory
RUN_RESULTS_DIR="results/${TIMESTAMP}_{{experiment_name}}_${SLURM_JOB_ID}_${RUN_ID}"
mkdir -p "$RUN_RESULTS_DIR"

# Redirect all output to date-stamped log files (includes run_id)
LOG_TIMESTAMP=$(date +%d-%m-%Y_%H%M)
LOG_OUT="logs/${LOG_TIMESTAMP}_{{experiment_name}}_${SLURM_JOB_ID}_${RUN_ID}.out"
LOG_ERR="logs/${LOG_TIMESTAMP}_{{experiment_name}}_${SLURM_JOB_ID}_${RUN_ID}.err"
mkdir -p logs
exec > "$LOG_OUT" 2> "$LOG_ERR"

echo "=============================================="
echo "Harmonia Experiment (GPU): {{experiment_name}}"
echo "=============================================="
echo ""
echo "Job ID: $SLURM_JOB_ID"
echo "Run ID: $RUN_ID"
echo "Node: $(hostname)"
echo "Date: $(date)"
echo ""

# Change to project directory
cd {{project_dir}}

# Dynamic port based on job ID to avoid conflicts
PORT=$((8100 + (SLURM_JOB_ID % 100)))
OLLAMA_PORT=$((11434 + 1 + (SLURM_JOB_ID % 200)))
echo "Using Beaker port: $PORT, Ollama port: $OLLAMA_PORT"

# Create logs directory
mkdir -p logs

# =============================================================================
# Start Beaker Server with exec_apptainer_harmonia.sh
# =============================================================================
# The exec script handles:
# - Ollama auto-start for local LLM providers (ollama, anyllm:ollama)
# - Ollama logging to logs/ollama_<timestamp>.log
# - Model pre-loading/warming
# - Apptainer image selection (new harmonia image with litellm support)
# - Data and results directory binding
# - Environment variable configuration

echo ""
echo "Starting Beaker server on port $PORT..."
echo "LLM Provider: {{llm_provider}}"
echo "LLM Model: {{llm_model}}"
echo ""

# Start Beaker server via exec script (handles Ollama automatically)
./exec_apptainer_harmonia.sh \
    --port $PORT \
    --config {{config_path}} \
    --job-name "{{experiment_name}}_${SLURM_JOB_ID}" \
    --results-dir "$RUN_RESULTS_DIR" \
    --run-id "$RUN_ID" &

SERVER_PID=$!
echo "Beaker Server PID: $SERVER_PID"

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "Cleaning up..."
    if [ -n "$SERVER_PID" ]; then
        kill $SERVER_PID 2>/dev/null || true
        wait $SERVER_PID 2>/dev/null || true
    fi
    echo "Done."
}
trap cleanup EXIT

# Wait for server to be ready
echo "Waiting for Beaker server to start..."
MAX_WAIT=900  # 15 minutes - allows time for Ollama model loading + Beaker startup (30B+ models need 5-10min)
WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
    if curl -s -o /dev/null -w "%{http_code}" "http://localhost:$PORT/api" 2>/dev/null | grep -q "200\|401"; then
        echo "Beaker server is ready!"
        break
    fi
    sleep 2
    WAITED=$((WAITED + 2))
    echo "  Waiting... ($WAITED/$MAX_WAIT seconds)"
done

if [ $WAITED -ge $MAX_WAIT ]; then
    echo "ERROR: Beaker server failed to start within $MAX_WAIT seconds"
    exit 1
fi

# =============================================================================
# Run Experiment
# =============================================================================

echo ""
echo "Running experiment..."
echo "Config: {{config_path}}"
echo ""

# Get token from env file
TOKEN=$(grep "^JUPYTER_TOKEN=" {{env_file}} | cut -d '=' -f2)

# Run the experiment
.venv/bin/python run_experiment.py \
    --config {{config_path}} \
    --server http://localhost:$PORT \
    --token "$TOKEN" \
    --timeout {{timeout}}

EXIT_CODE=$?

# =============================================================================
# Completion
# =============================================================================

echo ""
echo "=============================================="
if [ $EXIT_CODE -eq 0 ]; then
    echo "Experiment completed successfully!"
else
    echo "Experiment failed with exit code: $EXIT_CODE"
fi
echo "=============================================="

exit $EXIT_CODE
