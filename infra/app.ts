#!/usr/bin/env node

import * as cdk from 'aws-cdk-lib';
import { ApiStack } from './script';

const app = new cdk.App();

new ApiStack(app, 'FastApiStack');