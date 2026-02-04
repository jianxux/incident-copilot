# ☁️ AWS CloudWatch Integration

AWS CloudWatch Logs is an alternative to Datadog for fetching error logs during incidents. It's ideal for AWS-native environments.

---

## 📋 Prerequisites

- [ ] AWS account with CloudWatch Logs access
- [ ] IAM user or role with appropriate permissions
- [ ] Services logging to CloudWatch Log Groups

---

## 🔧 Step-by-Step Setup

### Step 1: Create IAM Policy

1. Go to AWS IAM → **Policies** → **Create policy**
2. Use the JSON editor and paste:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "IncidentCopilotCloudWatchLogs",
      "Effect": "Allow",
      "Action": [
        "logs:FilterLogEvents",
        "logs:DescribeLogGroups",
        "logs:DescribeLogStreams",
        "logs:GetLogEvents",
        "logs:StartQuery",
        "logs:GetQueryResults",
        "logs:StopQuery"
      ],
      "Resource": [
        "arn:aws:logs:*:YOUR_ACCOUNT_ID:log-group:*",
        "arn:aws:logs:*:YOUR_ACCOUNT_ID:log-group:*:log-stream:*"
      ]
    }
  ]
}
```

3. Name the policy: `IncidentCopilotCloudWatch`
4. Click **Create policy**

### Step 2: Create IAM User or Role

#### Option A: IAM User (for external deployments)

1. Go to IAM → **Users** → **Add users**
2. Username: `incident-copilot`
3. Select **Access key - Programmatic access**
4. Attach the `IncidentCopilotCloudWatch` policy
5. Complete creation and **save the credentials**

#### Option B: IAM Role (for EC2/ECS/EKS)

1. Go to IAM → **Roles** → **Create role**
2. Trusted entity: **AWS service** (EC2, ECS, or Lambda)
3. Attach the `IncidentCopilotCloudWatch` policy
4. Name: `IncidentCopilotRole`
5. Attach to your compute resource

### Step 3: Configure Environment Variables

```bash
# CloudWatch Configuration
LOG_PROVIDER=cloudwatch
AWS_REGION=us-east-1

# For IAM User (Option A)
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY

# For IAM Role (Option B) - no credentials needed
# boto3 will use instance profile automatically
```

### Step 4: Configure Log Group Mapping

```bash
# Map services to their CloudWatch Log Groups
CLOUDWATCH_LOG_GROUP_MAP='{
  "payments-api": "/aws/lambda/payments,/ecs/payments-production",
  "auth-service": "/aws/ecs/auth-prod",
  "api-gateway": "/aws/api-gateway/production"
}'
```

### Step 5: Restart Incident Copilot

```bash
docker-compose restart
```

---

## ✅ Testing the Integration

### Test AWS Credentials

```bash
# Using AWS CLI
aws sts get-caller-identity

# Expected output:
# {
#   "UserId": "...",
#   "Account": "123456789012",
#   "Arn": "arn:aws:iam::123456789012:user/incident-copilot"
# }
```

### Test Log Group Access

```bash
aws logs describe-log-groups --log-group-name-prefix "/aws/lambda/"
```

### Test Log Query

```bash
aws logs filter-log-events \
  --log-group-name "/aws/lambda/payments" \
  --filter-pattern "ERROR" \
  --start-time $(date -d '15 minutes ago' +%s000) \
  --limit 10
```

---

## 🔐 Required IAM Permissions

### Minimum Permissions

| Permission | Purpose |
|------------|---------|
| `logs:FilterLogEvents` | Query logs with patterns |
| `logs:DescribeLogGroups` | List available log groups |
| `logs:DescribeLogStreams` | List log streams |
| `logs:GetLogEvents` | Fetch log entries |

### For CloudWatch Logs Insights

| Permission | Purpose |
|------------|---------|
| `logs:StartQuery` | Start Insights query |
| `logs:GetQueryResults` | Get query results |
| `logs:StopQuery` | Cancel running queries |

### Restricted Policy Example

For tighter security, restrict to specific log groups:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "logs:FilterLogEvents",
        "logs:GetLogEvents"
      ],
      "Resource": [
        "arn:aws:logs:us-east-1:123456789012:log-group:/aws/lambda/payments*",
        "arn:aws:logs:us-east-1:123456789012:log-group:/ecs/production*"
      ]
    }
  ]
}
```

---

## 🔑 Environment Variables

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `LOG_PROVIDER` | ✅ | Set to `cloudwatch` | `cloudwatch` |
| `AWS_REGION` | ✅ | AWS region | `us-east-1` |
| `AWS_ACCESS_KEY_ID` | ⚡ | Access key (if not using role) | `AKIAIOSFODNN7...` |
| `AWS_SECRET_ACCESS_KEY` | ⚡ | Secret key (if not using role) | `wJalrXUtnFEMI...` |
| `CLOUDWATCH_LOG_GROUP_MAP` | ⚡ | Service to log group mapping | `{"svc": "/group"}` |

