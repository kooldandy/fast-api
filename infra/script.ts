import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";

import * as lambda from "aws-cdk-lib/aws-lambda";
import * as apigateway from "aws-cdk-lib/aws-apigateway";
import * as rds from "aws-cdk-lib/aws-rds";
import * as ec2 from "aws-cdk-lib/aws-ec2";

export class ApiStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const vpc = new ec2.Vpc(this, "AppVpc", {
      maxAzs: 2,
      natGateways: 0,
      subnetConfiguration: [
        {
          name: "public",
          subnetType: ec2.SubnetType.PUBLIC,
          cidrMask: 24,
        },
        {
          name: "private",
          subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
          cidrMask: 24,
        },
      ],
    });

    const dbPassword = this.node.tryGetContext("dbPassword");

    const db = new rds.DatabaseInstance(this, "PostgresDb", {
      engine: rds.DatabaseInstanceEngine.postgres({
        version: rds.PostgresEngineVersion.VER_15,
      }),

      instanceType: ec2.InstanceType.of(
        ec2.InstanceClass.T3,
        ec2.InstanceSize.MICRO,
      ),

      allocatedStorage: 20,
      maxAllocatedStorage: 20,

      multiAz: false,

      backupRetention: cdk.Duration.days(1),

      credentials: rds.Credentials.fromPassword(
        "postgres",
        cdk.SecretValue.unsafePlainText(dbPassword),
      ),

      databaseName: "appdb",

      vpc,

      vpcSubnets: {
        subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
      },

      publiclyAccessible: false,

      deletionProtection: false,

      removalPolicy: cdk.RemovalPolicy.DESTROY,

      deleteAutomatedBackups: true,
    });

    const fastApiLambda = new lambda.Function(this, "FastApiLambda", {
      runtime: lambda.Runtime.PYTHON_3_12,

      handler: "main.handler",

      code: lambda.Code.fromAsset("../lambda"),

      memorySize: 512,

      timeout: cdk.Duration.seconds(30),

      environment: {
        DB_HOST: db.dbInstanceEndpointAddress,
        DB_PORT: "5432",
        DB_ID: "postgres", // This matches your master username
        DB_PASSWORD: dbPassword, // Pulled from your GitHub DB_PASSWORD secret via context
        DB_NAME: "appdb",
        CORS_ORIGINS: '["*"]', // For testing, allow all origins. Update this in production for better security.
        AUTH0_DOMAIN: this.node.tryGetContext("auth0Domain"), // Pulled from your GitHub AUTH0_DOMAIN secret via context
        AUTH0_AUDIENCE: this.node.tryGetContext("auth0Audience"), // Pulled from your GitHub AUTH0_AUDIENCE secret via context
      },

      vpc,
      vpcSubnets: {
        subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
      },
    });

    db.connections.allowDefaultPortFrom(fastApiLambda);

    const api = new apigateway.LambdaRestApi(this, "FastApiGateway", {
      handler: fastApiLambda,
    });

    new cdk.CfnOutput(this, "ApiUrl", {
      value: api.url,
    });
  }
}
