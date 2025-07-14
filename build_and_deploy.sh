#!/bin/bash

# Enhanced build and deploy script for SensorFabric Lambda functions
# Creates Docker images, pushes to ECR, and optionally deploys via CDK

set -e  # Exit on any error

# Configuration
DOCKER_DIR="docker"
BUILD_DIR="build"
CDK_DIR="cdk"
ECR_REGISTRY="509812589231.dkr.ecr.us-east-1.amazonaws.com"
ECR_REPOSITORY="uh-biobayb"
AWS_REGION="us-east-1"

# Lambda function mapping: local_name -> aws_function_name
declare -A LAMBDA_FUNCTIONS=(
    ["uh_upload"]="biobayb_uh_uploader"
    ["uh_publisher"]="biobayb_uh_sns_publisher"
)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${BLUE}[HEADER]${NC} $1"
}

# Check if required tools are installed
check_prerequisites() {
    print_header "Checking prerequisites..."
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    if ! docker info &> /dev/null; then
        print_error "Docker is not running. Please start Docker first."
        exit 1
    fi
    
    # Check AWS CLI
    if ! command -v aws &> /dev/null; then
        print_error "AWS CLI is not installed. Please install AWS CLI first."
        exit 1
    fi
    
    # Check AWS credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        print_error "AWS credentials not configured. Please run 'aws configure' first."
        exit 1
    fi
    
    print_status "All prerequisites satisfied"
}

# Authenticate with ECR
ecr_login() {
    print_header "Authenticating with ECR..."
    
    aws ecr get-login-password --region $AWS_REGION | \
        docker login --username AWS --password-stdin $ECR_REGISTRY
    
    if [ $? -eq 0 ]; then
        print_status "Successfully authenticated with ECR"
    else
        print_error "Failed to authenticate with ECR"
        exit 1
    fi
}

# Create build directories for each lambda function
setup_build_directories() {
    print_header "Setting up build directories..."
    
    # Clean up existing build directory
    if [ -d "$BUILD_DIR" ]; then
        rm -rf "$BUILD_DIR"
    fi
    
    # Create build directories for each lambda function
    for local_func in "${!LAMBDA_FUNCTIONS[@]}"; do
        mkdir -p "$BUILD_DIR/$local_func"
        
        # Copy requirements.txt
        cp requirements.txt "$BUILD_DIR/$local_func/"
        
        # Copy entire sensorfabric package
        cp -r sensorfabric/ "$BUILD_DIR/$local_func/"
        
        # Copy and customize Dockerfile
        cp "$DOCKER_DIR/Dockerfile" "$BUILD_DIR/$local_func/"
        
        # Update CMD in Dockerfile to point to correct handler
        sed -i "s/CMD \[\".*\"\]/CMD [\"sensorfabric.${local_func}.lambda_handler\"]/" "$BUILD_DIR/$local_func/Dockerfile"
        
        print_status "Created build directory for $local_func"
    done
}

# Build Docker image for a specific lambda function
build_lambda_image() {
    local local_func=$1
    local aws_func=${LAMBDA_FUNCTIONS[$local_func]}
    local image_name="$ECR_REGISTRY/$ECR_REPOSITORY:$aws_func"
    local build_context="$BUILD_DIR/$local_func"
    
    print_header "Building Docker image for $local_func -> $aws_func..."
    
    # Build the Docker image
    docker buildx build --platform linux/amd64 --provenance=false \
        -t "$image_name" \
        -f "$build_context/Dockerfile" \
        "$build_context"
    
    if [ $? -eq 0 ]; then
        print_status "Successfully built $image_name"
        
        # Tag with version if available
        if [ -n "$VERSION" ]; then
            local versioned_image="$ECR_REGISTRY/$ECR_REPOSITORY:$aws_func-$VERSION"
            docker tag "$image_name" "$versioned_image"
            print_status "Tagged $versioned_image"
        fi
    else
        print_error "Failed to build $image_name"
        exit 1
    fi
}

# Push Docker image to ECR
push_to_ecr() {
    local local_func=$1
    local aws_func=${LAMBDA_FUNCTIONS[$local_func]}
    local image_name="$ECR_REGISTRY/$ECR_REPOSITORY:$aws_func"
    
    print_header "Pushing image to ECR: $image_name"
    
    docker push "$image_name"
    
    if [ $? -eq 0 ]; then
        print_status "Successfully pushed $image_name to ECR"
        
        # Push versioned image if available
        if [ -n "$VERSION" ]; then
            local versioned_image="$ECR_REGISTRY/$ECR_REPOSITORY:$aws_func-$VERSION"
            docker push "$versioned_image"
            print_status "Successfully pushed $versioned_image to ECR"
        fi
    else
        print_error "Failed to push $image_name to ECR"
        exit 1
    fi
}

