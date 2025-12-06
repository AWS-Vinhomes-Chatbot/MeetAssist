# /*
#  * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#  * SPDX-License-Identifier: MIT-0
#  */

"""
AuthStack - Cognito User Pools cho authentication
Tạo 2 User Pools riêng biệt:
1. Admin User Pool - cho Admin Dashboard
2. Consultant User Pool - cho Consultant Portal
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
        super().__init__(scope, construct_id, description="Authentication Stack - Cognito User Pools for Admin & Consultant", **kwargs)
        
        # ==================== ADMIN USER POOL ====================
        admin_user_pool = cognito.UserPool(
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

        admin_user_pool_domain = admin_user_pool.add_domain(
            "AdminCognitoDomain",
            cognito_domain=cognito.CognitoDomainOptions(
                domain_prefix=f"ma-admin-{Stack.of(self).account}"
            )
        )

        # ==================== CONSULTANT USER POOL ====================
        consultant_user_pool = cognito.UserPool(
            self, "ConsultantUserPool",
            user_pool_name="MeetAssist-ConsultantPool",
            self_sign_up_enabled=False,  # Admin tạo tài khoản cho consultant
            sign_in_aliases=cognito.SignInAliases(email=True),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_lowercase=True,
                require_uppercase=True,
                require_digits=True,
                require_symbols=True
            ),
            # Custom attribute để lưu consultant_id
            custom_attributes={
                "consultant_id": cognito.StringAttribute(mutable=True)
            },
            removal_policy=RemovalPolicy.DESTROY
        )

        consultant_user_pool_domain = consultant_user_pool.add_domain(
            "ConsultantCognitoDomain",
            cognito_domain=cognito.CognitoDomainOptions(
                domain_prefix=f"ma-consultant-{Stack.of(self).account}"
            )
        )

        # ==================== CUSTOMIZE EMAIL TEMPLATES ====================
        # Customize Consultant User Pool email templates
        cfn_consultant_pool = consultant_user_pool.node.default_child
        
        # Custom message template for admin creating user (temporary password)
        cfn_consultant_pool.add_property_override(
            'AdminCreateUserConfig.InviteMessageTemplate',
            {
                'EmailSubject': '[MeetAssist] Tài khoản tư vấn viên của bạn đã được tạo',
                'EmailMessage': '''Xin chào,

Tài khoản tư vấn viên MeetAssist của bạn đã được tạo.

Tên đăng nhập (email): {username}
Mật khẩu tạm thời: {####}

Vui lòng đăng nhập và đổi mật khẩu ngay sau lần đăng nhập đầu tiên.

Trân trọng,
Đội ngũ MeetAssist'''
            }
        )
        
        # Custom verification email template
        cfn_consultant_pool.add_property_override(
            'VerificationMessageTemplate',
            {
                'DefaultEmailOption': 'CONFIRM_WITH_CODE',
                'EmailSubject': '[MeetAssist] Xác nhận địa chỉ email',
                'EmailMessage': '''Xin chào,

Cảm ơn bạn đã sử dụng MeetAssist!

Mã xác nhận của bạn là: {####}

Vui lòng nhập mã này để hoàn tất việc xác thực email.

Nếu bạn không yêu cầu xác nhận này, vui lòng bỏ qua email này.
Trân trọng,
Đội ngũ MeetAssist'''
            }
        )

        # ==================== OUTPUTS - ADMIN ====================
        CfnOutput(
            self, "AdminUserPoolId",
            value=admin_user_pool.user_pool_id,
            description="Admin Cognito User Pool ID"
        )

        CfnOutput(
            self, "AdminCognitoDomainUrl",
            value=f"https://{admin_user_pool_domain.domain_name}.auth.{self.region}.amazoncognito.com",
            description="Admin Cognito Domain URL"
        )

        # ==================== OUTPUTS - CONSULTANT ====================
        CfnOutput(
            self, "ConsultantUserPoolId",
            value=consultant_user_pool.user_pool_id,
            description="Consultant Cognito User Pool ID"
        )

        CfnOutput(
            self, "ConsultantCognitoDomainUrl",
            value=f"https://{consultant_user_pool_domain.domain_name}.auth.{self.region}.amazoncognito.com",
            description="Consultant Cognito Domain URL"
        )

        # ==================== EXPOSE PROPERTIES ====================
        # Admin (backward compatible)
        self.user_pool = admin_user_pool
        self.admin_user_pool = admin_user_pool
        self.user_pool_domain = admin_user_pool_domain
        self.cognito_domain_url = f"{admin_user_pool_domain.domain_name}.auth.{self.region}.amazoncognito.com"
        self.admin_cognito_domain_url = self.cognito_domain_url
        
        # Consultant
        self.consultant_user_pool = consultant_user_pool
        self.consultant_user_pool_domain = consultant_user_pool_domain
        self.consultant_cognito_domain_url = f"{consultant_user_pool_domain.domain_name}.auth.{self.region}.amazoncognito.com"