---

## 📂 Log Group Mapping

### Default Behavior

Without explicit mapping, Incident Copilot tries these patterns:
- `/aws/lambda/{service-name}`
- `/ecs/{service-name}`
- `/aws/ecs/{service-name}`
- `/application/{service-name}`

### Custom Mapping

For specific log groups:

```bash
CLOUDWATCH_LOG_GROUP_MAP='{
  "payments-api": "/aws/lambda/payments-prod",
  "auth-service": "/ecs/auth-service-prod,/aws/ecs/auth-workers",
  "frontend": "/aws/amplify/d1234567890"
}'
```

**Multiple log groups:** Separate with commas (all will be queried).

### Common Log Group Patterns

| AWS Service | Log Group Pattern |
|-------------|-------------------|
| Lambda | `/aws/lambda/{function-name}` |
| ECS | `/ecs/{service-name}` or `/aws/ecs/{cluster}/{service}` |
| API Gateway | `/aws/api-gateway/{api-id}/{stage}` |
| EKS | `/aws/eks/{cluster-name}/containers` |
| Amplify | `/aws/amplify/{app-id}` |
| Custom | `/application/{service-name}` |

---

## 📊 Log Query Configuration

### Default Query Pattern

Incident Copilot searches for errors using:

```
?ERROR ?Exception ?CRITICAL ?FATAL
```

This matches common error patterns in logs.

### Time Range

- **Default:** Last 15 minutes
- Adjusts based on incident timing

### Log Limit

- Fetches up to **100 log entries**
- Most recent entries prioritized

---

## 🐛 Troubleshooting

### "Access Denied" Error

**Symptoms:** HTTP 403 / AccessDeniedException

**Checks:**
```bash
# Verify permissions
aws logs describe-log-groups
```

**Solutions:**
- Add required IAM permissions
- Check policy is attached to user/role
- Verify resource ARNs in policy

### "Log Group Not Found"

**Symptoms:** No logs returned for a service

**Checks:**
```bash
# List available log groups
aws logs describe-log-groups --query 'logGroups[*].logGroupName'
```

**Solutions:**
- Verify log group name is exact
- Check `CLOUDWATCH_LOG_GROUP_MAP` mapping
- Ensure logs are being written to CloudWatch

### "No Credentials" Error

**Symptoms:** Unable to locate credentials

**Checks:**
```bash
# Verify credentials are set
echo $AWS_ACCESS_KEY_ID
aws sts get-caller-identity
```

**Solutions:**
- Set credentials in `.env` or environment
- For EC2/ECS, attach IAM role to instance
- Check credential file: `~/.aws/credentials`

### Slow Queries

**Symptoms:** Context cards take >10 seconds

**Cause:** Large log groups or complex queries

**Solutions:**
- Use CloudWatch Logs Insights (more efficient)
- Reduce time range
- Add more specific log group mapping

### Rate Limiting

**Symptoms:** Throttling errors

**Info:** CloudWatch API limits:
- `FilterLogEvents`: 5 transactions/second
- `GetLogEvents`: 10 transactions/second

**Solutions:**
- Implement exponential backoff (built-in)
- Reduce concurrent queries
- Request limit increase via AWS Support

---

## 🔄 Multi-Region Setup

For services across multiple AWS regions:

```bash
# Primary region
AWS_REGION=us-east-1

# Multi-region mapping (future feature)
# CLOUDWATCH_REGION_MAP='{
#   "payments-api": "us-east-1",
#   "eu-service": "eu-west-1"
# }'
```

Currently, all queries go to the configured `AWS_REGION`.

---

## 🔐 Security Best Practices

### Use IAM Roles When Possible

IAM roles are more secure than access keys:
- No credential rotation needed
- Automatically scoped to the resource
- No risk of key exposure

### Restrict Log Group Access

Don't grant access to all log groups:

```json
{
  "Resource": [
    "arn:aws:logs:us-east-1:123456789012:log-group:/ecs/production-*",
    "arn:aws:logs:us-east-1:123456789012:log-group:/aws/lambda/prod-*"
  ]
}
```

### Use VPC Endpoints

For private connectivity to CloudWatch:

1. Create VPC endpoint for `logs.{region}.amazonaws.com`
2. Route traffic through your VPC
3. No internet access required

---

## 📚 Additional Resources

- [CloudWatch Logs Documentation](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/)
- [IAM Policies for CloudWatch](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/iam-identity-based-access-control-cwl.html)
- [CloudWatch Logs Insights](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/AnalyzingLogData.html)
- [Datadog Integration](./datadog.md) (alternative)
- [Splunk Integration](./splunk.md) (alternative)

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md) or open an issue on GitHub.*
