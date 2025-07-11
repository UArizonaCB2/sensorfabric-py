#!/bin/bash

# Comprehensive deployment automation script for SensorFabric Lambda functions
# This script provides a complete deployment pipeline with validation and rollback capabilities

set -e  # Exit on any error

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_NAME="sensorfabric"
ECR_REGISTRY="509812589231.dkr.ecr.us-east-1.amazonaws.com"
ECR_REPOSITORY="uh-biobayb"
AWS_REGION="us-east-1"
CDK_DIR="$SCRIPT_DIR/cdk"

# Lambda function mappings
declare -A LAMBDA_FUNCTIONS=(
    ["uh_upload"]="biobayb_uh_uploader"
    ["uh_publisher"]="biobayb_uh_sns_publisher"
)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_warning() {
    echo -e "${YELLOW}[WARN]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_header() {
    echo -e "${BLUE}[HEADER]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_debug() {
    if [ "$DEBUG" = "true" ]; then
        echo -e "${PURPLE}[DEBUG]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
    fi
}

# Validation functions
validate_prerequisites() {
    log_header "Validating prerequisites..."
    
    local errors=0
    
    # Check required tools
    local required_tools=("docker" "aws" "cdk" "python3" "pip")
    for tool in "${required_tools[@]}"; do
        if ! command -v "$tool" &> /dev/null; then
            log_error "$tool is not installed or not in PATH"
            errors=$((errors + 1))
        else
            log_debug "$tool is available"
        fi
    done
    
    # Check Docker daemon
    if ! docker info &> /dev/null; then
        log_error "Docker daemon is not running"
        errors=$((errors + 1))
    fi
    
    # Check AWS credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "AWS credentials are not configured"
        errors=$((errors + 1))
    else
        local aws_account=$(aws sts get-caller-identity --query Account --output text)
        local aws_region=$(aws configure get region)
        log_info "AWS Account: $aws_account, Region: $aws_region"
    fi
    
    # Check CDK bootstrap
    if ! aws cloudformation describe-stacks --stack-name CDKToolkit --region "$AWS_REGION" &> /dev/null; then
        log_warning "CDK is not bootstrapped in this region. Run 'cdk bootstrap' first."
    fi
    
    # Check project structure
    local required_files=("requirements.txt" "sensorfabric/" "docker/Dockerfile")
    for file in "${required_files[@]}"; do
        if [ ! -e "$SCRIPT_DIR/$file" ]; then
            log_error "Required file/directory not found: $file"
            errors=$((errors + 1))
        fi
    done
    
    if [ $errors -gt 0 ]; then
        log_error "Validation failed with $errors errors"
        exit 1
    fi
    
    log_info "All prerequisites validated successfully"
}

# Backup current Lambda functions
backup_lambda_functions() {
    log_header "Creating backup of current Lambda functions..."
    
    local backup_dir="$SCRIPT_DIR/backup/$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$backup_dir"
    
    for local_func in "${!LAMBDA_FUNCTIONS[@]}"; do
        local aws_func=${LAMBDA_FUNCTIONS[$local_func]}
        
        log_info "Backing up $aws_func..."
        
        # Get function configuration
        aws lambda get-function-configuration \
            --function-name "$aws_func" \
            --region "$AWS_REGION" \
            --output json > "$backup_dir/${aws_func}_config.json" 2>/dev/null || {
            log_warning "Could not backup configuration for $aws_func (function may not exist)"
        }
        
        # Get function code location
        aws lambda get-function \
            --function-name "$aws_func" \
            --region "$AWS_REGION" \
            --output json > "$backup_dir/${aws_func}_function.json" 2>/dev/null || {
            log_warning "Could not backup function code info for $aws_func"
        }
    done
    
    echo "$backup_dir" > "$SCRIPT_DIR/.last_backup"
    log_info "Backup completed in: $backup_dir"
}

