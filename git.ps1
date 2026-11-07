param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$GitArgs
)
python -m scripts.git_shim $GitArgs

