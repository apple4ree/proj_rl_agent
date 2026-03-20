#!/bin/bash
# =============================================================
# LOB Optimal Execution — 서버 셋업 스크립트
# =============================================================
# 사용법:
#   chmod +x setup.sh
#   ./setup.sh
# =============================================================

set -e  # 에러 발생 시 중단

PROJECT_DIR="$HOME/projects/lob-execution"
ENV_NAME="lob-exec"

echo "============================================"
echo " LOB Execution Project Setup"
echo "============================================"

# 1. 프로젝트 루트 생성
echo "[1/6] 프로젝트 디렉토리 생성..."
mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"

# 2. 빈 디렉토리 골격 생성 (src/ 하위는 deploy 파일로 채워짐)
echo "[2/6] 디렉토리 구조 생성..."
mkdir -p src/{agent,utils}
mkdir -p scripts
mkdir -p notebooks
mkdir -p conf
mkdir -p data/{raw,processed}
mkdir -p checkpoints
mkdir -p logs

# .gitkeep for empty dirs
touch notebooks/.gitkeep data/raw/.gitkeep data/processed/.gitkeep
touch checkpoints/.gitkeep logs/.gitkeep

# 3. PYTHONPATH 등록
echo "[3/6] PYTHONPATH 설정..."
if ! grep -q "lob-execution" ~/.bashrc 2>/dev/null; then
    echo '' >> ~/.bashrc
    echo '# LOB Execution project' >> ~/.bashrc
    echo "export PYTHONPATH=\"$PROJECT_DIR:\$PYTHONPATH\"" >> ~/.bashrc
    echo "   → ~/.bashrc에 PYTHONPATH 추가됨"
else
    echo "   → PYTHONPATH 이미 설정됨, 스킵"
fi
export PYTHONPATH="$PROJECT_DIR:$PYTHONPATH"

# 4. Conda 환경 생성
echo "[4/6] Conda 환경 생성..."
if conda env list | grep -q "^${ENV_NAME} "; then
    echo "   → 환경 '${ENV_NAME}' 이미 존재함, 스킵"
else
    conda env create -f environment.yml
    echo "   → 환경 '${ENV_NAME}' 생성 완료"
fi

# 5. GPU 확인
echo "[5/6] GPU 확인..."
if command -v nvidia-smi &> /dev/null; then
    echo "   → GPU 감지됨:"
    nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader | head -1 | sed 's/^/     /'

    # CUDA 버전 확인
    CUDA_VER=$(nvidia-smi | grep -oP 'CUDA Version: \K[0-9.]+')
    echo "   → CUDA Version: ${CUDA_VER}"
    echo ""
    echo "   ⚠️  environment.yml의 pytorch-cuda 버전이 ${CUDA_VER}과 호환되는지 확인하세요."
    echo "      현재 설정: pytorch-cuda=12.1"
    echo "      불일치 시: environment.yml 수정 후 conda env update -f environment.yml"
else
    echo "   → nvidia-smi 미발견 — GPU 설정 확인 필요"
fi

# 6. 환경 테스트
echo "[6/6] 환경 테스트 실행..."
echo ""

# conda activate는 스크립트 내에서 직접 안 될 수 있으므로 안내
echo "============================================"
echo " 셋업 완료!"
echo "============================================"
echo ""
echo " 다음 명령으로 테스트를 실행하세요:"
echo ""
echo "   conda activate ${ENV_NAME}"
echo "   cd ${PROJECT_DIR}"
echo "   python -m tests.test_env"
echo ""
echo " 프로젝트 구조:"
find . -type f -not -path './.gitkeep' -not -name '.gitkeep' | sort | head -30
echo ""