# Test Lambda functions
test_lambda_functions() {
    log_header "Testing Lambda functions..."
    
    for local_func in "${!LAMBDA_FUNCTIONS[@]}"; do
        local aws_func=${LAMBDA_FUNCTIONS[$local_func]}
        
        log_info "Testing $aws_func..."
        
        # Create test event
        local test_event='{
            "Records": [
                {
                    "eventSource": "aws:sns",
                    "eventVersion": "1.0",
                    "eventSubscriptionArn": "arn:aws:sns:us-east-1:123456789012:test-topic",
                    "sns": {
                        "Message": "{\"participant_id\": \"test-participant\", \"test\": true}",
                        "MessageId": "test-message-id",
                        "Subject": "Test Event",
                        "Timestamp": "2023-01-01T00:00:00.000Z",
                        "TopicArn": "arn:aws:sns:us-east-1:123456789012:test-topic"
                    }
                }
            ]
        }'
        
        # Invoke function with test event
        local response_file="/tmp/${aws_func}_test_response.json"
        local log_file="/tmp/${aws_func}_test_logs.txt"
        
        aws lambda invoke \
            --function-name "$aws_func" \
            --payload "$test_event" \
            --log-type Tail \
            --region "$AWS_REGION" \
            --cli-binary-format raw-in-base64-out \
            "$response_file" \
            --query 'LogResult' \
            --output text 2>/dev/null | base64 -d > "$log_file" || {
            log_error "Test failed for $aws_func"
            return 1
        }
        
        # Check response
        if grep -q "error" "$response_file" 2>/dev/null; then
            log_error "Test failed for $aws_func - check logs at $log_file"
            cat "$response_file"
            return 1
        else
            log_info "Test passed for $aws_func"
        fi
        
        # Clean up
        rm -f "$response_file" "$log_file"
    done
    
    log_info "All Lambda function tests passed"
}

# Rollback to previous version
rollback_deployment() {
    log_header "Rolling back deployment..."
    
    if [ ! -f "$SCRIPT_DIR/.last_backup" ]; then
        log_error "No backup found for rollback"
        return 1
    fi
    
    local backup_dir=$(cat "$SCRIPT_DIR/.last_backup")
    if [ ! -d "$backup_dir" ]; then
        log_error "Backup directory not found: $backup_dir"
        return 1
    fi
    
    log_info "Rolling back using backup: $backup_dir"
    
    for local_func in "${!LAMBDA_FUNCTIONS[@]}"; do
        local aws_func=${LAMBDA_FUNCTIONS[$local_func]}
        local config_file="$backup_dir/${aws_func}_config.json"
        local function_file="$backup_dir/${aws_func}_function.json"
        
        if [ -f "$config_file" ] && [ -f "$function_file" ]; then
            log_info "Rolling back $aws_func..."
            
            # Get previous image URI
            local image_uri=$(jq -r '.Code.ImageUri' "$function_file")
            
            if [ "$image_uri" != "null" ]; then
                aws lambda update-function-code \
                    --function-name "$aws_func" \
                    --image-uri "$image_uri" \
                    --region "$AWS_REGION" \
                    --output table
                
                log_info "Rolled back $aws_func to previous version"
            else
                log_warning "Could not find previous image URI for $aws_func"
            fi
        else
            log_warning "Backup files not found for $aws_func"
        fi
    done
    
    log_info "Rollback completed"
}