# Update Lambda function to use new container image
update_lambda_function() {
    local local_func=$1
    local aws_func=${LAMBDA_FUNCTIONS[$local_func]}
    local image_uri="$ECR_REGISTRY/$ECR_REPOSITORY:$aws_func"
    
    print_header "Updating Lambda function: $aws_func"
    
    # Update function code to use new container image
    aws lambda update-function-code \
        --function-name "$aws_func" \
        --image-uri "$image_uri" \
        --region "$AWS_REGION" \
        --output table
    
    if [ $? -eq 0 ]; then
        print_status "Successfully updated Lambda function $aws_func"
        
        # Wait for function to be updated
        print_status "Waiting for function update to complete..."
        aws lambda wait function-updated --function-name "$aws_func" --region "$AWS_REGION"
        print_status "Function update completed for $aws_func"
    else
        print_error "Failed to update Lambda function $aws_func"
        exit 1
    fi
}

# Deploy using CDK (optional)
deploy_with_cdk() {
    if [ -d "$CDK_DIR" ]; then
        print_header "Deploying infrastructure with CDK..."
        
        cd "$CDK_DIR"
        
        # Install CDK dependencies if needed
        if [ -f "requirements.txt" ]; then
            pip install -r requirements.txt
        fi
        
        # Deploy CDK stack
        cdk deploy --require-approval never
        
        cd ..
        print_status "CDK deployment completed"
    else
        print_warning "CDK directory not found. Skipping CDK deployment."
    fi
}

# Main build and deploy function
main() {
    print_header "Starting SensorFabric Lambda build and deploy process..."
    
    # Parse command line arguments
    local build_only=false
    local deploy_only=false
    local use_cdk=false
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --build-only)
                build_only=true
                shift
                ;;
            --deploy-only)
                deploy_only=true
                shift
                ;;
            --use-cdk)
                use_cdk=true
                shift
                ;;
            *)
                print_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done
    
    # Check prerequisites
    check_prerequisites
    
    # ECR authentication
    ecr_login
    
    if [ "$deploy_only" = false ]; then
        # Setup build directories
        setup_build_directories
        
        # Build and push each lambda function
        for local_func in "${!LAMBDA_FUNCTIONS[@]}"; do
            build_lambda_image "$local_func"
            push_to_ecr "$local_func"
        done
    fi
    
    if [ "$build_only" = false ]; then
        if [ "$use_cdk" = true ]; then
            deploy_with_cdk
        else
            # Update Lambda functions directly
            for local_func in "${!LAMBDA_FUNCTIONS[@]}"; do
                update_lambda_function "$local_func"
            done
        fi
    fi
    
    print_header "Build and deploy process completed successfully!"
    print_status "Updated Lambda functions:"
    for local_func in "${!LAMBDA_FUNCTIONS[@]}"; do
        local aws_func=${LAMBDA_FUNCTIONS[$local_func]}
        echo "  - $local_func -> $aws_func"
    done
}

# Clean up function
cleanup() {
    print_header "Cleaning up build directories and local Docker images..."
    
    # Remove build directory
    if [ -d "$BUILD_DIR" ]; then
        rm -rf "$BUILD_DIR"
        print_status "Removed build directory"
    fi
    
    # Remove local Docker images
    for local_func in "${!LAMBDA_FUNCTIONS[@]}"; do
        local aws_func=${LAMBDA_FUNCTIONS[$local_func]}
        local image_name="$ECR_REGISTRY/$ECR_REPOSITORY:$aws_func"
        
        if docker images -q "$image_name" &> /dev/null; then
            docker rmi "$image_name" &> /dev/null || true
            print_status "Removed local image: $image_name"
        fi
        
        # Remove versioned image if exists
        if [ -n "$VERSION" ]; then
            local versioned_image="$ECR_REGISTRY/$ECR_REPOSITORY:$aws_func-$VERSION"
            if docker images -q "$versioned_image" &> /dev/null; then
                docker rmi "$versioned_image" &> /dev/null || true
                print_status "Removed local versioned image: $versioned_image"
            fi
        fi
    done
    
    print_status "Cleanup completed"
}

# Handle command line arguments
case "${1:-}" in
    --help|-h)
        echo "Usage: $0 [OPTIONS]"
        echo "Build Docker images, push to ECR, and deploy Lambda functions"
        echo ""
        echo "Options:"
        echo "  --help, -h        Show this help message"
        echo "  --build-only      Only build and push images, don't deploy"
        echo "  --deploy-only     Only deploy (assumes images already exist in ECR)"
        echo "  --use-cdk         Use CDK for deployment instead of direct Lambda updates"
        echo "  --clean, -c       Clean up build directories and Docker images"
        echo ""
        echo "Environment variables:"
        echo "  VERSION           Optional version tag for Docker images"
        echo "  AWS_PROFILE       AWS profile to use (optional)"
        echo ""
        echo "Examples:"
        echo "  $0                        # Build, push, and deploy all functions"
        echo "  $0 --build-only           # Only build and push to ECR"
        echo "  $0 --deploy-only          # Only deploy from existing ECR images"
        echo "  $0 --use-cdk              # Use CDK for deployment"
        echo "  VERSION=v1.0.0 $0         # Build with version tag"
        echo "  $0 --clean                # Clean up build artifacts"
        exit 0
        ;;
    --clean|-c)
        cleanup
        exit 0
        ;;
    "")
        # Default action - build and deploy
        main
        ;;
    *)
        # Pass all arguments to main function
        main "$@"
        ;;
esac