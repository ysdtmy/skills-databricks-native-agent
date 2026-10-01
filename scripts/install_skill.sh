#!/usr/bin/env bash
# ==============================================================================
# Installer for Databricks Native Agent Development Skill (`databricks-native-agent`)
# Distributes and registers the skill across user or project environments.
# ==============================================================================

set -euo pipefail

SKILL_NAME="databricks-native-agent"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "============================================================"
echo "Installing Databricks Native Agent Skill: ${SKILL_NAME}"
echo "Source: ${SKILL_DIR}"
echo "============================================================"

# Determine target directory
#   default            : ~/.gemini/antigravity-cli/skills   (Antigravity / Gemini CLI, global)
#   --project          : ./.agents/skills                    (Antigravity / Gemini CLI, this project)
#   --claude           : ~/.claude/skills                    (Claude Code, global)
#   --claude --project : ./.claude/skills                    (Claude Code, this project)
# Claude Code discovers the skill from SKILL.md's frontmatter; no CLAUDE.md is installed or needed.
SCOPE="global"
AGENT="gemini"

for arg in "$@"; do
    case "${arg}" in
        --project) SCOPE="project" ;;
        --global)  SCOPE="global" ;;
        --claude)  AGENT="claude" ;;
        *) echo "[!] Unknown option: ${arg} (supported: --project --global --claude)" >&2; exit 2 ;;
    esac
done

if [[ "${AGENT}" == "claude" ]]; then
    GLOBAL_SKILLS_DIR="${HOME}/.claude/skills"
    PROJECT_SKILLS_DIR="$(pwd)/.claude/skills"
else
    GLOBAL_SKILLS_DIR="${HOME}/.gemini/antigravity-cli/skills"
    PROJECT_SKILLS_DIR="$(pwd)/.agents/skills"
fi

if [[ "${SCOPE}" == "project" ]]; then
    TARGET_DIR="${PROJECT_SKILLS_DIR}"
else
    TARGET_DIR="${GLOBAL_SKILLS_DIR}"
fi
MODE="${AGENT}/${SCOPE}"

echo "[*] Installation mode: ${MODE}"
echo "[*] Target directory: ${TARGET_DIR}/${SKILL_NAME}"

mkdir -p "${TARGET_DIR}"

if [[ -e "${TARGET_DIR}/${SKILL_NAME}" || -L "${TARGET_DIR}/${SKILL_NAME}" ]]; then
    echo "[!] Target skill directory or link already exists. Updating..."
    rm -rf "${TARGET_DIR}/${SKILL_NAME}"
fi

# Link the skill (single source of truth stays in SKILL_DIR)
ln -s "${SKILL_DIR}" "${TARGET_DIR}/${SKILL_NAME}"
echo "[OK] Linked ${SKILL_DIR} -> ${TARGET_DIR}/${SKILL_NAME}"

# Verify prerequisites
echo ""
echo "[*] Running environment verification..."
if command -v python3 >/dev/null 2>&1; then
    python3 "${SKILL_DIR}/scripts/check_environment.py" || true
else
    echo "[WARN] python3 not found. Please install Python >= 3.11."
fi

echo "============================================================"
echo "Skill '${SKILL_NAME}' successfully installed!"
echo ""
echo "Supported Coding Agents:"
echo "  • Antigravity / Gemini CLI: Auto-discovers from skills directory"
echo "  • Claude Code (claude): install with --claude [--project]; invoke via /databricks-native-agent"
echo ""
echo "Example Prompts:"
echo "  'Create a customer support AI agent on Databricks using Agent Bricks'"
echo "  'Run local API tests on databricks-smart-agent and fix any errors'"
echo "============================================================"