# Health check
health_check() {
    log_header "Performing health check..."
    
    local health_check_passed=true
    
    for local_func in "${!LAMBDA_FUNCTIONS[@]}"; do
        local aws_func=${LAMBDA_FUNCTIONS[$local_func]}
        
        log_info "Checking health of $aws_func..."
        
        # Check function state
        local state=$(aws lambda get-function-configuration \
            --function-name "$aws_func" \
            --region "$AWS_REGION" \
            --query 'State' \
            --output text 2>/dev/null)
        
        if [ "$state" = "Active" ]; then
            log_info "$aws_func is Active"
        else
            log_error "$aws_func is not Active (State: $state)"
            health_check_passed=false
        fi
        
        # Check recent errors
        local error_count=$(aws logs filter-log-events \
            --log-group-name "/aws/lambda/$aws_func" \
            --start-time $(date -d '5 minutes ago' +%s)000 \
            --filter-pattern "ERROR" \
            --region "$AWS_REGION" \
            --query 'length(events)' \
            --output text 2>/dev/null || echo "0")
        
        if [ "$error_count" -gt 0 ]; then
            log_warning "$aws_func has $error_count errors in the last 5 minutes"
        else
            log_info "$aws_func has no recent errors"
        fi
    done
    
    if [ "$health_check_passed" = true ]; then
        log_info "Health check passed"
        return 0
    else
        log_error "Health check failed"
        return 1
    fi
}

# Deploy pipeline
deploy_pipeline() {
    local deployment_method=${1:-"direct"}
    local skip_tests=${2:-false}
    
    log_header "Starting deployment pipeline (method: $deployment_method)..."
    
    # Validate prerequisites
    validate_prerequisites
    
    # Create backup
    backup_lambda_functions
    
    # Run build and deploy
    log_info "Running build and deploy script..."
    if [ "$deployment_method" = "cdk" ]; then
        "$SCRIPT_DIR/build_and_deploy.sh" --use-cdk
    else
        "$SCRIPT_DIR/build_and_deploy.sh"
    fi
    
    # Wait for deployment to stabilize
    log_info "Waiting for deployment to stabilize..."
    sleep 30
    
    # Run tests if not skipped
    # TODO fix tests.
    # if [ "$skip_tests" = false ]; then
    #     if ! test_lambda_functions; then
    #         log_error "Tests failed - initiating rollback"
    #         rollback_deployment
    #         exit 1
    #     fi
    # fi
    
    # Health check
    if ! health_check; then
        log_error "Health check failed - initiating rollback"
        rollback_deployment
        exit 1
    fi
    
    log_info "Deployment pipeline completed successfully"
}

# Main function with argument parsing
main() {
    local deployment_method="direct"
    local skip_tests=false
    local action="deploy"
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --cdk)
                deployment_method="cdk"
                shift
                ;;
            --skip-tests)
                skip_tests=true
                shift
                ;;
            --rollback)
                action="rollback"
                shift
                ;;
            --health-check)
                action="health-check"
                shift
                ;;
            --test)
                action="test"
                shift
                ;;
            --debug)
                DEBUG=true
                shift
                ;;
            --help|-h)
                cat << EOF
Usage: $0 [OPTIONS]

Comprehensive deployment automation for SensorFabric Lambda functions.

Options:
  --cdk                 Use CDK for deployment instead of direct Lambda updates
  --skip-tests          Skip function testing after deployment
  --rollback            Rollback to previous deployment
  --health-check        Perform health check only
  --test                Run tests only
  --debug               Enable debug logging
  --help, -h            Show this help message

Examples:
  $0                    # Deploy with direct Lambda updates
  $0 --cdk              # Deploy using CDK
  $0 --skip-tests       # Deploy without running tests
  $0 --rollback         # Rollback to previous version
  $0 --health-check     # Check current deployment health
  $0 --test             # Run tests on current deployment

Environment variables:
  DEBUG                 Enable debug logging (true/false)
  VERSION               Version tag for Docker images
  AWS_PROFILE           AWS profile to use
EOF
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done
    
    case $action in
        deploy)
            deploy_pipeline "$deployment_method" "$skip_tests"
            ;;
        rollback)
            rollback_deployment
            ;;
        health-check)
            health_check
            ;;
        test)
            test_lambda_functions
            ;;
        *)
            log_error "Unknown action: $action"
            exit 1
            ;;
    esac
}

# Error handling
trap 'log_error "Script failed at line $LINENO"' ERR

# Change to script directory
cd "$SCRIPT_DIR"

# Run main function
main "$@"