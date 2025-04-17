# duplicity-utility
Utility Tool for Duplicity backup solution

## Dependencies
Fedora/RHEL: `librsync duplicity python3-pyyaml python3-colorama python3-dateutil python3-fasteners python3-future python3-paramiko python3-boto3`

## Configuration
### Duplicity Environment: /usr/local/etc/duplicity_env.sh
```
export AWS_ACCESS_KEY_ID="xxxxxx"
export AWS_SECRET_ACCESS_KEY="xxxxxxx"
export AWS_S3_BUCKET="my-bucket-name"
export AWS_S3_ENDPOINT="https://s3.amazonaws.com"
export PASSPHRASE="PASSWORD"
export DUPLICITY_ARCHIVE_DIR="/var/cache/duplicity"
export DUPLICITY_OPTIONS="--s3-endpoint-url ${AWS_S3_ENDPOINT} --archive-dir=${DUPLICITY_ARCHIVE_DIR}"
```
### Backup jobs settings: /usr/local/etc/duplicity_backup_jobs.yaml
```YAML
---
destination: 'boto3+s3://my-bucket-name/'
jobs:
  'myhostname-domain-tld__tmp':
    source: '/tmp'
    retention: 5
    type: 'incremental'
    abort_on_pre_script_failure: true
    encrypt: true
    compress: true
  'myhostname-domain-tld__dump':
    source: '/dump'
    retention: 1
    schedule:
      minute: 0
      hour: 14
    type: 'full'
    encrypt: false
    compress: true
    exclude:
      - '**.log'
      - '**.snapshots/'
  'myhostname-domain-tld__var_log':
    source: '/var/log'
    retention: 3
    schedule:
      minute: 30
    fullifolder: 1
    pre_script: [/usr/local/bin/script.sh, arg1]
    abort_on_pre_script_failure: true
    encrypt: false
    compress: true
    exclude:
      - '**'
    include:
      - '**/audit/**'
```

## Usage
```
usage: duplicity-util [-h] [--job JOB] [-a] [--restore-path RESTORE_PATH] [--path-to-restore PATH_TO_RESTORE] [-t TIME] [--nice NICE] [--ionice-class {1,2,3}]
                   [--ionice-level {0,1,2,3,4,5,6,7}] [--progress] [--force]
                   {list,restore,backup,status,content,cleanup}
```
### List configured backup jobs (print YAML conf)
```
duplicity-util list
```
### Show content of a backup
```
duplicity-util content --job <job_id> [-t <TIME>]
```
### Trigger backup 
```
duplicity-util backup --job <job_id>
```
### Show backup collection status 
```
duplicity-util status --job <job_id>
```
### Restore a backup 
```
duplicity-util restore --job <job_id> [-t <TIME> --restore-path <RESTORE_PATH> --path-to-restore <PATH_TO_RESTORE>]
```
### TIME_FORMAT (-t <TIME>)
```
1. ISO datetime: '2002-01-25T07:00:00+02:00'
2. Interval: '<number>(s|m|h|D|W|M|Y)' (can be combined), e.g., '1h30m'
   s: seconds, m: minutes, h: hours
   D: days, W: weeks, M: months, Y: years
3. Date formats:
   - YYYY/MM/DD  (e.g., 2002/3/5)
   - YYYY-MM-DD  (e.g., 2002-3-5)
   - MM/DD/YYYY  (e.g., 3/5/2002)
   - MM-DD-YYYY  (e.g., 03-05-2002)
```