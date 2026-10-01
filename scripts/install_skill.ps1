<#
.SYNOPSIS
  Installer for the Databricks Native Agent Development Skill (`databricks-native-agent`) on Windows.

.DESCRIPTION
  PowerShell counterpart of install_skill.sh. Needs neither bash/Git Bash nor administrator rights:
  by default it creates a directory junction (no privileges required, local drives only) and falls back to
  copying the skill when a junction is not possible (-Copy forces a copy).

    default             -> %USERPROFILE%\.gemini\antigravity-cli\skills   (Antigravity / Gemini CLI, global)
    -Project            -> .\.agents\skills                               (Antigravity / Gemini CLI, this project)
    -Claude             -> %USERPROFILE%\.claude\skills                   (Claude Code, global)
    -Claude -Project    -> .\.claude\skills                               (Claude Code, this project)

  Claude Code discovers the skill from SKILL.md; no CLAUDE.md is installed or needed.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\.agents\skills\databricks-native-agent\scripts\install_skill.ps1 -Claude -Project
#>
[CmdletBinding()]
param(
    [switch]$Project,
    [switch]$Global,
    [switch]$Claude,
    [switch]$Copy
)

$ErrorActionPreference = 'Stop'

$SkillName = 'databricks-native-agent'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SkillDir  = (Resolve-Path (Join-Path $ScriptDir '..')).Path

Write-Host ('=' * 60)
Write-Host "Installing Databricks Native Agent Skill: $SkillName"
Write-Host "Source: $SkillDir"
Write-Host ('=' * 60)

if ($Claude) {
    $GlobalDir  = Join-Path $env:USERPROFILE '.claude\skills'
    $ProjectDir = Join-Path (Get-Location).Path '.claude\skills'
} else {
    $GlobalDir  = Join-Path $env:USERPROFILE '.gemini\antigravity-cli\skills'
    $ProjectDir = Join-Path (Get-Location).Path '.agents\skills'
}
$TargetRoot = if ($Project -and -not $Global) { $ProjectDir } else { $GlobalDir }
$Target = Join-Path $TargetRoot $SkillName

$agent = if ($Claude) { 'claude' } else { 'gemini' }
$scope = if ($Project -and -not $Global) { 'project' } else { 'global' }
Write-Host "[*] Installation mode: $agent/$scope"
Write-Host "[*] Target directory: $Target"

New-Item -ItemType Directory -Force -Path $TargetRoot | Out-Null

if (Test-Path -LiteralPath $Target) {
    Write-Host '[!] Target skill directory or link already exists. Updating...'
    $item = Get-Item -LiteralPath $Target -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        # Remove the junction/symlink itself. Do NOT use Remove-Item -Recurse: on Windows PowerShell 5.1 it
        # can delete the *target's* contents.
        cmd /c rmdir "`"$Target`"" | Out-Null
    } else {
        Remove-Item -LiteralPath $Target -Recurse -Force
    }
}

$linked = $false
if (-not $Copy) {
    try {
        New-Item -ItemType Junction -Path $Target -Target $SkillDir | Out-Null
        $linked = $true
        Write-Host "[OK] Linked (junction) $SkillDir -> $Target"
    } catch {
        Write-Host "[!] Could not create a junction ($($_.Exception.Message)); falling back to copy."
    }
}
if (-not $linked) {
    Copy-Item -LiteralPath $SkillDir -Destination $Target -Recurse -Force
    Write-Host "[OK] Copied $SkillDir -> $Target (re-run this installer to update the copy)"
}

# Verify prerequisites (Windows launcher is `py -3` or `python`; `python3` usually does not exist)
Write-Host ''
Write-Host '[*] Running environment verification...'
$py = $null
foreach ($cand in @(@('py', '-3'), @('python'), @('python3'))) {
    $cmd = Get-Command $cand[0] -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -notlike '*\WindowsApps\*') { $py = $cand; break }
}
if ($py) {
    $extra = if ($py.Length -gt 1) { $py[1..($py.Length - 1)] } else { @() }
    & $py[0] @extra (Join-Path $SkillDir 'scripts\check_environment.py')
} else {
    Write-Host '[WARN] No real Python found (the Microsoft Store stub does not count). Install Python >= 3.11.'
}

Write-Host ('=' * 60)
Write-Host "Skill '$SkillName' successfully installed!"
Write-Host ''
Write-Host 'Supported Coding Agents:'
Write-Host '  - Antigravity / Gemini CLI: Auto-discovers from skills directory'
Write-Host '  - Claude Code (claude): install with -Claude [-Project]; invoke via /databricks-native-agent'
Write-Host ('=' * 60)
