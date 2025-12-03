# /*
#  * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#  * SPDX-License-Identifier: MIT-0
#  */

"""
AuthStack - Cognito User Pool cho authentication
Chỉ tạo User Pool và Domain, KHÔNG tạo Client (vì cần CloudFront domain)
"""

from aws_cdk import (
    aws_cognito as cognito,
    Stack,
    CfnOutput,
    RemovalPolicy
)
from constructs import Construct


class AuthStack(Stack):

    def __init__(
            self,
            scope: Construct,
            construct_id: str,
            **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, description="Authentication Stack - Cognito User Pool", **kwargs)
        
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

        # ==================== OUTPUTS ====================
        CfnOutput(
            self, "CognitoUserPoolId",
            value=user_pool.user_pool_id,
            description="Cognito User Pool ID"
        )

        CfnOutput(
            self, "CognitoDomainName",
            value=user_pool_domain.domain_name,
            description="Cognito Domain Name"
        )
        
        CfnOutput(
            self, "CognitoDomainUrl",
            value=f"https://{user_pool_domain.domain_name}.auth.{self.region}.amazoncognito.com",
            description="Cognito Domain URL"
        )

        # ==================== EXPOSE PROPERTIES ====================
        self.user_pool = user_pool
        self.user_pool_domain = user_pool_domain
        self.cognito_domain_url = f"{user_pool_domain.domain_name}.auth.{self.region}.amazoncognito.com"
