#!/bin/bash

# ==========================================
# 1. DEFINE YOUR AWS PROFILE AND STACKS
# ==========================================
# This tells the script to use the active SSO session you just logged into
export AWS_PROFILE="SarahDE"

# Replace these strings with the exact names of your CloudFormation stacks
STACK_A="spam-deployment-stack"   # The stack that holds the upload bucket
STACK_B="spam-etl-stack"     # The stack launched from the bucket

echo "Starting AWS teardown process using profile: ${AWS_PROFILE}..."

# ==========================================
# 2. HELPER FUNCTION TO EMPTY BUCKETS
# ==========================================
# This function finds all S3 buckets in a stack and empties them
empty_stack_buckets() {
    local stack_name="${1}"
    echo "Scanning stack '${stack_name}' for S3 buckets..."

    # Query CloudFormation for the physical names of any AWS::S3::Bucket resources
    local buckets=$(aws cloudformation describe-stack-resources \
        --stack-name "${stack_name}" \
        --query "StackResources[?ResourceType=='AWS::S3::Bucket'].PhysicalResourceId" \
        --output text 2>/dev/null)

    # If buckets are found, loop through and delete their contents
    if [ -n "${buckets}" ] && [ "${buckets}" != "None" ]; then
        # We purposely do not put quotes around ${buckets} here so bash 
        # can split the list into individual items if there are multiple buckets.
        for bucket in ${buckets}; do
            echo "Emptying bucket: ${bucket}..."
            aws s3 rm "s3://${bucket}" --recursive
        done
    else
        echo "No S3 buckets found or stack does not exist."
    fi
}

# ==========================================
# 3. TEAR DOWN STACK B (The Lambda Stack)
# ==========================================
empty_stack_buckets "${STACK_B}"

echo "Commanding CloudFormation to delete '${STACK_B}'..."
aws cloudformation delete-stack --stack-name "${STACK_B}"

echo "Waiting for '${STACK_B}' to fully delete... (This may take a minute)"
# This pauses the script until AWS confirms the stack is gone
aws cloudformation wait stack-delete-complete --stack-name "${STACK_B}"


# ==========================================
# 4. TEAR DOWN STACK A (The Initial S3 Stack)
# ==========================================
empty_stack_buckets "${STACK_A}"

echo "Commanding CloudFormation to delete '${STACK_A}'..."
aws cloudformation delete-stack --stack-name "${STACK_A}"

echo "Waiting for '${STACK_A}' to fully delete..."
aws cloudformation wait stack-delete-complete --stack-name "${STACK_A}"

echo "Teardown complete! Your AWS environment is clean."
