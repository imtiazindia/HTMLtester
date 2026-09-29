"""Reproducible AWS deployment. Run from repository root with an authenticated AWS profile.
Phases: bootstrap, build, deploy, web. State is local and excluded from Git.
"""
import io, json, os, pathlib, secrets, subprocess, sys, time, zipfile
import boto3

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_DIR = ROOT/'.deploy'
STATE_DIR.mkdir(exist_ok=True)
STATE_FILE = STATE_DIR/'state.json'
state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
region = 'ap-south-1'
session = boto3.Session(region_name=region)
account = session.client('sts').get_caller_identity()['Account']
cf = session.client('cloudformation')

def save(): STATE_FILE.write_text(json.dumps(state, indent=2))
def ref(name): return {'Ref':name}
def att(name, key): return {'Fn::GetAtt':[name,key]}
def sub(value): return {'Fn::Sub':value}
def trust(service): return {'Version':'2012-10-17','Statement':[{'Effect':'Allow','Principal':{'Service':service},'Action':'sts:AssumeRole'}]}
def policy(name, statements): return {'PolicyName':name,'PolicyDocument':{'Version':'2012-10-17','Statement':statements}}
def allow(actions, resources): return {'Effect':'Allow','Action':actions,'Resource':resources}
def stack(name, resources, outputs):
    args=dict(StackName=name, TemplateBody=json.dumps({'AWSTemplateFormatVersion':'2010-09-09','Resources':resources,'Outputs':outputs}), Capabilities=['CAPABILITY_IAM'])
    try:
        cf.describe_stacks(StackName=name)
        try: cf.update_stack(**args)
        except cf.exceptions.ClientError as e:
            if 'No updates' not in str(e): raise
            return {o['OutputKey']:o['OutputValue'] for o in cf.describe_stacks(StackName=name)['Stacks'][0]['Outputs']}
        waiter='stack_update_complete'
    except cf.exceptions.ClientError as e:
        if 'does not exist' not in str(e): raise
        cf.create_stack(**args)
        waiter='stack_create_complete'
    print('Waiting for', name, flush=True)
    cf.get_waiter(waiter).wait(StackName=name, WaiterConfig={'Delay':10,'MaxAttempts':120})
    return {o['OutputKey']:o['OutputValue'] for o in cf.describe_stacks(StackName=name)['Stacks'][0]['Outputs']}

def bootstrap():
    resources = {
      'Artifacts': {'Type':'AWS::S3::Bucket','Properties':{'PublicAccessBlockConfiguration':{'BlockPublicAcls':True,'BlockPublicPolicy':True,'IgnorePublicAcls':True,'RestrictPublicBuckets':True},'LifecycleConfiguration':{'Rules':[{'Id':'build-cleanup','Status':'Enabled','ExpirationInDays':7}]}}},
      'Repository': {'Type':'AWS::ECR::Repository','Properties':{'RepositoryName':'htmltester-worker','ImageScanningConfiguration':{'ScanOnPush':True},'RepositoryPolicyText':{'Version':'2012-10-17','Statement':[{'Sid':'LambdaImageRead','Effect':'Allow','Principal':{'Service':'lambda.amazonaws.com'},'Action':['ecr:BatchGetImage','ecr:GetDownloadUrlForLayer'],'Condition':{'ArnLike':{'aws:SourceArn':sub('arn:aws:lambda:${AWS::Region}:${AWS::AccountId}:function:htmltester-worker')}}}]},'LifecyclePolicy':{'LifecyclePolicyText':json.dumps({'rules':[{'rulePriority':1,'description':'Keep two worker images','selection':{'tagStatus':'any','countType':'imageCountMoreThan','countNumber':2},'action':{'type':'expire'}}]})}}},
      'BuildRole': {'Type':'AWS::IAM::Role','Properties':{'AssumeRolePolicyDocument':trust('codebuild.amazonaws.com'),'Policies':[policy('build',[
        allow(['logs:CreateLogGroup','logs:CreateLogStream','logs:PutLogEvents'],sub('arn:aws:logs:${AWS::Region}:${AWS::AccountId}:log-group:/aws/codebuild/htmltester-build*')),
        allow(['s3:GetObject'],sub('${Artifacts.Arn}/*')), allow(['ecr:GetAuthorizationToken'],'*'),
        allow(['ecr:BatchCheckLayerAvailability','ecr:InitiateLayerUpload','ecr:UploadLayerPart','ecr:CompleteLayerUpload','ecr:PutImage','ecr:BatchGetImage','ecr:GetDownloadUrlForLayer'],att('Repository','Arn'))])]}},
      'Builder': {'Type':'AWS::CodeBuild::Project','Properties':{'Name':'htmltester-build','ServiceRole':att('BuildRole','Arn'),'Artifacts':{'Type':'NO_ARTIFACTS'},'TimeoutInMinutes':45,
        'Environment':{'Type':'LINUX_CONTAINER','ComputeType':'BUILD_GENERAL1_MEDIUM','Image':'aws/codebuild/standard:7.0','PrivilegedMode':True,'EnvironmentVariables':[{'Name':'IMAGE_URI','Value':att('Repository','RepositoryUri')}]},
        'Source':{'Type':'S3','Location':sub('${Artifacts}/source.zip'),'BuildSpec':json.dumps({'version':0.2,'phases':{'pre_build':{'commands':['aws ecr get-login-password --region "$AWS_DEFAULT_REGION" | docker login --username AWS --password-stdin "${IMAGE_URI%/*}"']},'build':{'commands':['docker build -f backend/Dockerfile -t "$IMAGE_URI:latest" .']},'post_build':{'commands':['docker push "$IMAGE_URI:latest"']}}})}}}}
    state.update(stack('HTMLtesterBuild', resources, {'Artifacts':{'Value':ref('Artifacts')},'Repository':{'Value':att('Repository','RepositoryUri')}}))
    save()

