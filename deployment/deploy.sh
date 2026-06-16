#!/bin/sh
set -eu

###
### Script to deploy S3 bucket + lambda in cloudformation stack
###

### CONFIGURATION SECTION ###
aws_profile="$1" # e.g. sot-academy, for the aws credentials
your_name="spam" # Team name
deployment_bucket="${your_name}-deployment-bucket"

# Find absolute path
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Path to templates
TEMPLATE_DIR="${SCRIPT_DIR}/templates"

echo ""
echo "Deploying templates from: ${TEMPLATE_DIR}"
echo ""

# Create deployment bucket stack
echo ""
echo "Doing deployment bucket..."
echo ""

aws cloudformation deploy --stack-name "${your_name}-deployment-stack" \
    --template-file "${TEMPLATE_DIR}/deployment-bucket-stack.yml" --region eu-west-1 \
    --capabilities CAPABILITY_IAM --profile ${aws_profile} \
    --parameter-overrides \
      YourName="${your_name}";

if [ -z "${SKIP_PIP_INSTALL:-}" ]; then
    echo ""
    echo "Doing pip install..."
    # Install dependencies from requirements-lambda.txt into src directory with python 3.12
    # On windows may need to use `py` not `python3`
    python3 -m pip install --platform manylinux2014_x86_64 \
        --target="${SCRIPT_DIR}/src" --implementation cp --python-version 3.12 \
        --only-binary=:all: --upgrade -r "${SCRIPT_DIR}/requirements-lambda.txt";
else
    echo ""
    echo "Skipping pip install"
fi

# Create an updated ETL packaged template "etl-stack-packaged.yml" from the default "etl-stack.yml"
# ...and upload local resources to S3 (e.g zips files of your lambdas)
# A unique S3 filename is automatically generated each time
echo ""
echo "Doing packaging..."
echo ""
aws cloudformation package --template-file "${TEMPLATE_DIR}/etl-stack.yml" \
    --s3-bucket ${deployment_bucket} \
    --output-template-file "${TEMPLATE_DIR}/etl-stack-packaged.yml" \
    --profile ${aws_profile};

# Deploy the main ETL stack using the packaged template "etl-stack-packaged.yml"
echo ""
echo "Doing etl stack deployment..."
echo ""
aws cloudformation deploy --stack-name "${your_name}-etl-stack" \
    --template-file "${TEMPLATE_DIR}/etl-stack-packaged.yml" --region eu-west-1 \
    --capabilities CAPABILITY_IAM \
    --profile ${aws_profile} \
    --parameter-overrides \
      YourName="${your_name}";

echo ""
echo "...all done!"
echo ""
