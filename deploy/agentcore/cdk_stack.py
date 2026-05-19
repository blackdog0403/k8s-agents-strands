"""AWS CDK stack: AgentCore RCA Agent — Pattern 4 (full VPC isolation).

배포되는 리소스:
- 격리된 VPC (private subnets only, NAT 없음)
- VPC Endpoints: Bedrock, STS, EKS, ECR, CloudWatch Logs, S3
- AgentCore Runtime (VPC ENI 연결)
- IAM Execution Role (deploy/agentcore/iam-execution-policy.json 내용)
- 진단 대상 EKS 클러스터(들)에 대한 SG 규칙

사용:
  cdk synth -c account=123456789012 -c region=us-west-2 -c clusters=prod-us,prod-eu
  cdk deploy

이 파일은 템플릿이다. 실제 배포 전에 cluster names, account, image URI를 채워야 한다.
"""
from __future__ import annotations

import json
from pathlib import Path

import aws_cdk as cdk
from aws_cdk import (
    aws_bedrock as bedrock,  # AgentCore가 별도 패키지면 변경 필요
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_logs as logs,
)
from constructs import Construct


class RcaAgentCoreStack(cdk.Stack):
    """AgentCore Pattern 4 — full VPC isolation."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        target_clusters: list[dict],   # [{"name": "prod-us", "eks_name": "...", "region": "us-west-2"}, ...]
        agent_image_uri: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ----- 1. 격리 VPC (private only) -----
        vpc = ec2.Vpc(
            self, "IsolatedVpc",
            max_azs=2,
            nat_gateways=0,                      # NAT 없음 → 외부 인터넷 접근 차단
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="private-isolated",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                ),
            ],
        )

        # ----- 2. Security Group: AgentCore ENI -----
        sg = ec2.SecurityGroup(
            self, "AgentCoreSg",
            vpc=vpc,
            description="AgentCore RCA Agent ENI security group",
            allow_all_outbound=False,            # 명시적으로 열어줌
        )
        # K8s API server (EKS endpoint)는 443
        sg.add_egress_rule(
            ec2.Peer.any_ipv4(), ec2.Port.tcp(443),
            description="K8s API + AWS service endpoints (over VPC endpoints)",
        )
        sg.add_egress_rule(
            ec2.Peer.any_ipv4(), ec2.Port.tcp(53),
            description="DNS",
        )

        # ----- 3. VPC Endpoints (Pattern 4 핵심) -----
        # 모든 AWS API 호출이 VPC를 떠나지 않도록 한다.
        for service in [
            ec2.InterfaceVpcEndpointAwsService.STS,
            ec2.InterfaceVpcEndpointAwsService.EKS,
            ec2.InterfaceVpcEndpointAwsService.ECR,
            ec2.InterfaceVpcEndpointAwsService.ECR_DOCKER,
            ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS,
            ec2.InterfaceVpcEndpointAwsService("bedrock-runtime"),
            ec2.InterfaceVpcEndpointAwsService("bedrock-agentcore"),
        ]:
            vpc.add_interface_endpoint(
                f"VPCe-{service.short_name}",
                service=service,
                private_dns_enabled=True,
                subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            )

        # S3는 Gateway endpoint가 무료 + 빠름
        vpc.add_gateway_endpoint(
            "VPCe-S3",
            service=ec2.GatewayVpcEndpointAwsService.S3,
        )

        # ----- 4. AgentCore Execution Role -----
        policy_doc = json.loads(
            Path(__file__).parent.joinpath("iam-execution-policy.json").read_text()
        )
        # CDK iam.PolicyDocument로 변환
        execution_role = iam.Role(
            self, "AgentCoreExecutionRole",
            assumed_by=iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
            description="Execution role for RCA Agent on AgentCore Runtime",
        )
        for stmt in policy_doc["Statement"]:
            # Comment 필드 제거
            stmt = {k: v for k, v in stmt.items() if k != "Comment"}
            execution_role.add_to_policy(iam.PolicyStatement.from_json(stmt))

        # ----- 5. CloudWatch Log Group -----
        logs.LogGroup(
            self, "AgentLogGroup",
            log_group_name="/aws/bedrock-agentcore/rca-agent",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )

        # ----- 6. AgentCore Runtime 은 별도 도구로 배포 -----
        # 현재 CDK 에는 AgentCore L2 construct 가 없음.
        # `agentcore deploy` CLI 또는 CloudFormation custom resource 사용 권장.
        cdk.CfnOutput(self, "VpcId", value=vpc.vpc_id)
        cdk.CfnOutput(
            self, "SubnetIds",
            value=",".join(s.subnet_id for s in vpc.isolated_subnets),
        )
        cdk.CfnOutput(self, "SecurityGroupId", value=sg.security_group_id)
        cdk.CfnOutput(self, "ExecutionRoleArn", value=execution_role.role_arn)
        cdk.CfnOutput(
            self, "ClusterRegistryEnv",
            value=json.dumps(target_clusters),
            description="K8S_CLUSTERS 환경변수에 그대로 사용",
        )

        # ----- 7. Resource Policy (Pattern 3 이상 권장) -----
        # AgentCore Runtime 생성 후 별도로 적용해야 함:
        #   aws bedrock-agentcore-control put-agent-runtime-resource-policy \
        #     --agent-runtime-id <id> --policy file://resource-policy-rendered.json
        resource_policy_template = (
            Path(__file__).parent.joinpath("resource-policy.json").read_text()
        )
        cdk.CfnOutput(
            self, "ResourcePolicyTemplate",
            value=resource_policy_template,
            description=(
                "AgentCore Runtime resource policy 템플릿. "
                "ACCOUNT_ID, REGION, AGENT_RUNTIME_ID, VPCE_ID 를 치환한 뒤 "
                "put-agent-runtime-resource-policy API 로 적용."
            ),
        )
