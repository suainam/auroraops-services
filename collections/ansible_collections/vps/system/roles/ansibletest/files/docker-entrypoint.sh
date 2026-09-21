#!/bin/bash
# AuroraOps Local Test Entrypoint
# 用于本地 Docker 测试的入口脚本

set -e

# 配置 git 安全目录（解决 dubious ownership 问题）
git config --global --add safe.directory '*'

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 显示帮助信息
show_help() {
    cat << EOF
AuroraOps Local Test Runner

Usage:
  docker run --rm -v \$(pwd):/workspace auroraops-test-local [OPTIONS]

Options:
  --target ROLE       指定测试目标角色 (默认: system_base)
  --list              列出所有可用测试目标
  --shell             进入交互式 shell
  --help              显示此帮助信息

Environment Variables:
  TEST_TARGET         测试目标角色名称

Examples:
  # 测试单个角色
  docker run --rm -v \$(pwd):/workspace auroraops-test-local --target system_base

  # 进入交互式 shell
  docker run --rm -it -v \$(pwd):/workspace auroraops-test-local --shell

  # 列出所有测试目标
  docker run --rm -v \$(pwd):/workspace auroraops-test-local --list
EOF
}

# 列出所有测试目标
list_targets() {
    log_info "Available test targets:"
    if [ -d "/workspace/tests/integration/targets" ]; then
        ls -1 /workspace/tests/integration/targets/ | grep "^test_" | sed 's/^test_//' | sed 's/^/  - /'
    else
        log_warn "No test targets found in /workspace/tests/integration/targets"
    fi
}

# 进入交互式 shell
start_shell() {
    log_info "Starting interactive shell..."
    log_info "Ansible version: $(ansible --version | head -n 1)"
    log_info "Working directory: $(pwd)"
    /bin/bash
}

# 执行测试
run_test() {
    local target="${1:-system_base}"
    
    log_info "Starting ansible-test integration for target: $target"
    log_info "Working directory: $(pwd)"
    
    # 确定测试目标名称
    local test_target="$target"
    if [[ ! -d "tests/integration/targets/$target" && -d "tests/integration/targets/test_$target" ]]; then
        test_target="test_$target"
        log_info "Using test target: $test_target"
    fi
    
    # 检查目标是否存在
    if [ ! -d "tests/integration/targets/$test_target" ]; then
        log_error "Test target not found: tests/integration/targets/$test_target"
        log_info "Available targets:"
        list_targets
        exit 1
    fi
    
    # 进入正确的目录
    cd collections/ansible_collections/vps/system || {
        log_error "Failed to enter collection directory"
        exit 1
    }
    
    log_info "Collection directory: $(pwd)"
    log_info "Running: ansible-test integration $test_target -v"
    
    # 执行测试
    ansible-test integration "$test_target" -v 2>&1 | tee /tmp/test_output.log
    local exit_code=${PIPESTATUS[0]}
    
    if [ $exit_code -eq 0 ]; then
        log_info "Test completed successfully!"
    else
        log_error "Test failed with exit code: $exit_code"
        log_info "Output saved to: /tmp/test_output.log"
    fi
    
    return $exit_code
}

# 主逻辑
main() {
    # 如果没有参数，检查环境变量
    if [ $# -eq 0 ]; then
        if [ -n "$TEST_TARGET" ]; then
            run_test "$TEST_TARGET"
            exit $?
        else
            show_help
            exit 0
        fi
    fi
    
    # 解析参数
    case "$1" in
        --help|-h)
            show_help
            exit 0
            ;;
        --list|-l)
            list_targets
            exit 0
            ;;
        --shell|-s)
            start_shell
            exit 0
            ;;
        --target|-t)
            if [ -z "$2" ]; then
                log_error "Missing target name. Use: --target ROLE_NAME"
                exit 1
            fi
            run_test "$2"
            exit $?
            ;;
        *)
            # 如果参数不以 - 开头，假设它是目标名称
            if [[ ! "$1" == -* ]]; then
                run_test "$1"
                exit $?
            else
                log_error "Unknown option: $1"
                show_help
                exit 1
            fi
            ;;
    esac
}

# 执行主函数
main "$@"