def build():
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as z:
        for f in (ROOT/'backend').glob('*'):
            if f.is_file(): z.write(f, 'backend/'+f.name)
    session.client('s3').put_object(Bucket=state['Artifacts'],Key='source.zip',Body=buffer.getvalue())
    job=session.client('codebuild').start_build(projectName='htmltester-build')['build']
    state['buildId']=job['id']; save()
    print('Started build:',job['id'])

def deploy():
    build=session.client('codebuild').batch_get_builds(ids=[state['buildId']])['builds'][0]
    if build['buildStatus']!='SUCCEEDED': raise RuntimeError('Container build is '+build['buildStatus'])
    digest=session.client('ecr').describe_images(repositoryName='htmltester-worker',imageIds=[{'imageTag':'latest'}])['imageDetails'][0]['imageDigest']
    s3=session.client('s3')
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as z:
        for name in ('api.py','telemetry.py'): z.write(ROOT/'backend'/name,name)
    api_key='api-'+str(int(time.time()))+'.zip'
    s3.put_object(Bucket=state['Artifacts'],Key=api_key,Body=buffer.getvalue())
    amplify=session.client('amplify')
    if 'amplifyId' not in state:
        app=amplify.create_app(name='HTMLtester',platform='WEB',customRules=[{'source':'/<*>','target':'/index.html','status':'404-200'}])['app']
        state['amplifyId']=app['appId']; state['webUrl']='https://main.'+app['defaultDomain']; save()
        amplify.create_branch(appId=app['appId'],branchName='main',stage='PRODUCTION',enableAutoBuild=False)
    origin=state['webUrl']
    resources={
      'Data':{'Type':'AWS::S3::Bucket','Properties':{'PublicAccessBlockConfiguration':{'BlockPublicAcls':True,'BlockPublicPolicy':True,'IgnorePublicAcls':True,'RestrictPublicBuckets':True},'CorsConfiguration':{'CorsRules':[{'AllowedOrigins':[origin,'http://localhost:5173'],'AllowedMethods':['GET','POST'],'AllowedHeaders':['*'],'MaxAge':300}]},'LifecycleConfiguration':{'Rules':[{'Id':'temporary-files','Status':'Enabled','ExpirationInDays':1}]}}},
      'Logs':{'Type':'AWS::S3::Bucket','Properties':{'PublicAccessBlockConfiguration':{'BlockPublicAcls':True,'BlockPublicPolicy':True,'IgnorePublicAcls':True,'RestrictPublicBuckets':True}}},
      'Pool':{'Type':'AWS::Cognito::UserPool','Properties':{'UserPoolName':'HTMLtester','AdminCreateUserConfig':{'AllowAdminCreateUserOnly':True},'Policies':{'PasswordPolicy':{'MinimumLength':12,'RequireLowercase':True,'RequireUppercase':True,'RequireNumbers':True,'RequireSymbols':True}},'UsernameConfiguration':{'CaseSensitive':False}}},
      'Client':{'Type':'AWS::Cognito::UserPoolClient','Properties':{'UserPoolId':ref('Pool'),'ClientName':'htmltester-web','GenerateSecret':False,'ExplicitAuthFlows':['ALLOW_USER_PASSWORD_AUTH','ALLOW_REFRESH_TOKEN_AUTH'],'PreventUserExistenceErrors':'ENABLED','AccessTokenValidity':1,'IdTokenValidity':1,'TokenValidityUnits':{'AccessToken':'hours','IdToken':'hours'}}},
      'DeadQueue':{'Type':'AWS::SQS::Queue','Properties':{'MessageRetentionPeriod':86400,'SqsManagedSseEnabled':True}},
      'Queue':{'Type':'AWS::SQS::Queue','Properties':{'VisibilityTimeout':5100,'MessageRetentionPeriod':86400,'SqsManagedSseEnabled':True,'RedrivePolicy':{'deadLetterTargetArn':att('DeadQueue','Arn'),'maxReceiveCount':1}}},
      'WorkerRole':{'Type':'AWS::IAM::Role','Properties':{'AssumeRolePolicyDocument':trust('lambda.amazonaws.com'),'ManagedPolicyArns':['arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole'],'Policies':[policy('files',[allow(['s3:ListBucket'],att('Logs','Arn')),allow(['s3:GetObject','s3:PutObject'],[sub('${Data.Arn}/*'),sub('${Logs.Arn}/*')]),allow(['sqs:ReceiveMessage','sqs:DeleteMessage','sqs:GetQueueAttributes'],att('Queue','Arn'))])]}},
      'Worker':{'Type':'AWS::Lambda::Function','Properties':{'FunctionName':'htmltester-worker','PackageType':'Image','Code':{'ImageUri':state['Repository']+'@'+digest},'Role':att('WorkerRole','Arn'),'MemorySize':3008,'Timeout':840,'EphemeralStorage':{'Size':2048},'Environment':{'Variables':{'DATA_BUCKET':ref('Data'),'LOG_BUCKET':ref('Logs')}}}},
      'WorkerQueue':{'Type':'AWS::Lambda::EventSourceMapping','Properties':{'FunctionName':ref('Worker'),'EventSourceArn':att('Queue','Arn'),'BatchSize':1,'ScalingConfig':{'MaximumConcurrency':2}}},
      'ApiRole':{'Type':'AWS::IAM::Role','Properties':{'AssumeRolePolicyDocument':trust('lambda.amazonaws.com'),'ManagedPolicyArns':['arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole'],'Policies':[policy('api',[allow(['s3:ListBucket'],att('Logs','Arn')),allow(['s3:GetObject','s3:PutObject'],[sub('${Data.Arn}/*'),sub('${Logs.Arn}/*')]),allow(['sqs:SendMessage'],att('Queue','Arn'))])]}},
      'Handler':{'Type':'AWS::Lambda::Function','Properties':{'FunctionName':'htmltester-api','Runtime':'python3.12','Handler':'api.handler','Role':att('ApiRole','Arn'),'Code':{'S3Bucket':state['Artifacts'],'S3Key':api_key},'Timeout':20,'MemorySize':256,'Environment':{'Variables':{'DATA_BUCKET':ref('Data'),'LOG_BUCKET':ref('Logs'),'QUEUE_URL':ref('Queue')}}}},
      'Api':{'Type':'AWS::ApiGatewayV2::Api','Properties':{'Name':'HTMLtester','ProtocolType':'HTTP','CorsConfiguration':{'AllowOrigins':[origin,'http://localhost:5173'],'AllowMethods':['GET','POST','OPTIONS'],'AllowHeaders':['authorization','content-type']}}},
      'Authorizer':{'Type':'AWS::ApiGatewayV2::Authorizer','Properties':{'ApiId':ref('Api'),'AuthorizerType':'JWT','IdentitySource':['$request.header.Authorization'],'Name':'Cognito','JwtConfiguration':{'Audience':[ref('Client')],'Issuer':sub('https://cognito-idp.${AWS::Region}.amazonaws.com/${Pool}')}}},
      'Integration':{'Type':'AWS::ApiGatewayV2::Integration','Properties':{'ApiId':ref('Api'),'IntegrationType':'AWS_PROXY','IntegrationUri':att('Handler','Arn'),'PayloadFormatVersion':'2.0'}},
      'Stage':{'Type':'AWS::ApiGatewayV2::Stage','Properties':{'ApiId':ref('Api'),'StageName':'$default','AutoDeploy':True,'DefaultRouteSettings':{'ThrottlingBurstLimit':5,'ThrottlingRateLimit':2}}},
      'Permission':{'Type':'AWS::Lambda::Permission','Properties':{'Action':'lambda:InvokeFunction','FunctionName':ref('Handler'),'Principal':'apigateway.amazonaws.com','SourceArn':sub('arn:aws:execute-api:${AWS::Region}:${AWS::AccountId}:${Api}/*')}}}
    for name,route in [('Upload','POST /uploads'),('Start','POST /jobs'),('Status','GET /jobs/{id}'),('SaveLog','POST /jobs/{id}/log'),('ListLogs','GET /logs'),('ReadLog','GET /logs/{id}')]:
        resources[name]={'Type':'AWS::ApiGatewayV2::Route','Properties':{'ApiId':ref('Api'),'RouteKey':route,'Target':sub('integrations/${Integration}'),'AuthorizationType':'JWT','AuthorizerId':ref('Authorizer')}}
    for name,function in [('ApiLog','htmltester-api'),('WorkerLog','htmltester-worker')]:
        resources[name]={'Type':'AWS::Logs::LogGroup','Properties':{'LogGroupName':'/aws/lambda/'+function,'RetentionInDays':7}}
    state.update(stack('HTMLtesterApp',resources,{'apiUrl':{'Value':att('Api','ApiEndpoint')},'userPoolId':{'Value':ref('Pool')},'clientId':{'Value':ref('Client')},'dataBucket':{'Value':ref('Data')},'logBucket':{'Value':ref('Logs')}}));save()
    cognito=session.client('cognito-idp')
    try: cognito.admin_get_user(UserPoolId=state['userPoolId'],Username='imtiaz')
    except cognito.exceptions.UserNotFoundException:
        password=secrets.token_urlsafe(22)+'aA1!'
        cognito.admin_create_user(UserPoolId=state['userPoolId'],Username='imtiaz',MessageAction='SUPPRESS')
        cognito.admin_set_user_password(UserPoolId=state['userPoolId'],Username='imtiaz',Password=password,Permanent=True)
        credentials=pathlib.Path.home()/'.codex'/'htmltester-login.json'
        credentials.write_text(json.dumps({'url':origin,'username':'imtiaz','password':password},indent=2))
        print('Login saved locally:',credentials)
    (ROOT/'public/config.json').write_text(json.dumps({k:state[k] for k in ('apiUrl','clientId')} | {'region':region}))
    print('Application infrastructure ready:',origin)

