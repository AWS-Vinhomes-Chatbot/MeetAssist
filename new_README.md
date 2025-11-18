# Lưu Facebook App ID
aws ssm put-parameter \
  --name "/meetassist/facebook/app_id" \
  --value "123456789012345" \
  --type String

# Lưu Facebook App Secret (encrypted)
aws ssm put-parameter \
  --name "/meetassist/facebook/app_secret" \
  --value "abc123def456..." \
  --type SecureString

# ma facebook
# secret:
EAAU7ZC4FkKAEBP3I7YwDZAwmhj5f7JsAfTB8nS5xbnZAlSX2LCx5HH8AkjzgjdnkMCxyoUKW5hiVW4UlSb2bRqV5EZApwCwR4Rnc0JnR9Vfo264ZBYUltWZC7AP2hVZA65jJTqmE68G9JHZBeGTiZCTUUmUWvsoNkx4hYQWNjaGgco3uEOqiPadQBT1tNM0NlSgXDCGUgBiD4
# id:
103575692353867