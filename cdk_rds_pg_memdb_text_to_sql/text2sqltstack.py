#chuyen toi thu muc code
# /*
#  * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#  * SPDX-License-Identifier: MIT-0
#  *
#  * Permission is hereby granted, free of charge, to any person obtaining a copy of this
#  * software and associated documentation files (the "Software"), to deal in the Software
#  * without restriction, including without limitation the rights to use, copy, modify,
#  * merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
#  * permit persons to whom the Software is furnished to do so.
#  *
#  * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
#  * INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
#  * PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
#  * HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
#  * OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
#  * SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#  */

import os

from aws_cdk import (
    aws_iam as iam,
    aws_rds as rds,
    aws_ec2 as ec2,
    aws_lambda as lambda_,
    aws_secretsmanager as sm,
    aws_logs as logs,
    Stack,
    Duration,
    BundlingOptions
)
from cdk_nag import NagSuppressions
from constructs import Construct


class Text2SQLStack(Stack):

    def __init__(
            self,
            scope: Construct,
            construct_id: str,
            db_instance: rds.IDatabaseInstance,
            vpc: ec2.IVpc,
            security_group: ec2.ISecurityGroup,
            readonly_secret: sm.ISecret,
            **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        asset_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "code"
        )
        # Create an IAM role for the Lambda function
        lambda_role = iam.Role( 
            self, "text2sqlRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaVPCAccessExecutionRole")
            ]
        )
        NagSuppressions.add_resource_suppressions(lambda_role, [
            {"id": "AwsSolutions-IAM4", "reason": "This is a managed policy for Lambda VPC execution.",
             "appliesTo": ["Policy::arn:<AWS::Partition>:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"]}
        ])
        # Attach inline policy to Lambda role for Secrets Manager access
        lambda_role.attach_inline_policy(
            iam.Policy(
                self, "LambdaSecretsManagerPolicy",
                statements=[
                    iam.PolicyStatement(
                        effect=iam.Effect.ALLOW,
                        actions=["secretsmanager:GetSecretValue"],
                        resources=[self.readonly_secret.secret_arn]
                    )
                ]
            )
        )
        # Add Bedrock InvokeModel permissions for Anthropic Claude to Lambda role
        lambda_role.attach_inline_policy(
            iam.Policy(
                self, "LambdaBedrockPolicy",
                statements=[
                    iam.PolicyStatement(
                        actions=["bedrock:InvokeModel"],
                        resources=[
                            f"arn:aws:bedrock:{self.region}::foundation-model/amazon.titan-embed-text-v1",
                            f"arn:aws:bedrock:{self.region}::foundation-model/anthropic.claude-3-5-sonnet-20240620-v1:0"]
                    )]
            )
        )
        # Grant the Lambda function read access to the RDS secret
        db_instance.secret.grant_read(lambda_role)

        function = lambda_.Function(
            self, "TextToSQLFunction",
            function_name="AppStack-TextToSQLFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="prompt_handler.lambda_handler",
            code=lambda_.Code.from_asset(
                asset_path,
                bundling=BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_12.bundling_image,
                    platform="linux/amd64",
                    command=[
                        "bash",
                        "-c",
                        "pip install --platform manylinux2014_x86_64 --target /asset-output --implementation cp " +
                        "--python-version 3.12 --only-binary=:all: --upgrade -r requirements.txt && cp -au . " +
                        "/asset-output",
                    ]
                )
            ),
            role=lambda_role,
            timeout=Duration.seconds(60),# có thể set lâu hơn nếu cần
            vpc=vpc,
            security_groups=[security_group],
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            memory_size=3072,
            environment={
                "SECRET_NAME": readonly_secret.secret_name,
                "RDS_HOST": db_instance.instance_endpoint.hostname,
            },
            log_retention=logs.RetentionDays.ONE_WEEK
        )
        NagSuppressions.add_stack_suppressions(
            self,
            [
                # Suppress IAM4 for LogRetention Lambda roles
                {
                    "id": "AwsSolutions-IAM4",
                    "reason": "Lambda log retention uses AWS managed policy for basic execution which is acceptable for this use case",
                    "appliesTo": [
                        "Policy::arn:<AWS::Partition>:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
                    ]
                },
                # Suppress IAM5 for LogRetention Lambda roles
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "Lambda log retention requires these permissions to function correctly",
                    "appliesTo": [
                        "Resource::*"
                    ]
                }
        ])