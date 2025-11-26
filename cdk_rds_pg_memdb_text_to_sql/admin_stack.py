# /*
#  * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#  * SPDX-License-Identifier: MIT-0
#  */

import os

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
    CustomResource,
    Stack,
    Duration,
    BundlingOptions,
    CfnOutput,
    RemovalPolicy
)
from constructs import Construct

class AdminStack(Stack):

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
        super().__init__(scope, construct_id, **kwargs)
        
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
        
        s3_deployment.BucketDeployment(
            self, "DeployAdminUI",
            sources=[s3_deployment.Source.asset(frontend_asset_path)],
            destination_bucket=frontend_bucket,
            distribution=distribution,
            distribution_paths=["/*"],
            memory_limit=1024
        )

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