def web():
    config = json.loads((ROOT/'public/config.json').read_text())
    if not config.get('apiUrl') or not config.get('clientId'):
        raise RuntimeError('Run the deploy phase successfully before publishing the frontend.')
    subprocess.run(['npm.cmd' if os.name=='nt' else 'npm','run','build'],cwd=ROOT,check=True)
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as z:
        for f in (ROOT/'dist').rglob('*'):
            if f.is_file(): z.write(f,f.relative_to(ROOT/'dist').as_posix())
    amplify=session.client('amplify')
    amplify.update_app(appId=state['amplifyId'],customHeaders='''customHeaders:
  - pattern: '**'
    headers:
      - key: X-Content-Type-Options
        value: nosniff
      - key: Referrer-Policy
        value: no-referrer
      - key: X-Frame-Options
        value: DENY
  - pattern: '/config.json'
    headers:
      - key: Cache-Control
        value: no-store
''')
    job=amplify.create_deployment(appId=state['amplifyId'],branchName='main')
    import urllib.request
    urllib.request.urlopen(urllib.request.Request(job['zipUploadUrl'],data=buffer.getvalue(),method='PUT')).read()
    amplify.start_deployment(appId=state['amplifyId'],branchName='main',jobId=job['jobId'])
    state['webJob']=job['jobId'];save();print('Web deployment started:',state['webUrl'])

if __name__=='__main__':
    {'bootstrap':bootstrap,'build':build,'deploy':deploy,'web':web}[sys.argv[1]]()
