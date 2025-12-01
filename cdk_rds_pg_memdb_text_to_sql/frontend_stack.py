# /*
#  * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#  * SPDX-License-Identifier: MIT-0
#  */

import os
import json

from aws_cdk import (
    aws_iam as iam,
    aws_s3 as s3,
    aws_s3_deployment as s3_deployment, 
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_cognito as cognito,
    aws_ec2 as ec2,
    aws_lambda as lambda_,
    aws_apigateway as apigw,
    aws_secretsmanager as sm,
    aws_rds as rds,
    aws_glue as glue,
    aws_logs as logs,
    aws_events as events,
    aws_events_targets as targets,
    aws_ssm as ssm,
    CustomResource,
    Fn,
    Stack,
    Duration,
    BundlingOptions,
    CfnOutput,
    RemovalPolicy
)
from constructs import Construct

# SSM Parameter name for API endpoint (shared between stacks)
SSM_API_ENDPOINT = "/meetassist/admin/api-endpoint"

class FrontendStack(Stack):

    def __init__(
            self,
            scope: Construct,
            construct_id: str,
            vpc: ec2.IVpc = None,
            security_group: ec2.ISecurityGroup = None,
            data_stored_bucket: s3.IBucket = None,
            readonly_secret: sm.ISecret = None,
            rds_instance: rds.IDatabaseInstance = None,
            **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, description="Admin Dashboard Frontend - React SPA with CloudFront + Cognito Authentication", **kwargs)
        
        # Trỏ đến dist folder đã build sẵn
        frontend_asset_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "admin-dashboard", "dist"
        )
        
        # ==================== COGNITO USER POOL ====================
        user_pool = cognito.UserPool(
            self, "AdminUserPool",
            user_pool_name="MeetAssist-AdminPool",
            self_sign_up_enabled=False,
            sign_in_aliases=cognito.SignInAliases(email=True),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_lowercase=True,
                require_uppercase=True,
                require_digits=True,
                require_symbols=True
            ),
            removal_policy=RemovalPolicy.DESTROY
        )

        user_pool_domain = user_pool.add_domain(
            "CognitoDomain",
            cognito_domain=cognito.CognitoDomainOptions(
                domain_prefix=f"meetassist-admin-{Stack.of(self).account}"
            )
        )

        # ==================== S3 + CLOUDFRONT ====================
        frontend_bucket = s3.Bucket(
            self, "AdminFrontendBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True
        )

        oai = cloudfront.OriginAccessIdentity(
            self, "AdminOAI",
            comment="OAI for Admin Dashboard"
        )
        
        frontend_bucket.add_to_resource_policy(iam.PolicyStatement(
            actions=["s3:GetObject"],
            resources=[f"{frontend_bucket.bucket_arn}/*"],
            principals=[iam.CanonicalUserPrincipal(
                oai.cloud_front_origin_access_identity_s3_canonical_user_id
            )]
        ))

        distribution = cloudfront.Distribution(
            self, "AdminDistribution",
            default_root_object="index.html",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3Origin(
                    frontend_bucket,
                    origin_access_identity=oai
                ),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                origin_request_policy=cloudfront.OriginRequestPolicy.CORS_S3_ORIGIN,
                response_headers_policy=cloudfront.ResponseHeadersPolicy.CORS_ALLOW_ALL_ORIGINS,
            ),
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_http_status=200,
                    response_page_path="/index.html"
                ),
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path="/index.html"
                ),
            ]
        )
        
        # ==================== COGNITO APP CLIENT ====================
        # Tạo Cognito client SAU KHI đã có CloudFront distribution
        user_pool_client = user_pool.add_client(
            "AdminAppClient",
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(
                    authorization_code_grant=True,
                    implicit_code_grant=False
                ),
                scopes=[
                    cognito.OAuthScope.OPENID,
                    cognito.OAuthScope.EMAIL,
                    cognito.OAuthScope.PROFILE
                ],
                callback_urls=[
                    "http://localhost:3000/callback"  # Placeholder - sẽ được update bởi Custom Resource
                ],
                logout_urls=[
                    "http://localhost:3000/"
                ]
            ),
            supported_identity_providers=[
                cognito.UserPoolClientIdentityProvider.COGNITO
            ],
            generate_secret=False
        )

        # ==================== CUSTOM RESOURCE ====================
        # Tự động update Cognito callback URLs với CloudFront domain
        custom_resource_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "custom_resource"
        )
        
        update_cognito_lambda = lambda_.Function(
            self, "UpdateCognitoCallback",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="update_cognito_callback.handler",
            code=lambda_.Code.from_asset(custom_resource_path),
            timeout=Duration.seconds(60),
            description="Update Cognito User Pool Client callback URLs with CloudFront domain"
        )
        
        update_cognito_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["cognito-idp:UpdateUserPoolClient"],
                resources=[user_pool.user_pool_arn]
            )
        )
        
        update_cognito_cr = CustomResource(
            self, "UpdateCognitoCallbackResource",
            service_token=update_cognito_lambda.function_arn,
            properties={
                "UserPoolId": user_pool.user_pool_id,
                "ClientId": user_pool_client.user_pool_client_id,
                "CloudFrontDomain": distribution.distribution_domain_name
            }
        )
        
        # Đảm bảo Custom Resource chạy SAU khi CloudFront và Cognito client đã tạo xong
        update_cognito_cr.node.add_dependency(distribution)
        update_cognito_cr.node.add_dependency(user_pool_client)
        
        # ==================== GENERATE CONFIG.JSON ====================
        # Tự động tạo config.json với thông tin Cognito + API endpoint
        # Sử dụng Custom Resource Lambda để đọc SSM và tạo config
        
        config_generator_lambda = lambda_.Function(
            self, "ConfigGenerator",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="index.handler",
            code=lambda_.Code.from_inline("""
import json
import boto3
import cfnresponse

def handler(event, context):
    try:
        if event['RequestType'] == 'Delete':
            cfnresponse.send(event, context, cfnresponse.SUCCESS, {})
            return
            
        props = event['ResourceProperties']
        ssm = boto3.client('ssm')
        s3 = boto3.client('s3')
        
        # Đọc API endpoint từ SSM (có thể chưa tồn tại lần deploy đầu)
        try:
            api_endpoint = ssm.get_parameter(Name=props['SsmApiEndpoint'])['Parameter']['Value']
            # Remove trailing slash
            api_endpoint = api_endpoint.rstrip('/')
        except ssm.exceptions.ParameterNotFound:
            api_endpoint = "https://placeholder.execute-api.ap-southeast-1.amazonaws.com/prod"
        
        config = {
            "region": props['Region'],
            "cognitoUserPoolId": props['CognitoUserPoolId'],
            "cognitoClientId": props['CognitoClientId'],
            "cognitoDomain": props['CognitoDomain'],
            "cloudFrontUrl": props['CloudFrontUrl'],
            "apiEndpoint": api_endpoint
        }
        
        # Upload config.json to S3
        s3.put_object(
            Bucket=props['BucketName'],
            Key='config.json',
            Body=json.dumps(config, indent=2),
            ContentType='application/json',
            CacheControl='no-cache, no-store, must-revalidate'
        )
        
        cfnresponse.send(event, context, cfnresponse.SUCCESS, {"ConfigJson": json.dumps(config)})
    except Exception as e:
        print(f"Error: {e}")
        cfnresponse.send(event, context, cfnresponse.FAILED, {"Error": str(e)})
"""),
            timeout=Duration.seconds(30),
            description="Generate config.json for frontend from SSM parameters"
        )
        
        # Grant permissions
        config_generator_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ssm:GetParameter"],
                resources=[f"arn:aws:ssm:{self.region}:{self.account}:parameter{SSM_API_ENDPOINT}"]
            )
        )
        config_generator_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:PutObject"],
                resources=[f"{frontend_bucket.bucket_arn}/config.json"]
            )
        )
        
        # Custom Resource để generate config
        config_generator_cr = CustomResource(
            self, "ConfigGeneratorResource",
            service_token=config_generator_lambda.function_arn,
            properties={
                "Region": self.region,
                "CognitoUserPoolId": user_pool.user_pool_id,
                "CognitoClientId": user_pool_client.user_pool_client_id,
                "CognitoDomain": f"{user_pool_domain.domain_name}.auth.{self.region}.amazoncognito.com",
                "CloudFrontUrl": f"https://{distribution.distribution_domain_name}",
                "BucketName": frontend_bucket.bucket_name,
                "SsmApiEndpoint": SSM_API_ENDPOINT,
                # Force update when redeploying
                "Timestamp": str(hash(f"{user_pool.user_pool_id}{distribution.distribution_domain_name}"))
            }
        )
        
        # Deploy static assets từ dist folder
        bucket_deployment = s3_deployment.BucketDeployment(
            self, "DeployAdminUI",
            sources=[s3_deployment.Source.asset(frontend_asset_path)],
            destination_bucket=frontend_bucket,
            distribution=distribution,
            distribution_paths=["/*"],
            memory_limit=1024,
            prune=False  # Don't delete config.json
        )
        
        # Ensure config is generated AFTER static files are deployed
        # This prevents BucketDeployment from overwriting the config
        config_generator_cr.node.add_dependency(bucket_deployment)

        # ==================== OUTPUTS ====================
        CfnOutput(
            self, "AdminDashboardURL",
            value=f"https://{distribution.distribution_domain_name}",
            description="Admin Dashboard CloudFront URL"
        )

        CfnOutput(
            self, "CloudFrontDistributionDomain",
            value=distribution.distribution_domain_name,
            description="CloudFront distribution domain"
        )

        CfnOutput(
            self, "CognitoUserPoolId",
            value=user_pool.user_pool_id,
            description="Cognito User Pool ID"
        )

        CfnOutput(
            self, "CognitoAppClientId",
            value=user_pool_client.user_pool_client_id,
            description="Cognito App Client ID"
        )

        CfnOutput(
            self, "CognitoDomain",
            value=f"https://{user_pool_domain.domain_name}.auth.{self.region}.amazoncognito.com",
            description="Cognito Hosted UI Domain"
        )

        CfnOutput(
            self, "Region",
            value=self.region,
            description="AWS Region"
        )

        # ==================== EXPOSE PROPERTIES ====================
        self.user_pool = user_pool

        # ==================== COMMENT TẠM - CẦN VPC/RDS ====================
        # Các phần này cần AppStack (VPC, RDS, S3 history bucket, secrets)
        # Sẽ uncomment khi deploy full stack
